"""Bring!-Semantik gegen einen Fake-Adapter (ARCHITECTURE.md §9 "contract").

Geprueft wird die Regel, die Duplikate verhindert (general_plan.md §8 Nr. 8): Push ist
ein Diff gegen die eigenen Einträge, Fremdeinträge werden nie angefasst.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mealplan.db import session as session_module
from mealplan.db.models import Base
from mealplan.domain.enums import SyncKind, SyncStatus
from mealplan.ports import ShoppingListSync, SyncItem, SyncResult, SyncState
from mealplan.services import bring_sync as service

ISO = "2026-W37"


class FakeBring(ShoppingListSync):
    """Verhaelt sich wie eine echte Liste: merkt sich Einträge, gibt UUIDs zurück."""

    name = "fake-bring"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[list[SyncItem], SyncState]] = []
        self.foreign = {"Bier"}  # von Hand in Bring! eingetragen
        self.items: dict[str, str] = {}

    def push(self, desired: list[SyncItem], state: SyncState) -> SyncResult:
        self.calls.append((desired, state))
        if self.fail:
            return SyncResult(ok=False, error="502 Bad Gateway", text_fallback="…")

        known = {item.article_id: item for item in state.items}
        created, updated, removed = [], [], []
        uuids = {}
        for item in desired:
            previous = known.get(item.article_id)
            if previous is None:
                created.append(item)
            elif previous.name != item.name or (previous.spec or "") != item.spec:
                updated.append(item)
            uuids[item.article_id] = f"uuid-{item.article_id}"
            self.items[item.name] = item.spec
        wanted = {item.article_id for item in desired}
        for article_id, previous in known.items():
            if article_id not in wanted:
                removed.append(previous.name)
                self.items.pop(previous.name, None)
        return SyncResult(
            ok=True,
            created=tuple(created),
            updated=tuple(updated),
            removed=tuple(removed),
            list_uuid="list-1",
            item_uuids=uuids,
        )


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'test.sqlite3'}")
    Base.metadata.create_all(engine)
    session_module.set_engine(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        from mealplan.cli.demo import seed
        from mealplan.services.planning import propose_week
        from mealplan.services.shopping_list import get_list

        seed(db)
        propose_week(db, ISO)
        get_list(db, ISO)
        db.commit()
        yield db
    engine.dispose()


def test_first_push_creates_everything(session):
    bring = FakeBring()
    outcome = service.push(session, ISO, bring)
    assert outcome.result.ok
    assert len(outcome.result.created) == outcome.items_sent > 0
    assert not outcome.result.updated


def test_second_push_creates_nothing(session):
    """Der Kern der Anti-Duplikat-Regel: gleicher Stand = kein Schreibvorgang."""
    bring = FakeBring()
    service.push(session, ISO, bring)
    session.commit()

    second = service.push(session, ISO, bring)
    assert second.result.ok
    assert not second.result.created
    assert not second.result.updated
    assert not second.result.removed


def test_changed_quantity_updates_instead_of_duplicating(session):
    from mealplan.services import shopping_list

    bring = FakeBring()
    service.push(session, ISO, bring)
    session.commit()
    before = len(bring.items)

    shopping = shopping_list.get_list(session, ISO, rebuild_first=False)
    item = shopping.items[0]
    item.quantity = (item.quantity or 0) + 500
    item.spec_text = f"{item.quantity} g"
    session.flush()

    second = service.push(session, ISO, bring)
    assert len(second.result.updated) == 1
    assert not second.result.created
    assert len(bring.items) == before, "Kein Duplikat"


def test_removing_an_item_removes_it_in_bring(session):
    from mealplan.services import shopping_list

    bring = FakeBring()
    service.push(session, ISO, bring)
    session.commit()

    shopping = shopping_list.get_list(session, ISO, rebuild_first=False)
    gone = shopping.items[0].article_id
    shopping_list.remove_item(session, ISO, article_id=gone)
    session.flush()

    second = service.push(session, ISO, bring)
    assert len(second.result.removed) == 1


def test_foreign_entries_are_never_touched(session):
    """Wir kennen nur unsere eigenen Artikel - alles andere bleibt unberuehrt."""
    bring = FakeBring()
    service.push(session, ISO, bring)
    assert "Bier" in bring.foreign
    assert "Bier" not in bring.items


def test_a_broken_bring_does_not_block_the_monday(session):
    bring = FakeBring(fail=True)
    outcome = service.push(session, ISO, bring)

    assert outcome.result.ok is False
    assert outcome.result.text_fallback, "Der Text-Fallback muss mitkommen"

    from mealplan.db.models import SyncRun

    run = session.get(SyncRun, outcome.run_id)
    assert run.status == SyncStatus.FAILED.value
    assert "502" in run.error
    assert service.last_run(session, SyncKind.BRING_PUSH) is None


def test_state_is_remembered_per_article(session):
    bring = FakeBring()
    service.push(session, ISO, bring)
    session.commit()

    state = service.load_state(session)
    assert state.list_uuid == "list-1"
    assert state.items
    assert all(item.item_uuid for item in state.items)
