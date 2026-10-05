"""Nährwerte am Gericht (nur dort - der Wochenplan bleibt davon unberührt)."""

from __future__ import annotations

from decimal import Decimal


def article(client, name: str, unit: str = "G", **kwargs) -> int:
    response = client.post(
        "/api/articles", json={"canonical_name": name, "unit": unit, **kwargs}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


RICE = {"kcal": "350", "protein_g": "7", "carbs_g": "78", "fat_g": "1"}
OIL = {"kcal": "900", "protein_g": "0", "carbs_g": "0", "fat_g": "100"}


def test_article_carries_nutrition_with_its_basis(client):
    rice = article(client, "Reis", **RICE)
    data = client.get(f"/api/articles/{rice}").json()
    assert data["kcal"] == "350"
    assert data["nutrition_basis"] == "je 100 g"

    pieces = article(client, "Zucchini", "STUECK", kcal="40")
    assert client.get(f"/api/articles/{pieces}").json()["nutrition_basis"] == "je Stück"


def test_dish_reports_nutrition_per_portion(client):
    rice = article(client, "Reis", **RICE)
    oil = article(client, "Olivenöl", "ML", **OIL)
    dish = client.post(
        "/api/dishes",
        json={
            "name": "Reispfanne",
            "portions": 2,
            "ingredients": [
                {"article_id": rice, "quantity": "200", "unit": "G"},
                {"article_id": oil, "quantity": "20", "unit": "ML"},
            ],
        },
    ).json()

    nutrition = dish["nutrition"]
    assert Decimal(nutrition["total"]["kcal"]) == Decimal(880)
    assert Decimal(nutrition["per_portion"]["kcal"]) == Decimal(440)
    assert nutrition["is_complete"] is True
    assert nutrition["counted"] == 2


def test_missing_values_are_a_visible_gap_not_a_silent_zero(client):
    rice = article(client, "Reis", **RICE)
    unknown = article(client, "Geheimzutat")
    dish = client.post(
        "/api/dishes",
        json={
            "name": "Halbwissen",
            "portions": 2,
            "ingredients": [
                {"article_id": rice, "quantity": "200", "unit": "G"},
                {"article_id": unknown, "quantity": "100", "unit": "G"},
            ],
        },
    ).json()

    nutrition = dish["nutrition"]
    assert nutrition["is_complete"] is False
    assert nutrition["missing_article_ids"] == [unknown]
    assert Decimal(nutrition["total"]["kcal"]) == Decimal(700), "Bekanntes zählt trotzdem"


def test_an_open_quantity_of_oil_is_a_gap(client):
    """"Olivenöl nach Bedarf" heißt: die Kalorien sind ehrlich unbekannt."""
    rice = article(client, "Reis", **RICE)
    oil = article(client, "Olivenöl", "ML", **OIL)
    dish = client.post(
        "/api/dishes",
        json={
            "name": "Ölpfanne",
            "portions": 2,
            "ingredients": [
                {"article_id": rice, "quantity": "200", "unit": "G"},
                {"article_id": oil, "quantity": None, "unit": "ML"},
            ],
        },
    ).json()
    assert dish["nutrition"]["open_quantity_article_ids"] == [oil]
    assert dish["nutrition"]["is_complete"] is False


def test_salt_without_a_quantity_is_no_gap(client):
    rice = article(client, "Reis", **RICE)
    salt = article(client, "Salz", kcal="0", protein_g="0", carbs_g="0", fat_g="0")
    dish = client.post(
        "/api/dishes",
        json={
            "name": "Salzreis",
            "portions": 2,
            "ingredients": [
                {"article_id": rice, "quantity": "200", "unit": "G"},
                {"article_id": salt, "quantity": None, "unit": "G"},
            ],
        },
    ).json()
    assert dish["nutrition"]["is_complete"] is True


def test_the_dish_list_carries_nutrition_too(client):
    rice = article(client, "Reis", **RICE)
    client.post(
        "/api/dishes",
        json={
            "name": "Reispfanne",
            "portions": 3,
            "ingredients": [{"article_id": rice, "quantity": "300", "unit": "G"}],
        },
    )
    row = client.get("/api/dishes").json()[0]
    assert Decimal(row["nutrition"]["per_portion"]["kcal"]) == Decimal(350)


def test_preview_works_before_the_dish_is_saved(client):
    rice = article(client, "Reis", **RICE)
    preview = client.post(
        "/api/nutrition/preview",
        json={
            "portions": 2,
            "ingredients": [{"article_id": rice, "quantity": "200", "unit": "G"}],
        },
    ).json()
    assert Decimal(preview["per_portion"]["kcal"]) == Decimal(350)
    assert client.get("/api/dishes").json() == [], "nichts gespeichert"


def test_preview_works_for_a_single_portion_dish(client):
    """Mit den 1-Portionen-Gerichten kam die Vorschau im Formular nicht mit (422)."""
    rice = article(client, "Reis", **RICE)
    response = client.post(
        "/api/nutrition/preview",
        json={
            "portions": 1,
            "ingredients": [{"article_id": rice, "quantity": "100", "unit": "G"}],
        },
    )
    assert response.status_code == 200, response.text
    assert Decimal(response.json()["per_portion"]["kcal"]) == Decimal(350)


def test_nutrition_can_be_edited_and_zero_is_a_value(client):
    """0 kcal heißt "enthält nichts" - nicht "nicht erfasst"."""
    rice = article(client, "Reis", **RICE)
    patched = client.patch(f"/api/articles/{rice}", json={"kcal": "0"}).json()
    assert Decimal(patched["kcal"]) == Decimal(0)


def test_negative_values_are_rejected(client):
    response = client.post(
        "/api/articles", json={"canonical_name": "Unsinn", "unit": "G", "kcal": "-5"}
    )
    assert response.status_code == 422


def test_the_week_plan_stays_free_of_nutrition(client, seeded):
    """Bewusste Grenze: Nährwerte gibt es im Gerichte-Tab, nicht im Wochenplan."""
    week = client.post("/api/weeks/2026-W37/propose", json={}).json()
    assert "nutrition" not in week
    for slot in week["slots"]:
        assert "nutrition" not in (slot.get("assignment") or {})

    shopping = client.get("/api/weeks/2026-W37/shopping-list").json()
    assert "nutrition" not in shopping
