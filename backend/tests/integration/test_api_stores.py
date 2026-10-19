"""Läden und der Knopf "Angebote abrufen" (Phase 2, Stufe 1)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from mealplan.ports import OfferSnapshotData, RawOffer, StoreRef

REWE = {
    "name": "Rewe Heinrichstraße",
    "chain": "REWE",
    "postal_code": "49080",
    "market_id": "241090",
    "offers_enabled": True,
}
ALLFRISCH = {"name": "Allfrisch Lotter Straße", "chain": "EDEKA", "is_primary": True}


class FakeSource:
    """Statt Korbunio: liefert pro Laden zwei Angebote, die bis Sonntag gelten."""

    name = "fake"

    def __init__(self) -> None:
        self.asked: list[StoreRef] = []

    def fetch(self, store: StoreRef) -> OfferSnapshotData:
        self.asked.append(store)
        until = date.today() + timedelta(days=6)
        return OfferSnapshotData(
            store_id=store.id,
            source=self.name,
            fetched_at=datetime.now().astimezone(),
            offers=(
                RawOffer("Jeden Tag Hirtenkäse", price=Decimal("1.49"), pack="250 g",
                         valid_to=until),
                RawOffer("Datteltomaten", price=Decimal("1.11"), valid_to=until),
            ),
            ok=True,
            market_label="REWE - Heinrichstr. 37, 49080 Osnabrück",
        )


def test_stores_are_created_listed_and_the_primary_comes_first(client):
    rewe = client.post("/api/stores", json=REWE)
    assert rewe.status_code == 201, rewe.text
    assert rewe.json() | {"id": 0} == REWE | {"id": 0, "is_primary": False}
    client.post("/api/stores", json=ALLFRISCH)

    names = [s["name"] for s in client.get("/api/stores").json()]
    assert names == ["Allfrisch Lotter Straße", "Rewe Heinrichstraße"]


def test_there_is_only_one_primary_store(client):
    first = client.post("/api/stores", json=ALLFRISCH).json()
    second = client.post("/api/stores", json=REWE).json()
    client.patch(f"/api/stores/{second['id']}", json={"is_primary": True})

    by_id = {s["id"]: s for s in client.get("/api/stores").json()}
    assert by_id[second["id"]]["is_primary"] is True
    assert by_id[first["id"]]["is_primary"] is False


def test_store_input_is_checked(client):
    cases = [
        (REWE | {"postal_code": "4908"}, "fünf Ziffern"),
        (REWE | {"market_id": "abc"}, "nur aus Ziffern"),
        (REWE | {"postal_code": None}, "braucht der Laden eine PLZ"),
    ]
    for payload, message in cases:
        response = client.post("/api/stores", json=payload)
        assert response.status_code == 422, payload
        assert message in response.json()["detail"]

    client.post("/api/stores", json=REWE)
    taken = client.post("/api/stores", json=REWE | {"name": "rewe heinrichstraße"})
    assert taken.status_code == 422
    assert "gibt es schon" in taken.json()["detail"]


def test_a_store_can_be_changed_and_its_market_cleared(client):
    rewe = client.post("/api/stores", json=REWE).json()
    changed = client.patch(
        f"/api/stores/{rewe['id']}", json={"market_id": "", "offers_enabled": False}
    ).json()
    assert changed["market_id"] is None
    assert changed["offers_enabled"] is False
    assert changed["postal_code"] == "49080", "nicht genannte Felder bleiben"

    cleared = client.patch(f"/api/stores/{rewe['id']}", json={"postal_code": ""})
    assert cleared.status_code == 200
    without_plz = client.patch(f"/api/stores/{rewe['id']}", json={"offers_enabled": True})
    assert without_plz.status_code == 422


def test_deleting_a_store_takes_its_offers_along(client):
    source = FakeSource()
    client.app.state.offer_source = source
    rewe = client.post("/api/stores", json=REWE).json()
    client.post("/api/offers/fetch")
    assert client.get("/api/offers").json()

    assert client.delete(f"/api/stores/{rewe['id']}").status_code == 204
    assert client.get("/api/stores").json() == []
    assert client.get("/api/offers").json() == []


def test_fetching_asks_only_stores_with_offers(client):
    source = FakeSource()
    client.app.state.offer_source = source
    client.post("/api/stores", json=REWE)
    client.post("/api/stores", json=ALLFRISCH)

    response = client.post("/api/offers/fetch")
    assert response.status_code == 200, response.text
    assert [s.postal_code for s in source.asked] == ["49080"]
    assert source.asked[0].market_id == "241090"

    [status] = response.json()
    assert status["store_name"] == "Rewe Heinrichstraße"
    assert status["last_status"] == "OK"
    assert status["current_count"] == 2
    assert status["market_label"] == "REWE - Heinrichstr. 37, 49080 Osnabrück"
    assert client.get("/api/offers/status").json() == response.json()


def test_offers_carry_store_pack_and_whether_the_match_is_confirmed(client):
    client.app.state.offer_source = FakeSource()
    client.post("/api/stores", json=REWE)
    client.post("/api/offers/fetch")

    offers = {o["raw_name"]: o for o in client.get("/api/offers").json()}
    cheese = offers["Jeden Tag Hirtenkäse"]
    assert cheese["store_name"] == "Rewe Heinrichstraße"
    assert cheese["pack"] == "250 g"
    assert cheese["match_confirmed"] is False


def test_fetching_explains_what_is_missing(client):
    client.app.state.offer_source = None
    client.post("/api/stores", json=REWE)
    no_source = client.post("/api/offers/fetch")
    assert no_source.status_code == 422
    assert "Angebotsquelle" in no_source.json()["detail"]

    client.app.state.offer_source = FakeSource()
    rewe_id = client.get("/api/stores").json()[0]["id"]
    client.patch(f"/api/stores/{rewe_id}", json={"offers_enabled": False})
    no_store = client.post("/api/offers/fetch")
    assert no_store.status_code == 422
    assert "Laden mit Angeboten" in no_store.json()["detail"]
