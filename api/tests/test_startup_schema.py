"""Start funkce: těžké DDL (create_all + ALTERy) jen při změně otisku schématu (rychlý cold start)."""
import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["INTERNAL_API_TOKEN"] = "test-token"

import app.main as m  # noqa: E402


def test_fingerprint_is_stable_and_sensitive_to_migrations(monkeypatch):
    a = m._schema_fingerprint()
    assert a == m._schema_fingerprint() and len(a) == 40
    monkeypatch.setattr(m, "_PG_MIGRATIONS", m._PG_MIGRATIONS + [("x", "ALTER TABLE t ADD COLUMN IF NOT EXISTS c INT")])
    assert m._schema_fingerprint() != a          # nová migrace → jednorázově se provede


def test_fingerprint_changes_when_a_model_column_is_added():
    from sqlalchemy import Column, Integer
    from app.models.regime import RegimeSnapshot
    a = m._schema_fingerprint()
    col = Column("tmp_probe_col", Integer)
    RegimeSnapshot.__table__.append_column(col)
    try:
        assert m._schema_fingerprint() != a
    finally:
        RegimeSnapshot.__table__._columns.remove(col)
    assert m._schema_fingerprint() == a


def test_all_known_migrations_are_idempotent_alters():
    assert len(m._PG_MIGRATIONS) >= 8
    for name, sql in m._PG_MIGRATIONS:
        idempotent_alter = sql.startswith("ALTER TABLE") and "IF NOT EXISTS" in sql
        guarded_update = sql.startswith("UPDATE") and " WHERE " in sql  # opakovatelný backfill
        assert idempotent_alter or guarded_update, name


def test_anthropic_not_imported_at_startup():
    """Knihovna anthropic (~1 s) se nesmí načítat při importu appky — jen při prvním volání LLM."""
    import subprocess, sys
    code = ("import os;os.environ.update(APP_ENV='test',DATABASE_URL='sqlite+aiosqlite:///:memory:',"
            "ANTHROPIC_API_KEY='x',INTERNAL_API_TOKEN='x');import sys;import app.main;"
            "print('anthropic' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))
    assert out.stdout.strip().splitlines()[-1] == "False", out.stdout + out.stderr
