"""Die Migration muss dasselbe Schema erzeugen wie die Modelle (ARCHITECTURE.md §9)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from mealplan.db.models import Base

BACKEND = Path(__file__).resolve().parents[2]


def test_alembic_upgrade_creates_every_table(tmp_path, monkeypatch):
    monkeypatch.setenv("MEALPLAN_DATA_DIR", str(tmp_path))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'mealplan.sqlite3'}")
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    expected = set(Base.metadata.tables)
    missing = expected - tables
    assert not missing, f"Migration fehlt: {sorted(missing)}"
    # Phase-2-Tabellen sind von Anfang an da (ARCHITECTURE.md §3)
    assert {"store", "offer", "offer_snapshot", "offer_match"} <= tables
