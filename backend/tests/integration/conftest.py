from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from mealplan.config import Settings
from mealplan.db import session as session_module
from mealplan.db.models import Base
from mealplan.integrations.bring.text_export import TextExportSync
from mealplan.main import create_app


class _StubCatalog:
    """Kein Netz im Test - der Katalog liefert einen festen Vorschlag."""

    def suggest(self, name: str, *, limit: int = 5) -> list:
        from mealplan.ports import CatalogSuggestion

        return [CatalogSuggestion(name=name.title(), category="Sonstiges", score=90.0)]

    def is_cached(self) -> bool:
        return True


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # Ausdrücklich ohne Angebotsquelle und Scheduler - egal, was in der .env steht.
    return Settings(
        data_dir=tmp_path,
        bring_sync="text",
        catalog_autofetch=False,
        korbunio_url=None,
        offer_fetch_enabled=False,
    )


@pytest.fixture
def engine(settings: Settings):
    """Schema per `Base.metadata` - die Migration selbst prueft `test_migrations.py`."""
    settings.ensure_dirs()
    engine = create_engine(settings.sqlalchemy_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_module.set_engine(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    factory = sessionmaker(engine, expire_on_commit=False)
    session = factory()
    yield session
    session.commit()
    session.close()


@pytest.fixture
def client(engine, settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.state.catalog = _StubCatalog()
    app.state.sync = TextExportSync()
    with TestClient(app) as test_client:
        test_client.app.state.catalog = _StubCatalog()
        test_client.app.state.sync = TextExportSync()
        yield test_client


@pytest.fixture
def seeded(client: TestClient, engine):
    """Beispieldaten ueber den echten Seed-Pfad."""
    from mealplan.cli.demo import seed

    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        result = seed(session)
        session.commit()
    return result
