"""FastAPI-Dependencies und Fehler-Mapping (ARCHITECTURE.md §6)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db.session import session_scope
from ..ports import BringCatalog, ShoppingListSync


def db() -> Iterator[Session]:
    with session_scope() as session:
        yield session


def settings() -> Settings:
    return get_settings()


def sync_adapter(request: Request) -> ShoppingListSync:
    return request.app.state.sync


def catalog(request: Request) -> BringCatalog:
    return request.app.state.catalog


# `scope="function"`: committen, *bevor* die Antwort rausgeht. Der Standard ("request")
# committet erst danach - dann sieht der nächste Request des Clients die Daten der
# vorigen Antwort womöglich noch nicht, und scheitert der Commit, hat der Client schon
# sein 200. Genau so entstand der 500 beim Raster einer frisch geöffneten Woche.
SessionDep = Annotated[Session, Depends(db, scope="function")]
SettingsDep = Annotated[Settings, Depends(settings)]
SyncDep = Annotated[ShoppingListSync, Depends(sync_adapter)]
CatalogDep = Annotated[BringCatalog, Depends(catalog)]
