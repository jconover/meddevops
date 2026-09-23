import json
from uuid import uuid4

import pytest
from telemetry import LogValidationError, dump_log, parse_log

HEADER = {
    "kind": "procedure",
    "procedure_id": str(uuid4()),
    "device_id": "dev-001",
    "model": "sim-x1",
    "procedure_type": "endoscopy",
    "started_at": "2026-09-22T14:00:00Z",
    "ended_at": "2026-09-22T15:10:00Z",
    "status": "completed",
}
EVENT = {
    "kind": "event",
    "ts": "2026-09-22T14:02:13Z",
    "event_type": "instrument_attached",
    "payload": {"instrument": "grasper"},
}


def to_bytes(*lines: dict | str) -> bytes:
    return "\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines).encode()


def test_parses_header_and_events():
    log = parse_log(to_bytes(HEADER, EVENT, EVENT))
    assert log.header.device_id == "dev-001"
    assert len(log.events) == 2
    assert log.events[0].payload == {"instrument": "grasper"}


def test_ignores_blank_lines():
    log = parse_log(to_bytes(HEADER, "", EVENT, ""))
    assert len(log.events) == 1


def test_dump_round_trips():
    log = parse_log(to_bytes(HEADER, EVENT))
    assert parse_log(dump_log(log).encode()) == log


def test_empty_file_rejected():
    with pytest.raises(LogValidationError, match="empty file"):
        parse_log(b"\n\n")


def test_invalid_utf8_rejected():
    with pytest.raises(LogValidationError, match="UTF-8"):
        parse_log(b"\xff\xfe")


def test_missing_header_field_reports_line_1():
    bad = {k: v for k, v in HEADER.items() if k != "device_id"}
    with pytest.raises(LogValidationError, match="line 1: device_id"):
        parse_log(to_bytes(bad, EVENT))


def test_bad_json_reports_line_number():
    with pytest.raises(LogValidationError, match="line 3"):
        parse_log(to_bytes(HEADER, EVENT, "not json"))


def test_naive_timestamp_rejected():
    with pytest.raises(LogValidationError, match="line 2: ts"):
        parse_log(to_bytes(HEADER, {**EVENT, "ts": "2026-09-22T14:02:13"}))


def test_unknown_field_rejected():
    with pytest.raises(LogValidationError, match="line 2"):
        parse_log(to_bytes(HEADER, {**EVENT, "extra": 1}))
