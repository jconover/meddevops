"""Postgres connection pool and request-scoped connections."""

from collections.abc import Iterator

from fastapi import Request
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def create_pool(conninfo: str) -> ConnectionPool:
    """Open a small pool. An empty conninfo means use libpq environment variables."""
    return ConnectionPool(
        conninfo, min_size=1, max_size=5, timeout=5, kwargs={"row_factory": dict_row}, open=True
    )


def get_conn(request: Request) -> Iterator[Connection]:
    """FastAPI dependency: borrow a connection for the length of one request."""
    with request.app.state.pool.connection() as conn:
        yield conn
