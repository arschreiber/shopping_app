"""Die Migration muss dasselbe Schema erzeugen wie die Modelle (ARCHITECTURE.md §9)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from mealplan.db.models import Base

BACKEND = Path(__file__).resolve().parents[2]


def test_alembic_upgrade_creates_every_table(tmp_path, monkeypatch):
    monkeypatch.setenv("MEALPLAN_DATA_DIR", str(tmp_path))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'mealplan.sqlite3'}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    expected = set(Base.metadata.tables)
    missing = expected - tables
    assert not missing, f"Migration fehlt: {sorted(missing)}"
    # Auch jede Spalte: die Tests laufen auf `create_all`, die App auf den Migrationen.
    for table in Base.metadata.sorted_tables:
        columns = {column["name"] for column in inspector.get_columns(table.name)}
        absent = {column.name for column in table.columns} - columns
        assert not absent, f"Migration fehlt für {table.name}: {sorted(absent)}"
    engine.dispose()
    # Phase-2-Tabellen sind von Anfang an da (ARCHITECTURE.md §3)
    assert {"store", "offer", "offer_snapshot", "offer_match"} <= tables


# Alles, was per ON DELETE CASCADE an einem Gericht hängt - samt Wochenplan.
CHILD_TABLES = ("ingredient", "dish_category", "slot_assignment", "cook_log")


def test_migrations_keep_child_rows(tmp_path, monkeypatch):
    """Keine Migration darf Rezepte, Kategorien, Pläne oder Kochhistorie kosten.

    Unter SQLite baut `batch_alter_table` die Tabelle neu - anlegen, kopieren,
    `drop table`, umbenennen. Mit `foreign_keys=ON` nimmt dieses DROP jede Zeile mit,
    die per ON DELETE CASCADE daran hängt: ein Schema-Zusatz löscht dann stillschweigend
    das Rezept. Deshalb wandert hier ein echter Datenbestand durch die ganze Kette.
    """
    monkeypatch.setenv("MEALPLAN_DATA_DIR", str(tmp_path))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))

    script = ScriptDirectory.from_config(config)
    revisions = [rev.revision for rev in script.walk_revisions()][::-1]
    command.upgrade(config, revisions[0])

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'mealplan.sqlite3'}")
    with engine.begin() as connection:
        for statement in (
            "insert into article (canonical_name, unit, is_staple, is_watchlist) "
            "values ('Basmatireis', 'G', 0, 0)",
            "insert into dish (name, portions, packable, effort, suitable_for, archived) "
            "values ('Reispfanne', 2, 1, 'QUICK', 'BOTH', 0)",
            "insert into ingredient (dish_id, article_id, quantity, unit, sort_order) "
            "values (1, 1, 250, 'G', 0)",
            "insert into category (axis, name) values ('SIDE', 'Reis')",
            "insert into dish_category (dish_id, category_id) values (1, 1)",
            "insert into week (iso_year, iso_week, planner_seed, version) "
            "values (2026, 40, 0, 1)",
            "insert into slot (week_id, day, meal, eaters_home, packed_portions, "
            "time_budget, special, pinned) values (1, 0, 'DINNER', 2, 2, 'PLENTY', 'NONE', 0)",
            "insert into slot_assignment (slot_id, kind, dish_id, doubled) "
            "values (1, 'DISH', 1, 1)",
            "insert into cook_log (slot_id, dish_id, cooked_at, confirmed) "
            "values (1, 1, '2026-09-28', 1)",
        ):
            connection.execute(text(statement))

    for revision in revisions[1:]:
        command.upgrade(config, revision)
        with engine.connect() as connection:
            for table in CHILD_TABLES:
                left = connection.execute(text(f"select count(*) from {table}")).scalar()
                assert left == 1, f"Migration {revision} hat {table} gelöscht"

    with engine.connect() as connection:
        factor = connection.execute(text("select factor from slot_assignment")).scalar()
        broken = connection.execute(text("pragma foreign_key_check")).fetchall()
    assert factor == 2, "aus 'doubled' muss Faktor 2 werden"
    assert broken == []
    engine.dispose()


def test_portions_one_to_three_are_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("MEALPLAN_DATA_DIR", str(tmp_path))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'mealplan.sqlite3'}")
    insert = text(
        "insert into dish (name, portions, packable, effort, suitable_for, archived) "
        "values (:name, :portions, 1, 'QUICK', 'BOTH', 0)"
    )
    with engine.begin() as connection:
        for portions in (1, 2, 3):
            connection.execute(insert, {"name": f"P{portions}", "portions": portions})
    for portions in (0, 4):
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(insert, {"name": f"P{portions}", "portions": portions})
    engine.dispose()


def test_effort_and_time_shrink_to_two_levels(tmp_path, monkeypatch):
    """aufwendig -> normal, viel Zeit -> normal, keine Zeit -> wenig (das Nächste)."""
    monkeypatch.setenv("MEALPLAN_DATA_DIR", str(tmp_path))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "3f7940826523")

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'mealplan.sqlite3'}")
    with engine.begin() as connection:
        for name, effort in (("Gratin", "ELABORATE"), ("Curry", "NORMAL"), ("Pfanne", "QUICK")):
            connection.execute(
                text("insert into dish (name, portions, packable, effort, suitable_for, "
                     "archived) values (:name, 2, 1, :effort, 'BOTH', 0)"),
                {"name": name, "effort": effort},
            )
        connection.execute(
            text("insert into week (iso_year, iso_week, planner_seed, version) "
                 "values (2026, 41, 0, 1)")
        )
        for day, budget in enumerate(("PLENTY", "LITTLE", "NONE")):
            connection.execute(
                text("insert into slot (week_id, day, meal, eaters_home, packed_portions, "
                     "packed_fresh, time_budget, special, pinned) "
                     "values (1, :day, 'DINNER', 2, 0, 0, :budget, 'NONE', 0)"),
                {"day": day, "budget": budget},
            )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        efforts = dict(connection.execute(text("select name, effort from dish")).all())
        budgets = [
            row[0]
            for row in connection.execute(text("select time_budget from slot order by day"))
        ]
    engine.dispose()
    assert efforts == {"Gratin": "NORMAL", "Curry": "NORMAL", "Pfanne": "QUICK"}
    assert budgets == ["NORMAL", "LITTLE", "LITTLE"]


def test_eating_out_becomes_nobody_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MEALPLAN_DATA_DIR", str(tmp_path))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "bb1c22ee6a86")

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'mealplan.sqlite3'}")
    with engine.begin() as connection:
        connection.execute(
            text("insert into week (iso_year, iso_week, planner_seed, version) "
                 "values (2026, 41, 0, 1)")
        )
        connection.execute(
            text("insert into slot (week_id, day, meal, eaters_home, packed_portions, "
                 "packed_fresh, time_budget, special, pinned) "
                 "values (1, 0, 'DINNER', 2, 1, 1, 'PLENTY', 'EATING_OUT', 0)")
        )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        row = connection.execute(
            text("select special, eaters_home, packed_portions, packed_fresh from slot")
        ).one()
    engine.dispose()
    assert tuple(row) == ("NONE", 0, 0, 0)
