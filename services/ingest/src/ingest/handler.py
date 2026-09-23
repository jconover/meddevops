"""Lambda entry point: SQS batch of S3 notifications -> validated rows in Postgres."""

import json
import logging
import os
from datetime import datetime
from urllib.parse import unquote_plus

import boto3
import psycopg
from psycopg.conninfo import make_conninfo
from telemetry import LogValidationError, parse_log

from ingest.store import record_quarantine, store_log

logger = logging.getLogger()
logger.setLevel(logging.INFO)

RAW_PREFIX = "raw/"
QUARANTINE_PREFIX = "quarantine/"

_conn: psycopg.Connection | None = None


def lambda_handler(event: dict, context) -> dict:
    """Process an SQS batch, reporting failed messages so only they are retried."""
    return handle_batch(event["Records"], boto3.client("s3"), _db_connection())


def handle_batch(records: list[dict], s3, conn: psycopg.Connection) -> dict:
    """Process each SQS message; collect the IDs of messages that should be retried."""
    failures = []
    for record in records:
        try:
            for notification in json.loads(record["body"]).get("Records", []):
                process_object(s3, conn, notification)
        except Exception:
            logger.exception("message %s failed", record["messageId"])
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}


def process_object(s3, conn: psycopg.Connection, notification: dict) -> None:
    """Validate and store one S3 object, or quarantine it if it can never succeed."""
    bucket = notification["s3"]["bucket"]["name"]
    key = unquote_plus(notification["s3"]["object"]["key"])
    received_at = datetime.fromisoformat(notification["eventTime"])
    data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    try:
        stored = store_log(conn, key, received_at, parse_log(data))
    except LogValidationError as e:
        _quarantine(s3, conn, bucket, key, received_at, str(e))
    except psycopg.errors.UniqueViolation:
        _quarantine(s3, conn, bucket, key, received_at, "duplicate procedure_id")
    else:
        logger.info("%s %s", "stored" if stored else "already ingested", key)


def _quarantine(s3, conn, bucket: str, key: str, received_at: datetime, error: str) -> None:
    target = QUARANTINE_PREFIX + key.removeprefix(RAW_PREFIX)
    s3.copy_object(Bucket=bucket, Key=target, CopySource={"Bucket": bucket, "Key": key})
    record_quarantine(conn, key, received_at, error)
    logger.warning("quarantined %s: %s", key, error)


def _db_connection() -> psycopg.Connection:
    """Reuse one connection across warm invocations; reconnect if it was closed."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg.connect(_conninfo_from_secret(os.environ["DB_SECRET_ARN"]), autocommit=True)
    return _conn


def _conninfo_from_secret(secret_arn: str) -> str:
    secret = json.loads(
        boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)["SecretString"]
    )
    return make_conninfo(
        host=secret["host"],
        port=secret["port"],
        dbname=secret["dbname"],
        user=secret["username"],
        password=secret["password"],
    )
