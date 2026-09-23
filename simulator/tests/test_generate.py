import random
from datetime import UTC, datetime

from simulator.generate import INVALID_LOG, generate_procedure, invalid_key, object_key
from telemetry import LogValidationError, dump_log, parse_log

START = datetime(2026, 9, 22, 14, 0, tzinfo=UTC)


def test_generated_log_is_valid_and_ordered():
    log = generate_procedure("dev-001", START, random.Random(1), n_events=20)
    assert parse_log(dump_log(log).encode()) == log
    assert len(log.events) == 20
    stamps = [e.ts for e in log.events]
    assert stamps == sorted(stamps)
    assert all(log.header.started_at <= t <= log.header.ended_at for t in stamps)


def test_same_seed_same_log():
    a = generate_procedure("dev-001", START, random.Random(7))
    b = generate_procedure("dev-001", START, random.Random(7))
    assert a == b


def test_object_key_layout():
    log = generate_procedure("dev-002", START, random.Random(1))
    key = object_key(log.header)
    assert key == f"raw/device=dev-002/date=2026-09-22/{log.header.procedure_id}.jsonl"


def test_invalid_log_fails_validation():
    try:
        parse_log(INVALID_LOG)
    except LogValidationError:
        pass
    else:
        raise AssertionError("INVALID_LOG should not parse")


def test_invalid_key_under_raw_prefix():
    key = invalid_key(START, random.Random(1))
    assert key.startswith("raw/device=dev-bad/date=2026-09-22/invalid-")
    assert key.endswith(".jsonl")
