"""Pydantic models for one procedure log file."""

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ProcedureHeader(BaseModel):
    """First line of a log file: which device ran which procedure, and when."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["procedure"]
    procedure_id: UUID
    device_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    procedure_type: str = Field(min_length=1)
    started_at: AwareDatetime
    ended_at: AwareDatetime
    status: Literal["completed", "aborted"]


class Event(BaseModel):
    """One timestamped device event within a procedure."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["event"]
    ts: AwareDatetime
    event_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ProcedureLog:
    """A parsed log file: one header followed by its events."""

    header: ProcedureHeader
    events: list[Event]
