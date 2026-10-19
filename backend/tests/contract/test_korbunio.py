"""Korbunio-Vertrag gegen eine *echte* Antwort (ARCHITECTURE.md §9).

Die Cassette ist ein Ausschnitt aus dem Abruf vom 5.10.2026 (Korbunio 0.1.57, PLZ
49078), ohne Links und Tokens. Zweck laut Plan §8 Nr. 2: ein Schema-Bruch soll ein roter
Test sein, keine Montag-früh-Überraschung. Und ein fehlgeschlagener Abruf darf die
Angebotsansicht nie leeren.
"""

from __future__ import annotations

import copy
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

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
from mealplan.ports import StoreRef
from mealplan.services import offers as service
from mealplan.services.articles import ValidationError

BASE = "http://korbunio:8000"
COMPARE = f"{BASE}/api/v1/compare"
PAGE = json.loads((Path(__file__).parent / "cassettes" / "korbunio_compare_49078.json").read_text())
REWE = StoreRef(id=1, chain=Chain.REWE.value, postal_code="49080", market_id="241090")
COMBI = StoreRef(id=2, chain=Chain.COMBI.value, postal_code="49078")
DURING = date(2026, 10, 7)  # Mittwoch der Prospektwoche


def page(**changes) -> dict:
    out = copy.deepcopy(PAGE)
    out.update(changes)
    return out


def row_chain(row: dict) -> str:
    return {"REWE": Chain.REWE, "Combi": Chain.COMBI}[row["retailer"]].value


@pytest.fixture(autouse=True)
def during_the_brochure_week(monkeypatch):
    """"Heute" ist die Prospektwoche der Cassette - sonst wäre alles längst abgelaufen."""

    class _Date(date):
        @classmethod
        def today(cls):
            return DURING

    monkeypatch.setattr(service, "date", _Date)


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'offers.sqlite3'}")
    Base.metadata.create_all(engine)
    session_module.set_engine(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        from mealplan.cli.demo import seed

        seed(db)
        db.add_all([
            m.Store(id=1, name="Rewe Heinrichstraße", chain=Chain.REWE.value,
                    postal_code="49080", market_id="241090", offer_source="korbunio"),
            m.Store(id=2, name="Combi Natruper Straße", chain=Chain.COMBI.value,
                    postal_code="49078", offer_source="korbunio"),
            # Hauptladen ohne Angebote: Allfrisch veröffentlicht sie nur in der Edeka-App
            m.Store(id=3, name="Allfrisch", chain=Chain.EDEKA.value, postal_code="49078",
                    is_primary=True),
        ])
        db.commit()
        yield db
    engine.dispose()


def _fetch(session, today=DURING):
    service.fetch_all(session, KorbunioOfferSource(BASE))
    session.commit()
    return {view.raw_name: view for view in service.current_offers(session, today=today)}


# ----------------------------------------------------------------------------- Adapter


@respx.mock
def test_asks_for_the_whole_brochure_of_exactly_this_market():
    route = respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    KorbunioOfferSource(BASE).fetch(REWE)

    sent = json.loads(route.calls[0].request.content)
    assert sent["postal_code"] == "49080"
    assert sent["retailers"] == ["REWE"]
    assert sent["rewe_market_id"] == "241090", "sonst nimmt Korbunio irgendeinen Rewe"
    assert "keywords" not in sent, "ganzer Prospekt - zugeordnet wird bei uns"
    assert sent["view"] == "all" and sent["page"] == 1
    assert sent["include_image_urls"] is True, "Bilder zum Nachprüfen eines Angebots"


@respx.mock
def test_maps_the_real_shape():
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    data = KorbunioOfferSource(BASE).fetch(REWE)

    assert data.ok and data.usable
    assert {o.raw_name for o in data.offers} == {
        "Mini Roma Rispentomaten", "Reis-Fit Expressreis", "Bonduelle Goldmais",
    }, "nur die Angebote der gefragten Kette"
    tomatoes = next(o for o in data.offers if o.raw_name == "Mini Roma Rispentomaten")
    assert tomatoes.price == Decimal("2.39")
    assert tomatoes.old_price is None, "regulär = Angebotspreis heißt: kein 'statt'-Preis"
    assert tomatoes.pack == "250 g"
    assert tomatoes.base_price and "€/kg" in tomatoes.base_price
    assert (tomatoes.valid_from, tomatoes.valid_to) == (date(2026, 10, 5), date(2026, 10, 11))
    assert data.market_label == "REWE - Lengericher Landstr. 2, 49078 Osnabrück"
    assert "result_url" not in data.raw_payload["pages"][0], "keine signierten Links speichern"


@respx.mock
def test_brings_what_it_takes_to_check_an_offer():
    """Prospekttext, Bild, Angebotsseite des Markts, Art der Quelle."""
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    data = KorbunioOfferSource(BASE).fetch(REWE)

    tomatoes = next(o for o in data.offers if o.raw_name == "Mini Roma Rispentomaten")
    assert tomatoes.description.startswith("»Aromatica«, Kl. I")
    assert tomatoes.image_url.startswith("https://img.rewe-static.de/")
    assert tomatoes.source_url is None, "leere Links werden nicht zu Links"
    assert data.market_url == "https://www.rewe.de/angebote/osnabrueck/541741/rewe-lengericher-landstr-2/"
    assert data.source_detail == "offiziell"


ALDI = StoreRef(id=5, chain=Chain.ALDI_NORD.value, postal_code="49080")
AVOCADOS = {  # so kam die Zeile am 13.10.2026 (Korbunio 0.1.57)
    **PAGE["offers"][0],
    "retailer": "ALDI Nord", "product": "Avocados", "brand": "", "category": "Obst & Gemüse",
    "description": "Genussreif, Ready to Enjoy; Klasse 1; Ursprung siehe Etikett · 2er-Schale",
    "regular_price": 1.29, "checkout_price": 1.29, "effective_price": 1.29,
    "pack": "", "unit_price": "",
}


@respx.mock
def test_aldi_keeps_the_pack_at_the_end_of_the_text():
    rows = [AVOCADOS, {**AVOCADOS, "product": "Kohlrabi", "description": "Klasse 1 · Stück"},
            {**AVOCADOS, "product": "Puzzle", "description": "Ab 3 Jahren; verschiedene Motive"}]
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page(offers=rows)))
    packs = {o.raw_name: o.pack for o in KorbunioOfferSource(BASE).fetch(ALDI).offers}
    assert packs == {"Avocados": "2er-Schale", "Kohlrabi": "Stück", "Puzzle": None}


