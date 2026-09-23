"""Shared pytest fixtures."""

import psycopg
import pytest
from api.migrate import apply_migrations
from moto import mock_aws
from testcontainers.postgres import PostgresContainer


@pytest.fixture
def aws(monkeypatch):
    """Mocked AWS with fake credentials so no real account is touched."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        yield


@pytest.fixture(scope="session")
def pg_url():
    """URL of a migrated throwaway Postgres (started once per test session)."""
    with PostgresContainer("postgres:18-alpine", driver=None) as pg:
        url = pg.get_connection_url()
        apply_migrations(url)
        yield url


@pytest.fixture
def db(pg_url):
    """Autocommit connection; all data is removed after each test."""
    with psycopg.connect(pg_url, autocommit=True) as conn:
        yield conn
        conn.execute("TRUNCATE events, procedures, devices, ingest_files")
