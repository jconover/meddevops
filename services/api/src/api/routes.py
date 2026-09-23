"""Read-only REST endpoints over ingested telemetry."""

from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg import Connection

from api.db import get_conn
from api.schemas import Device, EventPage, IngestFile, IngestStatus, Procedure

router = APIRouter()
Conn = Annotated[Connection, Depends(get_conn)]

PROCEDURE_COLUMNS = "id, device_id, procedure_type, started_at, ended_at, status"


@router.get("/health")
def health(request: Request) -> dict:
    """Liveness plus database reachability, used by the load balancer."""
    try:
        with request.app.state.pool.connection() as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError as e:
        raise HTTPException(503, "database unavailable") from e
    return {"status": "ok"}


@router.get("/devices")
def list_devices(conn: Conn) -> list[Device]:
    return conn.execute(
        "SELECT id, model, first_seen, last_seen FROM devices ORDER BY id"
    ).fetchall()


@router.get("/devices/{device_id}/procedures")
def list_device_procedures(device_id: str, conn: Conn) -> list[Procedure]:
    if conn.execute("SELECT 1 FROM devices WHERE id = %s", (device_id,)).fetchone() is None:
        raise HTTPException(404, "device not found")
    return conn.execute(
        f"SELECT {PROCEDURE_COLUMNS} FROM procedures WHERE device_id = %s ORDER BY started_at DESC",
        (device_id,),
    ).fetchall()


@router.get("/procedures/{procedure_id}")
def get_procedure(procedure_id: UUID, conn: Conn) -> Procedure:
    row = conn.execute(
        f"SELECT {PROCEDURE_COLUMNS} FROM procedures WHERE id = %s", (procedure_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "procedure not found")
    return row


@router.get("/procedures/{procedure_id}/events")
def list_events(
    procedure_id: UUID,
    conn: Conn,
    event_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    cursor: Annotated[int, Query(ge=0)] = 0,
) -> EventPage:
    """Events in id order. Pass the returned next_cursor to get the following page."""
    if conn.execute("SELECT 1 FROM procedures WHERE id = %s", (procedure_id,)).fetchone() is None:
        raise HTTPException(404, "procedure not found")
    items = conn.execute(
        """
        SELECT id, ts, event_type, payload FROM events
        WHERE procedure_id = %(pid)s
          AND id > %(cursor)s
          AND (%(event_type)s::text IS NULL OR event_type = %(event_type)s)
        ORDER BY id
        LIMIT %(limit)s
        """,
        {"pid": procedure_id, "cursor": cursor, "event_type": event_type, "limit": limit},
    ).fetchall()
    next_cursor = items[-1]["id"] if len(items) == limit else None
    return EventPage(items=items, next_cursor=next_cursor)


@router.get("/ingest/files")
def list_ingest_files(conn: Conn, status: IngestStatus | None = None) -> list[IngestFile]:
    return conn.execute(
        """
        SELECT s3_key, status, event_count, error, received_at, processed_at FROM ingest_files
        WHERE (%(status)s::text IS NULL OR status = %(status)s)
        ORDER BY processed_at DESC
        """,
        {"status": status},
    ).fetchall()