@respx.mock
def test_validity_is_read_from_the_text_when_the_dates_are_missing():
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    data = KorbunioOfferSource(BASE).fetch(COMBI)

    cheese = next(o for o in data.offers if o.raw_name == "Jeden Tag Hirtenkäse")
    assert (cheese.valid_from, cheese.valid_to) == (date(2026, 10, 5), date(2026, 10, 10))
    assert data.market_label is None, "marktguru: regionaler Prospekt, kein Markt"


@respx.mock
def test_without_any_validity_an_offer_runs_until_saturday():
    row = copy.deepcopy(PAGE["offers"][0]) | {"validity": "", "valid_until": None}
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page(offers=[row])))
    data = KorbunioOfferSource(BASE).fetch(StoreRef(1, row_chain(row), "49078"))

    today = date.today()
    assert data.offers[0].valid_to.weekday() == 5
    assert 0 <= (data.offers[0].valid_to - today).days <= 6


@respx.mock
def test_only_a_higher_regular_price_is_an_old_price():
    row = next(o for o in PAGE["offers"] if o["retailer"] == "Combi")
    row = copy.deepcopy(row) | {"regular_price": 1.99, "checkout_price": 1.49}
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page(offers=[row])))
    offer = KorbunioOfferSource(BASE).fetch(COMBI).offers[0]
    assert (offer.price, offer.old_price) == (Decimal("1.49"), Decimal("1.99"))


@respx.mock
def test_all_pages_are_read():
    first = page(has_next=True, offers=PAGE["offers"][:3])
    second = page(has_next=False, page=2, offers=PAGE["offers"][3:])
    route = respx.post(COMPARE).mock(
        side_effect=[httpx.Response(200, json=first), httpx.Response(200, json=second)]
    )
    data = KorbunioOfferSource(BASE).fetch(COMBI)

    assert [json.loads(c.request.content)["page"] for c in route.calls] == [1, 2]
    assert len(data.offers) == 4, "alle Combi-Angebote beider Seiten"


@respx.mock
def test_an_unknown_shape_is_reported_not_raised():
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json={"unexpected": "format"}))
    data = KorbunioOfferSource(BASE).fetch(REWE)
    assert data.ok is False
    assert "Antwortformat" in data.error


@respx.mock
def test_http_errors_carry_korbunios_reason():
    respx.post(COMPARE).mock(
        return_value=httpx.Response(
            400, json={"detail": "Der gewählte REWE-Markt gehört nicht zur PLZ 49078"}
        )
    )
    data = KorbunioOfferSource(BASE).fetch(REWE)
    assert data.ok is False
    assert data.error == (
        "Korbunio antwortet 400: Der gewählte REWE-Markt gehört nicht zur PLZ 49078"
    )


@respx.mock
def test_a_missing_container_says_so():
    respx.post(COMPARE).mock(side_effect=httpx.ConnectError("refused"))
    data = KorbunioOfferSource(BASE).fetch(REWE)
    assert data.ok is False
    assert "Container" in data.error


