"""Write validated procedure logs to Postgres."""

from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb
from telemetry import ProcedureLog

CLAIM_FILE = """
INSERT INTO ingest_files (s3_key, status, event_count, received_at)
VALUES (%s, 'processed', %s, %s)
ON CONFLICT (s3_key) DO NOTHING
RETURNING s3_key
"""

UPSERT_DEVICE = """
INSERT INTO devices (id, model, first_seen, last_seen)
VALUES (%s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    model = EXCLUDED.model,
    first_seen = LEAST(devices.first_seen, EXCLUDED.first_seen),
    last_seen = GREATEST(devices.last_seen, EXCLUDED.last_seen)
"""

INSERT_PROCEDURE = """
INSERT INTO procedures (id, device_id, procedure_type, started_at, ended_at, status)
VALUES (%s, %s, %s, %s, %s, %s)
"""

INSERT_EVENT = """
INSERT INTO events (procedure_id, ts, event_type, payload) VALUES (%s, %s, %s, %s)
"""

INSERT_QUARANTINE = """
INSERT INTO ingest_files (s3_key, status, error, received_at)
VALUES (%s, 'quarantined', %s, %s)
ON CONFLICT (s3_key) DO NOTHING
"""


def store_log(
    conn: psycopg.Connection, s3_key: str, received_at: datetime, log: ProcedureLog
) -> bool:
    """Store a log in one transaction. Return False if this key was already ingested.

    The ingest_files row is claimed first, so concurrent deliveries of the same key
    serialize on its primary key and only one of them writes data.
    """
    h = log.header
    with conn.transaction():
        claimed = conn.execute(CLAIM_FILE, (s3_key, len(log.events), received_at)).fetchone()
        if claimed is None:
            return False
        conn.execute(UPSERT_DEVICE, (h.device_id, h.model, h.started_at, h.ended_at))
        conn.execute(
            INSERT_PROCEDURE,
            (h.procedure_id, h.device_id, h.procedure_type, h.started_at, h.ended_at, h.status),
        )
        with conn.cursor() as cur:
            cur.executemany(
                INSERT_EVENT,
                [(h.procedure_id, e.ts, e.event_type, Jsonb(e.payload)) for e in log.events],
            )
    return True


def record_quarantine(
    conn: psycopg.Connection, s3_key: str, received_at: datetime, error: str
) -> None:
    """Record a file that failed validation. Recording the same key again is a no-op."""
    conn.execute(INSERT_QUARANTINE, (s3_key, error, received_at))
