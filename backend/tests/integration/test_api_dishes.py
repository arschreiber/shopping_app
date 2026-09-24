"""Router + Service + Schema zusammen (ARCHITECTURE.md §9)."""

from __future__ import annotations


def create_article(client, name: str, unit: str = "G", **kwargs) -> int:
    response = client.post(
        "/api/articles", json={"canonical_name": name, "unit": unit, **kwargs}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_article_crud_roundtrip(client):
    article_id = create_article(client, "Basmatireis", aliases=["Reis"])
    assert client.get(f"/api/articles/{article_id}").json()["aliases"] == ["Reis"]

    patched = client.patch(f"/api/articles/{article_id}", json={"is_staple": True})
    assert patched.json()["is_staple"] is True

    assert client.get("/api/articles", params={"q": "basmati"}).json()[0]["id"] == article_id


def test_only_canonical_units_are_accepted(client):
    response = client.post("/api/articles", json={"canonical_name": "Milch", "unit": "L"})
    assert response.status_code == 422
    assert "kanonische Einheit" in response.json()["detail"]


def test_duplicate_article_is_rejected(client):
    create_article(client, "Zucchini", "STUECK")
    response = client.post("/api/articles", json={"canonical_name": "zucchini", "unit": "STUECK"})
    assert response.status_code == 422


def test_dish_with_ingredients(client):
    rice = create_article(client, "Basmatireis")
    cheese = create_article(client, "Hirtenkäse")
    response = client.post(
        "/api/dishes",
        json={
            "name": "Hirtenkäse-Reispfanne",
            "portions": 3,
            "packable": True,
            "effort": "QUICK",
            "suitable_for": "BOTH",
            "ingredients": [
                {"article_id": rice, "quantity": "250", "unit": "G"},
                {"article_id": cheese, "quantity": "200", "unit": "G"},
            ],
            "categories": [
                {"axis": "SIDE", "name": "Reis"},
                {"axis": "PROTEIN", "name": "Hirtenkäse"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    dish = response.json()
    assert dish["can_double"] is False  # 3 Portionen
    assert [i["spec_text"] for i in dish["ingredients"]] == ["250 g", "200 g"]
    assert {c["name"] for c in dish["categories"]} == {"Reis", "Hirtenkäse"}


def test_ingredient_unit_must_match_article_dimension(client):
    onions = create_article(client, "Zwiebeln", "STUECK")
    response = client.post(
        "/api/dishes",
        json={
            "name": "Zwiebelsuppe",
            "portions": 2,
            "ingredients": [{"article_id": onions, "quantity": "150", "unit": "G"}],
        },
    )
    assert response.status_code == 422
    assert "Dimensionswechsel" in response.json()["detail"]


def test_dish_is_archived_not_deleted(client):
    create_article(client, "Nudeln")
    dish_id = client.post("/api/dishes", json={"name": "Pasta", "portions": 2}).json()["id"]
    assert client.delete(f"/api/dishes/{dish_id}").json()["archived"] is True
    assert client.get("/api/dishes").json() == []
    assert len(client.get("/api/dishes", params={"include_archived": True}).json()) == 1


def test_parse_endpoint_matches_and_flags_new_articles(client):
    create_article(client, "Basmatireis", aliases=["Reis"])
    response = client.post(
        "/api/parse/ingredients",
        json={"text": "250 g Basmatireis\n300 g Rinderhack\nSalz"},
    )
    lines = response.json()["lines"]
    assert lines[0]["article_id"] is not None
    assert lines[0]["quantity"] == "250"
    assert lines[1]["article_id"] is None
    assert lines[1]["catalog_suggestion"] == "Rinderhack"  # Chip "neu anlegen"
    assert lines[2]["quantity"] is None  # "nach Bedarf"


def test_parse_reports_a_unit_conflict_instead_of_guessing(client):
    create_article(client, "Zwiebeln", "STUECK")
    response = client.post("/api/parse/ingredients", json={"text": "150 g Zwiebeln"})
    line = response.json()["lines"][0]
    assert line["article_id"] is not None
    assert line["unit_conflict"] is True


def test_categories_are_ranked_by_usage(client, seeded):
    rows = client.get("/api/categories").json()
    assert rows
    assert rows == sorted(rows, key=lambda r: (-r["usage"], r["name"]))


def test_cook_log_drives_rotation(client, seeded):
    dish_id = client.get("/api/dishes").json()[0]["id"]
    before = client.get(f"/api/dishes/{dish_id}").json()
    assert before["weeks_since_cooked"] is None

    client.post(
        "/api/cook-log",
        json={"dish_id": dish_id, "cooked_at": "2026-09-01", "rating": 5},
    )
    after = client.get(f"/api/dishes/{dish_id}").json()
    assert after["last_cooked"] == "2026-09-01"
    assert after["rating"] == 5


def test_creating_a_dish_again_revives_the_archived_one(client):
    """Ein archiviertes Gericht darf seinen Namen nicht für immer blockieren."""
    create_article(client, "Nudeln")
    first = client.post("/api/dishes", json={"name": "Pizza", "portions": 2}).json()
    client.delete(f"/api/dishes/{first['id']}")

    again = client.post("/api/dishes", json={"name": "Pizza", "portions": 3})
    assert again.status_code == 201, again.text
    assert again.json()["id"] == first["id"], "dieselbe Zeile, damit die Historie bleibt"
    assert again.json()["archived"] is False
    assert again.json()["portions"] == 3


def test_an_active_dish_name_is_still_taken(client):
    client.post("/api/dishes", json={"name": "Pizza", "portions": 2})
    response = client.post("/api/dishes", json={"name": "pizza", "portions": 2})
    assert response.status_code == 422
    assert "gibt es schon" in response.json()["detail"]