@respx.mock
def test_an_empty_brochure_explains_why():
    respx.post(COMPARE).mock(
        return_value=httpx.Response(
            200,
            json=page(offers=[], warnings=["REWE: Quelle derzeit nicht erreichbar"]),
        )
    )
    data = KorbunioOfferSource(BASE).fetch(REWE)
    assert data.ok and not data.usable
    assert data.error == "REWE: Quelle derzeit nicht erreichbar"


# ---------------------------------------------------------------------------- Service


@respx.mock
def test_only_stores_with_offers_are_fetched(session):
    route = respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    _fetch(session)

    asked = sorted(json.loads(c.request.content)["retailers"][0] for c in route.calls)
    assert asked == ["Combi", "REWE"], "Allfrisch hat keine Angebote - nicht abfragen"


@respx.mock
def test_a_failed_fetch_never_empties_the_offer_view(session):
    """Plan §8 Nr. 2: der letzte gute Snapshot bleibt der, den die App liest."""
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    assert len(_fetch(session)) == 7

    respx.post(COMPARE).mock(return_value=httpx.Response(500))
    assert len(_fetch(session)) == 7, "Angebote dürfen nicht verschwinden"

    run = session.query(m.SyncRun).order_by(m.SyncRun.id.desc()).first()
    assert run.status == SyncStatus.FAILED.value
    assert "Rewe Heinrichstraße: Korbunio antwortet 500" in run.error
    status = {s.store_name: s for s in service.store_status(session, today=DURING)}
    assert status["Rewe Heinrichstraße"].last_status is SyncStatus.FAILED
    assert status["Rewe Heinrichstraße"].current_count == 3, "die alten gelten weiter"


@respx.mock
def test_offers_with_the_same_name_in_one_brochure_are_no_problem(session):
    """Gefunden im ersten echten Abruf: Combi führt "Küstengold Mineralwasser" in zwei
    Sorten - normalisiert derselbe Name, und der Abruf brach am UNIQUE-Index ab."""
    row = next(o for o in PAGE["offers"] if o["retailer"] == "Combi")
    twins = [copy.deepcopy(row) | {"description": sort} for sort in ("medium", "still")]
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page(offers=twins)))

    _fetch(session)
    assert len(service.current_offers(session, today=DURING)) == 2


@respx.mock
def test_expired_offers_disappear(session):
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    _fetch(session)

    sunday = {v.store_name for v in service.current_offers(session, today=date(2026, 10, 11))}
    assert sunday == {"Rewe Heinrichstraße"}, "Combi bis Sa, Rewe bis So"
    assert not service.current_offers(session, today=date(2026, 10, 12))


@respx.mock
def test_old_fetches_are_cleaned_up_but_the_last_good_one_stays(session):
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    _fetch(session)
    respx.post(COMPARE).mock(return_value=httpx.Response(500))
    for _ in range(service.KEEP_SNAPSHOTS + 2):
        _fetch(session)

    rewe = session.query(m.OfferSnapshot).filter_by(store_id=1).all()
    assert len(rewe) == service.KEEP_SNAPSHOTS + 1, "6 neueste + der letzte gute"
    assert service.latest_snapshot(session, 1) is not None


@respx.mock
def test_offers_are_matched_to_articles(session):
    """Fuzzy-Matching gegen die Alias-Liste (general_plan.md §8 Nr. 4)."""
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    offers = _fetch(session)

    assert offers["Jeden Tag Hirtenkäse"].article_name == "Hirtenkäse"
    assert offers["Jeden Tag Hirtenkäse"].match_confirmed is False


@respx.mock
def test_only_confirmed_matches_reach_the_list_and_the_planner(session):
    """Die automatische Zuordnung hält gefüllte Paprika für Paprika - auf die Liste und
    in den Planer kommt erst, was jemand bestätigt hat."""
    rows = copy.deepcopy(PAGE["offers"])
    for row in rows:
        if row["product"] == "Jeden Tag Hirtenkäse":
            row["regular_price"] = 1.99  # mit "statt"-Preis, damit es einen Bonus gäbe
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page(offers=rows)))
    offers = _fetch(session)
    cheese = session.query(m.Article).filter_by(canonical_name="Hirtenkäse").one()
    assert offers["Jeden Tag Hirtenkäse"].article_id == cheese.id, "automatisch zugeordnet"

    assert service.offer_hints(session, [cheese.id]) == {}
    assert service.savings_by_dish(session, week=None) == {}  # type: ignore[arg-type]

    from mealplan.services.matching import confirm

    confirm(session, offer_name="Jeden Tag Hirtenkäse", store_id=2, article_id=cheese.id)
    session.commit()
    assert "Combi Natruper Straße 1,49 €" in service.offer_hints(session, [cheese.id])[cheese.id]
    assert service.savings_by_dish(session, week=None)  # type: ignore[arg-type]


