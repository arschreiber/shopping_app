"""Richtpreis pro Artikel und das Nachprüfen eines Angebots - über die API."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from mealplan.ports import OfferSnapshotData, RawOffer, StoreRef


class FakeSource:
    name = "fake"

    def __init__(self, extra: tuple[RawOffer, ...] = ()) -> None:
        self.extra = extra

    def fetch(self, store: StoreRef) -> OfferSnapshotData:
        until = date.today() + timedelta(days=6)
        return OfferSnapshotData(
            store_id=store.id,
            source=self.name,
            fetched_at=datetime.now().astimezone(),
            offers=(
                *self.extra,
                RawOffer(
                    "Jeden Tag Hirtenkäse",
                    price=Decimal("1.49"),
                    base_price="5,96 €/kg",
                    pack="250 g",
                    valid_to=until,
                    description="aus Kuhmilch 250g",
                    image_url="https://mg2de.b-cdn.net/api/v1/offers/1/images/default/0/medium",
                ),
            ),
            ok=True,
            market_url="https://www.rewe.de/angebote/osnabrueck/241090/rewe-heinrichstr-37/",
            source_detail="offiziell",
            market_label="REWE - Heinrichstr. 37, 49080 Osnabrück",
        )


def _article(client, name: str) -> dict:
    return next(a for a in client.get("/api/articles").json() if a["canonical_name"] == name)


def _fetch(client, *extra: RawOffer) -> dict:
    client.app.state.offer_source = FakeSource(extra)
    client.post(
        "/api/stores",
        json={"name": "Rewe", "chain": "REWE", "postal_code": "49080", "offers_enabled": True},
    )
    assert client.post("/api/offers/fetch").status_code == 200
    return {o["raw_name"]: o for o in client.get("/api/offers").json()}


def test_a_target_price_can_be_set_and_cleared(client, seeded):
    cheese = _article(client, "Hirtenkäse")
    assert cheese["max_unit_price"] is None

    set_ = client.patch(f"/api/articles/{cheese['id']}", json={"max_unit_price": "6.50"})
    assert set_.status_code == 200, set_.text
    assert Decimal(set_.json()["max_unit_price"]) == Decimal("6.50")

    other = client.patch(f"/api/articles/{cheese['id']}", json={"is_watchlist": True})
    assert Decimal(other.json()["max_unit_price"]) == Decimal("6.50"), "bleibt beim Ändern"

    cleared = client.patch(f"/api/articles/{cheese['id']}", json={"max_unit_price": None})
    assert cleared.json()["max_unit_price"] is None

    zero = client.patch(f"/api/articles/{cheese['id']}", json={"max_unit_price": "0"})
    assert zero.status_code == 422


def test_an_offer_carries_what_it_takes_to_check_it(client, seeded):
    cheese = _fetch(client)["Jeden Tag Hirtenkäse"]

    assert cheese["description"] == "aus Kuhmilch 250g"
    assert cheese["image_url"].startswith("https://mg2de.b-cdn.net/")
    assert cheese["market_url"].endswith("/rewe-heinrichstr-37/")
    assert cheese["source_detail"] == "offiziell"
    assert cheese["fetched_at"] is not None
    assert (Decimal(cheese["unit_price"]), cheese["unit_price_unit"]) == (Decimal("5.96"), "kg")


def test_the_offer_list_judges_against_the_target_price(client, seeded):
    cheese_id = _article(client, "Hirtenkäse")["id"]
    client.patch(f"/api/articles/{cheese_id}", json={"max_unit_price": "5.00"})

    offer = _fetch(client)["Jeden Tag Hirtenkäse"]
    assert offer["article_name"] == "Hirtenkäse"
    assert Decimal(offer["target_price"]) == Decimal("5.00")
    assert offer["price_verdict"] == "too_expensive"
    assert offer["counts"] is False

    client.patch(f"/api/articles/{cheese_id}", json={"max_unit_price": "6.00"})
    offer = next(o for o in client.get("/api/offers").json() if o["offer_id"] == offer["offer_id"])
    assert (offer["price_verdict"], offer["counts"]) == ("ok", True)


def test_merging_keeps_a_target_price(client, seeded):
    cheese = _article(client, "Hirtenkäse")
    feta = _article(client, "Feta")
    client.patch(f"/api/articles/{feta['id']}", json={"max_unit_price": "9.00"})

    merged = client.post(f"/api/articles/{cheese['id']}/merge", json={"source_ids": [feta["id"]]})
    assert merged.status_code == 200, merged.text
    assert Decimal(merged.json()["max_unit_price"]) == Decimal("9.00")


def test_the_normal_price_is_entered_like_you_buy_it(client, seeded):
    """ "250 g für 1,29 €" - die App rechnet den Grundpreis selbst."""
    cheese = _article(client, "Hirtenkäse")
    saved = client.patch(
        f"/api/articles/{cheese['id']}",
        json={"regular_pack_amount": "250", "regular_pack_price": "1.29"},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert (Decimal(body["regular_pack_amount"]), Decimal(body["regular_pack_price"])) == (
        Decimal("250"),
        Decimal("1.29"),
    )
    assert Decimal(body["regular_unit_price"]) == Decimal("5.16")

    cheaper = client.patch(f"/api/articles/{cheese['id']}", json={"regular_pack_price": "1.19"})
    assert Decimal(cheaper.json()["regular_unit_price"]) == Decimal("4.76"), "nur der Preis neu"

    cleared = client.patch(
        f"/api/articles/{cheese['id']}",
        json={"regular_pack_amount": None, "regular_pack_price": None},
    )
    assert cleared.json()["regular_unit_price"] is None


def test_a_normal_price_needs_amount_and_price(client, seeded):
    cheese = _article(client, "Hirtenkäse")
    half = client.patch(f"/api/articles/{cheese['id']}", json={"regular_pack_price": "1.29"})
    assert half.status_code == 422
    assert "braucht Menge und Preis" in half.json()["detail"]

    client.patch(
        f"/api/articles/{cheese['id']}",
        json={"regular_pack_amount": "250", "regular_pack_price": "1.29"},
    )
    only_amount_gone = client.patch(
        f"/api/articles/{cheese['id']}", json={"regular_pack_amount": None}
    )
    assert only_amount_gone.status_code == 422


def test_an_offer_shows_how_far_it_is_from_the_normal_price(client, seeded):
    """Markenkäse für 5,96 €/kg, die Eigenmarke kostet normal 5,16 €/kg: 0,80 € teurer -
    und mit Richtpreis 7 € zählt das Angebot trotzdem, weil hier die Qualität zählt."""
    cheese_id = _article(client, "Hirtenkäse")["id"]
    client.patch(
        f"/api/articles/{cheese_id}",
        json={"regular_pack_amount": "250", "regular_pack_price": "1.29", "max_unit_price": "7"},
    )

    offer = _fetch(client)["Jeden Tag Hirtenkäse"]
    assert Decimal(offer["regular_unit_price"]) == Decimal("5.16")
    assert offer["article_price_unit"] == "kg"
    assert Decimal(offer["normal_diff"]) == Decimal("0.80")
    assert offer["normal_diff_percent"] == 16
    assert (offer["price_verdict"], offer["counts"]) == ("ok", True)


def test_merging_keeps_a_normal_price(client, seeded):
    cheese = _article(client, "Hirtenkäse")
    feta = _article(client, "Feta")
    client.patch(
        f"/api/articles/{feta['id']}",
        json={"regular_pack_amount": "200", "regular_pack_price": "1.49"},
    )
    merged = client.post(
        f"/api/articles/{cheese['id']}/merge", json={"source_ids": [feta["id"]]}
    ).json()
    assert Decimal(merged["regular_unit_price"]) == Decimal("7.45")


AVOCADO = RawOffer(
    "Avocado",
    price=Decimal("0.99"),
    base_price="0,99 €/Stück",
    valid_to=date.today() + timedelta(days=6),
)


def _avocado(client, **fields) -> dict:
    response = client.post(
        "/api/articles", json={"canonical_name": "Avocado", "unit": "G", **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_piece_offer_compares_through_the_piece_size(client, seeded):
    """Avocado 0,99 €/Stück, 1 Stück ≈ 200 g -> 4,95 €/kg; normal 1 Stück für 0,79 €."""
    avocado = _avocado(
        client,
        piece_size="200",
        max_unit_price="5.00",
        regular_pack_amount="1",
        regular_pack_price="0.79",
        regular_pack_unit="STUECK",
    )
    assert Decimal(avocado["regular_unit_price"]) == Decimal("3.95")

    offer = _fetch(client, AVOCADO)["Avocado"]
    assert offer["article_name"] == "Avocado"
    assert (Decimal(offer["compared_price"]), offer["compared_via_piece"]) == (
        Decimal("4.95"),
        True,
    )
    assert (offer["price_verdict"], offer["counts"]) == ("ok", True)
    assert Decimal(offer["normal_diff"]) == Decimal("1.00")
    assert offer["normal_diff_percent"] == 25


def test_without_a_piece_size_a_piece_offer_stays_open(client, seeded):
    _avocado(client, max_unit_price="5.00")
    offer = _fetch(client, AVOCADO)["Avocado"]
    assert offer["compared_price"] is None
    assert (offer["price_verdict"], offer["counts"]) == ("unknown", False)


def test_piece_sizes_are_checked(client, seeded):
    buns = client.post(
        "/api/articles", json={"canonical_name": "Brötchen", "unit": "STUECK", "piece_size": "60"}
    )
    assert buns.status_code == 422
    assert "Stück-Artikel braucht kein Stückgewicht" in buns.json()["detail"]

    per_piece = client.post(
        "/api/articles",
        json={
            "canonical_name": "Avocado",
            "unit": "G",
            "regular_pack_amount": "1",
            "regular_pack_price": "0.79",
            "regular_pack_unit": "STUECK",
        },
    )
    assert per_piece.status_code == 422
    assert "braucht der Artikel ein Stückgewicht" in per_piece.json()["detail"]

    avocado = _avocado(
        client,
        piece_size="200",
        regular_pack_amount="1",
        regular_pack_price="0.79",
        regular_pack_unit="STUECK",
    )
    gone = client.patch(f"/api/articles/{avocado['id']}", json={"piece_size": None})
    assert gone.status_code == 422, "der Normalpreis pro Stück hinge sonst in der Luft"


def test_switching_to_pieces_drops_the_piece_size(client, seeded):
    avocado = _avocado(client, piece_size="200")
    switched = client.patch(f"/api/articles/{avocado['id']}", json={"unit": "STUECK"})
    assert switched.status_code == 200, switched.text
    assert switched.json()["piece_size"] is None


# ------------------------------------------------------------------ Mindestpackung

BLUEBERRIES = (
    RawOffer("Heidelbeeren", price=Decimal("3.33"), pack="200 g",
             valid_to=date.today() + timedelta(days=6)),
    RawOffer("Heidelbeeren XXL", price=Decimal("4.99"), pack="500 g",
             valid_to=date.today() + timedelta(days=6)),
    # nur der Grundpreis: 3,99 € bei 13,30 €/kg sind 300 g
    RawOffer("Bio Heidelbeeren", price=Decimal("3.99"), base_price="13,30 €/kg",
             valid_to=date.today() + timedelta(days=6)),
    RawOffer("Heidelbeeren aus der Region", price=Decimal("2.99"),
             valid_to=date.today() + timedelta(days=6)),
)


def _blueberries(client, **fields) -> dict:
    response = client.post(
        "/api/articles", json={"canonical_name": "Heidelbeeren", "unit": "G", **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_offers_count_only_from_the_minimum_pack(client, seeded):
    """Heidelbeeren erst ab 400 g: 200 g und 300 g zählen nicht, 500 g schon - und eine
    Packung, deren Größe niemand kennt, auch nicht."""
    article = _blueberries(client, min_offer_amount="400")
    assert Decimal(article["min_offer_amount"]) == Decimal("400")

    offers = _fetch(client, *BLUEBERRIES)
    judged = {
        name: (offers[name]["offer_amount"], offers[name]["pack_verdict"], offers[name]["counts"])
        for name in ("Heidelbeeren", "Heidelbeeren XXL", "Bio Heidelbeeren",
                     "Heidelbeeren aus der Region")
    }
    assert judged == {
        "Heidelbeeren": ("200", "too_small", False),
        "Heidelbeeren XXL": ("500", "ok", True),
        "Bio Heidelbeeren": ("300", "too_small", False),
        "Heidelbeeren aus der Region": (None, "unknown", False),
    }
    assert offers["Heidelbeeren XXL"]["min_offer_amount"] == "400"


def test_without_a_minimum_every_pack_counts(client, seeded):
    _blueberries(client)
    offers = _fetch(client, *BLUEBERRIES)
    assert offers["Heidelbeeren"]["pack_verdict"] is None
    assert offers["Heidelbeeren"]["counts"] is True


def test_the_minimum_pack_can_be_cleared_and_survives_a_merge(client, seeded):
    article = _blueberries(client, min_offer_amount="400")
    cleared = client.patch(f"/api/articles/{article['id']}", json={"min_offer_amount": None})
    assert cleared.json()["min_offer_amount"] is None
    assert client.patch(
        f"/api/articles/{article['id']}", json={"min_offer_amount": "0"}
    ).status_code == 422

    source = client.post(
        "/api/articles",
        json={"canonical_name": "Blaubeeren", "unit": "G", "min_offer_amount": "250"},
    ).json()
    merged = client.post(
        f"/api/articles/{article['id']}/merge", json={"source_ids": [source["id"]]}
    )
    assert Decimal(merged.json()["min_offer_amount"]) == Decimal("250")


def test_the_bring_name_can_be_removed(client, seeded):
    """Das Formular schickt `null` - bisher blieb der alte Name einfach stehen. Er zählt
    auch als Name beim Angebotsabgleich ("Cola" fand jede Cola)."""
    article = _article(client, "Hirtenkäse")
    named = client.patch(f"/api/articles/{article['id']}", json={"bring_catalog_name": "Feta"})
    assert named.json()["bring_catalog_name"] == "Feta"
    cleared = client.patch(f"/api/articles/{article['id']}", json={"bring_catalog_name": None})
    assert cleared.json()["bring_catalog_name"] is None
