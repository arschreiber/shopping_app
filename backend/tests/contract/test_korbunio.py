"""Korbunio-Vertrag mit respx-Cassettes (ARCHITECTURE.md §9).

Zweck laut Plan §8 Nr. 2: ein Schema-Bruch soll ein roter Test sein, keine
Montag-frueh-Ueberraschung. Und ein fehlgeschlagener Abruf darf die Angebotsansicht
nie leeren.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mealplan.db import models as m
from mealplan.db import session as session_module
from mealplan.db.models import Base
from mealplan.domain.enums import Chain, SyncStatus
from mealplan.integrations.offers.korbunio import KorbunioOfferSource
from mealplan.services import offers as service

BASE = "http://korbunio:8000"
PAYLOAD = {
    "results": [
        {
            "name": "Lachsfilet frisch",
            "price": "4.99",
            "oldPrice": "7.49",
            "brand": "Gut & Günstig",
            "validFrom": "2026-09-07",
            "validTo": "2026-09-12",
            "basePrice": "24,95 €/kg",
        },
        {"name": "Hirtenkäse 200g", "price": "1.49", "oldPrice": "1.99"},
        {"name": "Bio-Zucchini", "price": "0.99"},
    ]
}


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'offers.sqlite3'}")
    Base.metadata.create_all(engine)
    session_module.set_engine(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        from mealplan.cli.demo import seed

        seed(db)
        db.add(
            m.Store(
                name="Allfrisch",
                chain=Chain.EDEKA.value,
                market_id="30159",
                offer_source="korbunio",
                is_primary=True,
            )
        )
        db.commit()
        yield db
    engine.dispose()


@respx.mock
def test_fetch_maps_the_documented_shape(session):
    respx.post(f"{BASE}/api/v1/compare").mock(
        return_value=httpx.Response(200, json=PAYLOAD)
    )
    source = KorbunioOfferSource(BASE)
    data = source.fetch(store_id=1, market_id="30159", queries=["Lachs"])

    assert data.ok and data.usable
    assert len(data.offers) == 3
    first = data.offers[0]
    assert first.raw_name == "Lachsfilet frisch"
    assert str(first.price) == "4.99"
    assert str(first.old_price) == "7.49"
    assert first.valid_to.isoformat() == "2026-09-12"
    assert data.raw_payload is not None, "raw_payload ermoeglicht Reprocessing"


@respx.mock
def test_unknown_shape_is_not_a_crash(session):
    """Endpunkte ändern sich still - dann gibt es 0 Treffer, keinen Traceback."""
    respx.post(f"{BASE}/api/v1/compare").mock(
        return_value=httpx.Response(200, json={"unexpected": "format"})
    )
    data = KorbunioOfferSource(BASE).fetch(1, "30159", ["Lachs"])
    assert data.ok
    assert not data.usable  # ok, aber keine Treffer -> kein OK-Snapshot


@respx.mock
def test_http_error_is_reported_not_raised(session):
    respx.post(f"{BASE}/api/v1/compare").mock(return_value=httpx.Response(403))
    data = KorbunioOfferSource(BASE).fetch(1, "30159", ["Lachs"])
    assert data.ok is False
    assert "403" in data.error


@respx.mock
def test_a_failed_fetch_never_empties_the_offer_view(session):
    """Plan §8 Nr. 2: der letzte gute Snapshot bleibt der, den die App liest."""
    respx.post(f"{BASE}/api/v1/compare").mock(
        return_value=httpx.Response(200, json=PAYLOAD)
    )
    source = KorbunioOfferSource(BASE)
    service.fetch_all(session, source)
    session.commit()
    good = service.current_offers(session)
    assert len(good) == 3

    respx.post(f"{BASE}/api/v1/compare").mock(return_value=httpx.Response(500))
    service.fetch_all(session, source)
    session.commit()

    assert len(service.current_offers(session)) == 3, "Angebote dürfen nicht verschwinden"
    runs = [r for r in session.query(m.SyncRun).all() if r.status != SyncStatus.OK.value]
    assert runs, "Der Fehlschlag muss in der Historie stehen"


@respx.mock
def test_offers_are_matched_to_articles(session):
    """Fuzzy-Matching gegen die Alias-Liste (general_plan.md §8 Nr. 4)."""
    respx.post(f"{BASE}/api/v1/compare").mock(
        return_value=httpx.Response(200, json=PAYLOAD)
    )
    service.fetch_all(session, KorbunioOfferSource(BASE))
    session.commit()

    by_name = {view.raw_name: view for view in service.current_offers(session)}
    assert by_name["Lachsfilet frisch"].article_name == "Lachsfilet"
    assert by_name["Hirtenkäse 200g"].article_name == "Hirtenkäse"


@respx.mock
def test_unmatched_offers_are_listed_for_one_click_mapping(session):
    respx.post(f"{BASE}/api/v1/compare").mock(
        return_value=httpx.Response(
            200, json={"results": [{"name": "Wildlachs-Terrine", "price": "3.99"}]}
        )
    )
    service.fetch_all(session, KorbunioOfferSource(BASE))
    session.commit()

    open_items = service.unmatched(session)
    assert [view.raw_name for view in open_items] == ["Wildlachs-Terrine"]

    from mealplan.services.matching import confirm

    salmon = session.query(m.Article).filter_by(canonical_name="Lachsfilet").one()
    confirm(session, offer_name="Wildlachs-Terrine", store_id=1, article_id=salmon.id)
    session.commit()
    assert not service.unmatched(session)


@respx.mock
def test_offer_savings_reach_the_planner_score(session):
    """Angebots-Bonus im Ranking (general_plan.md §4)."""
    respx.post(f"{BASE}/api/v1/compare").mock(
        return_value=httpx.Response(200, json=PAYLOAD)
    )
    service.fetch_all(session, KorbunioOfferSource(BASE))
    session.commit()

    savings = service.savings_by_dish(session, week=None)  # type: ignore[arg-type]
    assert savings, "Gerichte mit Lachs oder Hirtenkäse müssen einen Bonus bekommen"
    assert all(value > 0 for value in savings.values())
