from api.migrate import apply_migrations


def test_tables_exist(db):
    rows = db.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchall()
    assert {r[0] for r in rows} >= {
        "devices",
        "procedures",
        "events",
        "ingest_files",
        "schema_migrations",
    }


def test_second_run_applies_nothing(pg_url):
    assert apply_migrations(pg_url) == []


def test_migration_recorded(db):
    names = [r[0] for r in db.execute("SELECT name FROM schema_migrations").fetchall()]
    assert names == ["001_init.sql"]
