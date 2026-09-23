"""Apply numbered SQL migrations in order. Safe to run from several processes at once."""

from importlib.resources import files

import psycopg

MIGRATION_LOCK_ID = 7331001

CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    name text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


def apply_migrations(conninfo: str) -> list[str]:
    """Apply pending migrations; return the names applied in this run."""
    migrations = sorted(
        (f for f in (files("api") / "migrations").iterdir() if f.name.endswith(".sql")),
        key=lambda f: f.name,
    )
    applied = []
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
        conn.execute(CREATE_TRACKING_TABLE)
        done = {row[0] for row in conn.execute("SELECT name FROM schema_migrations")}
        for migration in migrations:
            if migration.name in done:
                continue
            with conn.transaction():
                conn.execute(migration.read_text())
                conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (migration.name,))
            applied.append(migration.name)
    return applied


def main() -> None:
    """Apply migrations using libpq environment variables (PGHOST, PGUSER, ...)."""
    applied = apply_migrations("")
    print(f"applied migrations: {', '.join(applied) or 'none'}")


if __name__ == "__main__":
    main()