@respx.mock
def test_the_unit_price_is_stored_comparable(session):
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    offers = _fetch(session)

    cheese = offers["Jeden Tag Hirtenkäse"]
    assert (cheese.unit_price, cheese.unit_price_unit) == (Decimal("5.96"), "kg")
    beer = offers["Maisel & Friends Pale Ale"]
    assert (beer.unit_price, beer.unit_price_unit) == (Decimal("3.03"), "l")
    assert cheese.market_url is None and cheese.source_detail == "Marktguru"


@respx.mock
def test_avocados_by_the_piece_are_compared_through_the_piece_size(session):
    """1,29 € für die 2er-Schale, 1 Avocado ≈ 150 g -> 0,65 €/Stück ≈ 4,33 €/kg."""
    session.add_all([
        m.Store(id=5, name="Aldi Martinistraße", chain=Chain.ALDI_NORD.value,
                postal_code="49080", offer_source="korbunio"),
        m.Article(canonical_name="Avocado", unit="G", piece_size=Decimal("150"),
                  max_unit_price=Decimal("9.00")),
    ])
    session.commit()
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page(offers=[AVOCADOS])))
    avocados = _fetch(session)["Avocados"]

    assert (avocados.unit_price, avocados.unit_price_unit) == (Decimal("0.65"), "Stück")
    assert avocados.article_name == "Avocado"
    assert (avocados.compared_price, avocados.compared_via_piece) == (Decimal("4.33"), True)
    assert avocados.price_verdict == "ok"


def _set_target(session, name: str, value: str | None) -> m.Article:
    article = session.query(m.Article).filter_by(canonical_name=name).one()
    article.max_unit_price = Decimal(value) if value is not None else None
    session.commit()
    return article


@respx.mock
def test_a_target_price_decides_whether_an_offer_counts(session):
    """Hirtenkäse für 5,96 €/kg: bei Richtpreis 5 € zu teuer, bei 6 € gut, ohne egal."""
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    _fetch(session)

    def cheese():
        views = service.current_offers(session, today=DURING)
        return next(v for v in views if v.raw_name == "Jeden Tag Hirtenkäse")

    _set_target(session, "Hirtenkäse", "5.00")
    assert (cheese().price_verdict, cheese().counts) == ("too_expensive", False)
    assert cheese().article_name == "Hirtenkäse", "die Zuordnung bleibt sichtbar"
    _set_target(session, "Hirtenkäse", "6.00")
    assert (cheese().price_verdict, cheese().counts) == ("ok", True)
    _set_target(session, "Hirtenkäse", None)
    assert (cheese().price_verdict, cheese().counts) == (None, True)


@respx.mock
def test_a_price_that_cannot_be_compared_never_beats_the_target(session):
    """Paprika wird in Stück geführt, die gefüllte Paprika kostet 8,90 €/kg."""
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    _fetch(session)
    _set_target(session, "Paprika", "0.80")

    views = service.current_offers(session, today=DURING)
    stuffed = next(v for v in views if v.raw_name == "Goldmarie Gefüllte Paprika")
    assert stuffed.article_name == "Paprika"
    assert (stuffed.price_verdict, stuffed.counts) == ("unknown", False)


@respx.mock
def test_only_offers_within_the_target_reach_the_list(session):
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    _fetch(session)
    from mealplan.services.matching import confirm

    cheese = _set_target(session, "Hirtenkäse", "5.00")
    confirm(session, offer_name="Jeden Tag Hirtenkäse", store_id=2, article_id=cheese.id)
    session.commit()
    assert service.offer_hints(session, [cheese.id]) == {}, "bestätigt, aber zu teuer"

    _set_target(session, "Hirtenkäse", "6.00")
    assert cheese.id in service.offer_hints(session, [cheese.id])


@respx.mock
def test_a_pack_below_the_minimum_never_reaches_the_list(session):
    """Hirtenkäse 250 g: bestätigt, aber erst ab 400 g gewünscht - kein Hinweis."""
    respx.post(COMPARE).mock(return_value=httpx.Response(200, json=page()))
    _fetch(session)
    from mealplan.services.matching import confirm

    cheese = session.query(m.Article).filter_by(canonical_name="Hirtenkäse").one()
    cheese.min_offer_amount = Decimal("400")
    confirm(session, offer_name="Jeden Tag Hirtenkäse", store_id=2, article_id=cheese.id)
    session.commit()
    assert service.offer_hints(session, [cheese.id]) == {}

    cheese.min_offer_amount = Decimal("250")
    session.commit()
    assert cheese.id in service.offer_hints(session, [cheese.id])


def test_a_second_fetch_while_one_runs_is_refused(session):
    with service._FETCH_LOCK, pytest.raises(ValidationError, match="schon abgerufen"):
        service.fetch_all(session, KorbunioOfferSource(BASE))
