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
    assert dish["factors"] == [1]  # 3 Portionen: nie vervielfacht
    assert [i["spec_text"] for i in dish["ingredients"]] == ["250 g", "200 g"]
    assert {c["name"] for c in dish["categories"]} == {"Reis", "Hirtenkäse"}


def test_doubling_can_be_switched_off_on_a_two_portion_dish(client):
    """`allow_double` ist der Schalter, `factors` das Ergebnis daraus."""
    dish_id = client.post("/api/dishes", json={"name": "Auflauf", "portions": 2}).json()["id"]
    assert client.get(f"/api/dishes/{dish_id}").json()["factors"] == [1, 2]

    patched = client.patch(f"/api/dishes/{dish_id}", json={"allow_double": False}).json()
    assert patched["allow_double"] is False
    assert patched["factors"] == [1]
    assert client.get("/api/dishes").json()[0]["allow_double"] is False



def test_a_dish_can_be_marked_as_not_reheatable(client):
    created = client.post("/api/dishes", json={"name": "Knusper-Tofu", "portions": 2}).json()
    assert created["reheatable"] is True, "Standard: aufwärmbar"

    dish_id = created["id"]
    patched = client.patch(f"/api/dishes/{dish_id}", json={"reheatable": False}).json()
    assert patched["reheatable"] is False
    assert client.get("/api/dishes").json()[0]["reheatable"] is False

    salad = client.post(
        "/api/dishes", json={"name": "Salat", "portions": 2, "reheatable": False}
    ).json()
    assert salad["reheatable"] is False


def test_single_portion_dishes_choose_their_factors(client):
    """Bei 1 Portion sind doppelt *und* dreifach zugleich wählbar."""
    ramen = client.post(
        "/api/dishes",
        json={"name": "Ramen", "portions": 1, "allow_double": True, "allow_triple": True},
    ).json()
    assert ramen["factors"] == [1, 2, 3]

    patched = client.patch(f"/api/dishes/{ramen['id']}", json={"allow_double": False}).json()
    assert patched["factors"] == [1, 3]
    assert client.get("/api/dishes").json()[0]["factors"] == [1, 3]


def test_portions_stay_between_one_and_three(client):
    for portions in (0, 4):
        response = client.post("/api/dishes", json={"name": f"P{portions}", "portions": portions})
        assert response.status_code == 422

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


def test_renaming_onto_a_taken_name_is_refused(client):
    """Lief vorher in den UNIQUE-Index (500) - oder, anders geschrieben, an ihm vorbei."""
    client.post("/api/dishes", json={"name": "Pizza", "portions": 2})
    soup = client.post("/api/dishes", json={"name": "Suppe", "portions": 2}).json()
    old = client.post("/api/dishes", json={"name": "Chili", "portions": 2}).json()
    client.delete(f"/api/dishes/{old['id']}")

    for name, hint in (("Pizza", ""), ("pizza", ""), ("Chili", " (archiviert)")):
        response = client.patch(f"/api/dishes/{soup['id']}", json={"name": name})
        assert response.status_code == 422, name
        assert response.json()["detail"] == f"'{name}' gibt es schon{hint}"

    assert client.patch(f"/api/dishes/{soup['id']}", json={"name": " "}).status_code == 422
    own = client.patch(f"/api/dishes/{soup['id']}", json={"name": " suppe "})
    assert own.status_code == 200, "die eigene Schreibweise ändern geht"
    assert own.json()["name"] == "suppe"
