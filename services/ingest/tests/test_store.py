import random
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from ingest.store import record_quarantine, store_log
from simulator.generate import generate_procedure

START = datetime(2026, 9, 22, 14, 0, tzinfo=UTC)
RECEIVED = datetime(2026, 9, 22, 16, 0, tzinfo=UTC)


def make_log(device_id="dev-001", started_at=START, seed=1, n_events=5):
    return generate_procedure(device_id, started_at, random.Random(seed), n_events=n_events)


def count(db, table):
    return db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_stores_device_procedure_events_and_file(db):
    log = make_log()
    assert store_log(db, "raw/a.jsonl", RECEIVED, log) is True
    assert count(db, "devices") == 1
    assert count(db, "procedures") == 1
    assert count(db, "events") == 5
    row = db.execute("SELECT status, event_count FROM ingest_files").fetchone()
    assert row == ("processed", 5)


def test_same_key_twice_is_noop(db):
    log = make_log()
    store_log(db, "raw/a.jsonl", RECEIVED, log)
    assert store_log(db, "raw/a.jsonl", RECEIVED, log) is False
    assert count(db, "events") == 5


def test_device_seen_window_widens(db):
    store_log(db, "raw/a.jsonl", RECEIVED, make_log(started_at=START, seed=1))
    store_log(db, "raw/b.jsonl", RECEIVED, make_log(started_at=START - timedelta(days=1), seed=2))
    first_seen, last_seen = db.execute("SELECT first_seen, last_seen FROM devices").fetchone()
    assert first_seen == START - timedelta(days=1)
    assert last_seen > START


def test_duplicate_procedure_under_new_key_raises_and_rolls_back(db):
    log = make_log()
    store_log(db, "raw/a.jsonl", RECEIVED, log)
    with pytest.raises(psycopg.errors.UniqueViolation):
        store_log(db, "raw/b.jsonl", RECEIVED, log)
    assert count(db, "ingest_files") == 1
    assert count(db, "events") == 5


def test_record_quarantine(db):
    record_quarantine(db, "raw/bad.jsonl", RECEIVED, "line 1: device_id: Field required")
    record_quarantine(db, "raw/bad.jsonl", RECEIVED, "line 1: device_id: Field required")
    row = db.execute("SELECT status, error, event_count FROM ingest_files").fetchone()
    assert row == ("quarantined", "line 1: device_id: Field required", None)
