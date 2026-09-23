"""API response models."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

IngestStatus = Literal["processed", "quarantined"]


class Device(BaseModel):
    id: str
    model: str
    first_seen: datetime
    last_seen: datetime


class Procedure(BaseModel):
    id: UUID
    device_id: str
    procedure_type: str
    started_at: datetime
    ended_at: datetime
    status: str


class Event(BaseModel):
    id: int
    ts: datetime
    event_type: str
    payload: dict[str, Any]


class EventPage(BaseModel):
    items: list[Event]
    next_cursor: int | None


class IngestFile(BaseModel):
    s3_key: str
    status: IngestStatus
    event_count: int | None
    error: str | None
    received_at: datetime
    processed_at: datetime
