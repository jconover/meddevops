import json
import random
from datetime import UTC, datetime
from urllib.parse import quote_plus

import boto3
import pytest
from ingest.handler import handle_batch
from simulator.generate import INVALID_LOG, generate_procedure
from telemetry import dump_log

BUCKET = "raw-test"
START = datetime(2026, 9, 22, 14, 0, tzinfo=UTC)


@pytest.fixture
def s3(aws):
    client = boto3.client("s3")
    client.create_bucket(Bucket=BUCKET)
    return client


def sqs_record(key: str, message_id: str = "m1") -> dict:
    notification = {
        "eventTime": "2026-09-22T16:00:00.000Z",
        "s3": {"bucket": {"name": BUCKET}, "object": {"key": quote_plus(key, safe="/")}},
    }
    return {"messageId": message_id, "body": json.dumps({"Records": [notification]})}


def put_valid(s3, key: str, seed: int = 1) -> None:
    log = generate_procedure("dev-001", START, random.Random(seed), n_events=4)
    s3.put_object(Bucket=BUCKET, Key=key, Body=dump_log(log).encode())


def test_valid_file_is_stored(s3, db):
    put_valid(s3, "raw/device=dev-001/date=2026-09-22/a.jsonl")
    result = handle_batch([sqs_record("raw/device=dev-001/date=2026-09-22/a.jsonl")], s3, db)
    assert result == {"batchItemFailures": []}
    assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 4


def test_invalid_file_is_quarantined_not_retried(s3, db):
    s3.put_object(Bucket=BUCKET, Key="raw/bad.jsonl", Body=INVALID_LOG)
    result = handle_batch([sqs_record("raw/bad.jsonl")], s3, db)
    assert result == {"batchItemFailures": []}
    status, error = db.execute("SELECT status, error FROM ingest_files").fetchone()
    assert status == "quarantined"
    assert error.startswith("line 1:")
    s3.head_object(Bucket=BUCKET, Key="quarantine/bad.jsonl")


def test_null_byte_payload_is_quarantined(s3, db):
    log = generate_procedure("dev-001", START, random.Random(1), n_events=4)
    log.events[0].payload["note"] = "bad\x00char"
    key = "raw/nullbyte.jsonl"
    s3.put_object(Bucket=BUCKET, Key=key, Body=dump_log(log).encode())
    result = handle_batch([sqs_record(key)], s3, db)
    assert result == {"batchItemFailures": []}
    status, error = db.execute(
        "SELECT status, error FROM ingest_files WHERE s3_key = %s", (key,)
    ).fetchone()
    assert status == "quarantined"
    assert error


def test_duplicate_procedure_is_quarantined(s3, db):
    put_valid(s3, "raw/a.jsonl", seed=1)
    put_valid(s3, "raw/b.jsonl", seed=1)
    handle_batch([sqs_record("raw/a.jsonl", "m1"), sqs_record("raw/b.jsonl", "m2")], s3, db)
    row = db.execute(
        "SELECT status, error FROM ingest_files WHERE s3_key = 'raw/b.jsonl'"
    ).fetchone()
    assert row == ("quarantined", "duplicate procedure_id")


def test_redelivery_is_noop(s3, db):
    put_valid(s3, "raw/a.jsonl")
    handle_batch([sqs_record("raw/a.jsonl")], s3, db)
    handle_batch([sqs_record("raw/a.jsonl")], s3, db)
    assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 4


def test_missing_object_fails_only_that_message(s3, db):
    put_valid(s3, "raw/a.jsonl")
    records = [sqs_record("raw/missing.jsonl", "m1"), sqs_record("raw/a.jsonl", "m2")]
    result = handle_batch(records, s3, db)
    assert result == {"batchItemFailures": [{"itemIdentifier": "m1"}]}
    assert db.execute("SELECT count(*) FROM procedures").fetchone()[0] == 1


def test_s3_test_event_is_ignored(s3, db):
    record = {
        "messageId": "m1",
        "body": json.dumps({"Service": "Amazon S3", "Event": "s3:TestEvent"}),
    }
    assert handle_batch([record], s3, db) == {"batchItemFailures": []}


def test_url_encoded_key(s3, db):
    key = "raw/device=dev-001/date=2026-09-22/with space.jsonl"
    put_valid(s3, key)
    handle_batch([sqs_record(key)], s3, db)
    assert db.execute("SELECT s3_key FROM ingest_files").fetchone()[0] == key
