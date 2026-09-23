import random
import uuid
from datetime import UTC, datetime

import pytest
from api.app import create_app
from fastapi.testclient import TestClient
from ingest.store import record_quarantine, store_log
from simulator.generate import generate_procedure

START = datetime(2026, 9, 22, 14, 0, tzinfo=UTC)
RECEIVED = datetime(2026, 9, 22, 16, 0, tzinfo=UTC)


@pytest.fixture
def client(pg_url, db):
    with TestClient(create_app(pg_url)) as c:
        yield c


@pytest.fixture
def log(db):
    log = generate_procedure("dev-001", START, random.Random(1), n_events=5)
    store_log(db, "raw/a.jsonl", RECEIVED, log)
    return log


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_health_503_when_database_unreachable():
    with TestClient(create_app("postgresql://nobody@127.0.0.1:1/none")) as c:
        assert c.get("/health").status_code == 503


def test_devices(client, log):
    body = client.get("/devices").json()
    assert [d["id"] for d in body] == ["dev-001"]
    assert body[0]["model"] == "sim-x1"


def test_device_procedures(client, log):
    body = client.get("/devices/dev-001/procedures").json()
    assert [p["id"] for p in body] == [str(log.header.procedure_id)]


def test_unknown_device_404(client):
    assert client.get("/devices/nope/procedures").status_code == 404


def test_procedure(client, log):
    body = client.get(f"/procedures/{log.header.procedure_id}").json()
    assert body["device_id"] == "dev-001"
    assert body["status"] == log.header.status


def test_unknown_procedure_404(client):
    assert client.get(f"/procedures/{uuid.uuid4()}").status_code == 404


def test_bad_procedure_id_422(client):
    assert client.get("/procedures/not-a-uuid").status_code == 422


def test_events_paginate(client, log):
    url = f"/procedures/{log.header.procedure_id}/events"
    first = client.get(url, params={"limit": 2}).json()
    second = client.get(url, params={"limit": 2, "cursor": first["next_cursor"]}).json()
    third = client.get(url, params={"limit": 2, "cursor": second["next_cursor"]}).json()
    ids = [e["id"] for page in (first, second, third) for e in page["items"]]
    assert len(ids) == 5 and ids == sorted(ids)
    assert third["next_cursor"] is None


def test_events_filter_by_type(client, log):
    wanted = log.events[0].event_type
    url = f"/procedures/{log.header.procedure_id}/events"
    items = client.get(url, params={"event_type": wanted}).json()["items"]
    assert items and all(e["event_type"] == wanted for e in items)


def test_events_unknown_procedure_404(client):
    assert client.get(f"/procedures/{uuid.uuid4()}/events").status_code == 404


def test_ingest_files_filter(client, db, log):
    record_quarantine(db, "raw/bad.jsonl", RECEIVED, "line 1: json: Invalid JSON")
    body = client.get("/ingest/files", params={"status": "quarantined"}).json()
    assert [f["s3_key"] for f in body] == ["raw/bad.jsonl"]
    assert len(client.get("/ingest/files").json()) == 2


def test_ingest_files_bad_status_422(client):
    assert client.get("/ingest/files", params={"status": "nope"}).status_code == 422
