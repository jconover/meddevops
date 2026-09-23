"""Build synthetic procedure logs."""

import random
import uuid
from datetime import datetime, timedelta

from telemetry import Event, ProcedureHeader, ProcedureLog

INSTRUMENTS = ["grasper", "scissors", "needle_driver", "stapler"]
PROCEDURE_TYPES = ["endoscopy", "biopsy", "resection"]
FAULT_CODES = ["E101", "E204", "E310"]

INVALID_LOG = b'{"kind": "procedure", "device_id": "dev-bad"}\nnot json\n'


def _payload(event_type: str, rng: random.Random) -> dict:
    match event_type:
        case "arm_docked":
            return {"arm": rng.randint(1, 4)}
        case "instrument_attached" | "instrument_detached":
            return {"instrument": rng.choice(INSTRUMENTS)}
        case "camera_moved":
            return {"pan": round(rng.uniform(-30, 30), 1), "tilt": round(rng.uniform(-15, 15), 1)}
        case "energy_applied":
            return {"watts": rng.randint(20, 60), "duration_ms": rng.randint(200, 3000)}
        case "fault":
            return {"code": rng.choice(FAULT_CODES)}
    raise ValueError(f"unknown event type {event_type}")


EVENT_TYPES = [
    "arm_docked",
    "instrument_attached",
    "instrument_detached",
    "camera_moved",
    "energy_applied",
    "fault",
]


def _uuid(rng: random.Random) -> uuid.UUID:
    return uuid.UUID(int=rng.getrandbits(128), version=4)


def generate_procedure(
    device_id: str, started_at: datetime, rng: random.Random, n_events: int = 50
) -> ProcedureLog:
    """Generate one procedure with time-ordered random events."""
    duration = timedelta(minutes=rng.randint(30, 180))
    header = ProcedureHeader(
        kind="procedure",
        procedure_id=_uuid(rng),
        device_id=device_id,
        model="sim-x1",
        procedure_type=rng.choice(PROCEDURE_TYPES),
        started_at=started_at,
        ended_at=started_at + duration,
        status="aborted" if rng.random() < 0.05 else "completed",
    )
    offsets = sorted(rng.uniform(0, duration.total_seconds()) for _ in range(n_events))
    events = []
    for offset in offsets:
        event_type = rng.choice(EVENT_TYPES)
        events.append(
            Event(
                kind="event",
                ts=started_at + timedelta(seconds=offset),
                event_type=event_type,
                payload=_payload(event_type, rng),
            )
        )
    return ProcedureLog(header=header, events=events)


def object_key(header: ProcedureHeader) -> str:
    """S3 key for a log, partitioned by device and date."""
    date = header.started_at.strftime("%Y-%m-%d")
    return f"raw/device={header.device_id}/date={date}/{header.procedure_id}.jsonl"


def invalid_key(now: datetime, rng: random.Random) -> str:
    """S3 key for a deliberately invalid log."""
    return f"raw/device=dev-bad/date={now:%Y-%m-%d}/invalid-{_uuid(rng)}.jsonl"
