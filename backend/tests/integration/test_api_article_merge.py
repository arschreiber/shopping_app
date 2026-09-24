"""Korpus-Sparsamkeit: Vorschläge statt Dubletten, und Zusammenführen, wenn's zu spät ist.

Das Ziel des Nutzers: *ein* "Reis" statt "Reis", "Basmatireis" und "Vollkornreis".
"""

from __future__ import annotations

from decimal import Decimal

ISO = "2026-W37"


def article(client, name: str, unit: str = "G", **kwargs) -> int:
    response = client.post(
        "/api/articles", json={"canonical_name": name, "unit": unit, **kwargs}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def dish(client, name: str, ingredients: list[dict], portions: int = 3) -> int:
    response = client.post(
        "/api/dishes",
        json={"name": name, "portions": portions, "ingredients": ingredients},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ------------------------------------------------------------------------- Vorschläge


def test_parse_suggests_an_existing_article_for_a_compound(client):
    """"Basmatireis" bei vorhandenem "Reis" darf keinen neuen Artikel nahelegen."""
    article(client, "Reis")
    line = client.post(
        "/api/parse/ingredients", json={"text": "250 g Basmatireis"}
    ).json()["lines"][0]

    assert line["article_id"] is None, "kein automatischer Treffer - das wäre geraten"
    assert [s["article"]["canonical_name"] for s in line["suggestions"]] == ["Reis"]
    assert line["suggestions"][0]["kind"] == "COMPOUND"


def test_parse_suggests_nothing_for_an_unrelated_word(client):
    article(client, "Reis")
    line = client.post(
        "/api/parse/ingredients", json={"text": "500 g Preiselbeeren"}
    ).json()["lines"][0]
    assert line["suggestions"] == []


def test_a_confident_match_needs_no_suggestions(client):
    article(client, "Basmatireis")
    line = client.post(
        "/api/parse/ingredients", json={"text": "250 g Basmatireis"}
    ).json()["lines"][0]
    assert line["article_id"] is not None
    assert line["suggestions"] == []


# ------------------------------------------------------------------- Dubletten finden


# ---------------------------------------------------------------- Zusammenführen


def test_merge_moves_ingredient_lines(client):
    rice = article(client, "Reis")
    basmati = article(client, "Basmatireis")
    dish_id = dish(client, "Reispfanne", [{"article_id": basmati, "quantity": "250", "unit": "G"}])

    merged = client.post(f"/api/articles/{rice}/merge", json={"source_ids": [basmati]})
    assert merged.status_code == 200, merged.text

    detail = client.get(f"/api/dishes/{dish_id}").json()
    assert [i["article_name"] for i in detail["ingredients"]] == ["Reis"]
    assert detail["ingredients"][0]["spec_text"] == "250 g"
    assert basmati not in {a["id"] for a in client.get("/api/articles").json()}


def test_merge_sums_quantities_when_one_dish_used_both(client):
    """Ein Gericht mit "200 g Reis" *und* "250 g Basmatireis" wird zu einer Zeile."""
    rice = article(client, "Reis")
    basmati = article(client, "Basmatireis")
    dish_id = dish(
        client,
        "Doppelreis",
        [
            {"article_id": rice, "quantity": "200", "unit": "G"},
            {"article_id": basmati, "quantity": "250", "unit": "G"},
        ],
    )

    client.post(f"/api/articles/{rice}/merge", json={"source_ids": [basmati]})
    ingredients = client.get(f"/api/dishes/{dish_id}").json()["ingredients"]
    assert len(ingredients) == 1
    assert Decimal(ingredients[0]["quantity"]) == Decimal("450")


def test_merge_handles_kilogram_lines(client):
    rice = article(client, "Reis")
    basmati = article(client, "Basmatireis")
    dish_id = dish(
        client,
        "Reis hoch zwei",
        [
            {"article_id": rice, "quantity": "500", "unit": "G"},
            {"article_id": basmati, "quantity": "1", "unit": "KG"},
        ],
    )
    client.post(f"/api/articles/{rice}/merge", json={"source_ids": [basmati]})
    ingredients = client.get(f"/api/dishes/{dish_id}").json()["ingredients"]
    assert len(ingredients) == 1
    assert ingredients[0]["spec_text"] == "1,5 kg"


def test_merge_refuses_different_dimensions(client):
    """2 Stück Zwiebeln und 150 g Zwiebeln lassen sich nicht summieren."""
    pieces = article(client, "Zwiebeln", "STUECK")
    grams = article(client, "Zwiebelwürfel", "G")
    response = client.post(f"/api/articles/{pieces}/merge", json={"source_ids": [grams]})
    assert response.status_code == 422
    assert "Dimensionen" in response.json()["detail"]


def test_merge_takes_over_flags_and_the_bring_name(client):
    rice = article(client, "Reis")
    basmati = article(client, "Basmatireis", is_staple=True, bring_catalog_name="Reis")
    merged = client.post(f"/api/articles/{rice}/merge", json={"source_ids": [basmati]}).json()
    assert merged["is_staple"] is True
    assert merged["bring_catalog_name"] == "Reis"


def test_merge_several_sources_at_once(client):
    rice = article(client, "Reis")
    sources = [article(client, "Basmatireis"), article(client, "Vollkornreis")]
    merged = client.post(f"/api/articles/{rice}/merge", json={"source_ids": sources}).json()

    assert merged["canonical_name"] == "Reis"
    assert merged["aliases"] == [], "Zutaten haben genau einen Namen - keine Zweitnamen"
    assert [a["canonical_name"] for a in client.get("/api/articles").json()] == ["Reis"]


def test_merge_consolidates_the_shopping_list(client, seeded):
    """Nach dem Zusammenführen steht Reis einmal auf der Liste, nicht zweimal."""
    articles = {a["canonical_name"]: a["id"] for a in client.get("/api/articles").json()}
    rice = articles["Basmatireis"]
    extra = article(client, "Vollkornreis")
    dish(client, "Testreis", [{"article_id": extra, "quantity": "300", "unit": "G"}], portions=2)

    client.post(f"/api/weeks/{ISO}/propose", json={})
    before = client.get(f"/api/weeks/{ISO}/shopping-list").json()["items"]
    rice_rows = [i for i in before if "reis" in i["article_name"].lower()]

    client.post(f"/api/articles/{rice}/merge", json={"source_ids": [extra]})
    after = client.get(f"/api/weeks/{ISO}/shopping-list").json()["items"]
    merged_rows = [i for i in after if "reis" in i["article_name"].lower()]

    assert len(merged_rows) <= len(rice_rows)
    assert len({row["article_id"] for row in merged_rows}) == len(merged_rows)


def test_merge_needs_a_source(client):
    rice = article(client, "Reis")
    response = client.post(f"/api/articles/{rice}/merge", json={"source_ids": [rice]})
    assert response.status_code == 422
    assert "Keine Artikel" in response.json()["detail"]



# ------------------------------------------------- Genau ein Name pro Zutat


def test_choosing_a_suggestion_creates_no_second_name(client):
    """Der Vorschlag führt zur vorhandenen Zutat - nicht zu einer Schreibweise davon."""
    rice = article(client, "Reis")
    line = client.post(
        "/api/parse/ingredients", json={"text": "250 g Basmatireis"}
    ).json()["lines"][0]
    assert [s["article"]["id"] for s in line["suggestions"]] == [rice]

    # Die Zeile wird auf "Reis" gelegt; am Artikel ändert sich dadurch nichts.
    dish(client, "Reispfanne", [{"article_id": rice, "quantity": "250", "unit": "G"}])
    assert client.get(f"/api/articles/{rice}").json()["aliases"] == []


def test_the_search_matches_names_only(client):
    """Die Combobox sucht über den Namen, nicht über Angebots-Aliase."""
    article(client, "Hirtenkäse", aliases=["Schafskäse"])

    by_name = client.get("/api/articles/suggest", params={"q": "Hirten"}).json()
    assert [hit["article"]["canonical_name"] for hit in by_name] == ["Hirtenkäse"]

    by_alias = client.get("/api/articles/suggest", params={"q": "Schafskäse"}).json()
    assert by_alias == [], "Angebots-Aliase gehören nicht in die Zutaten-Suche"


def test_the_search_finds_a_partial_name(client):
    """Wer "Reis" tippt, muss "Reis" finden, bevor er es neu anlegt."""
    rice = article(client, "Reis")
    article(client, "Kartoffeln")
    hits = client.get("/api/articles/suggest", params={"q": "Rei"}).json()
    assert rice in [hit["article"]["id"] for hit in hits]


def test_merge_leaves_no_trace_of_the_old_names(client):
    rice = article(client, "Reis")
    basmati = article(client, "Basmatireis")
    client.post(f"/api/articles/{rice}/merge", json={"source_ids": [basmati]})

    assert client.get("/api/articles", params={"q": "Basmati"}).json() == []
    line = client.post(
        "/api/parse/ingredients", json={"text": "250 g Basmatireis"}
    ).json()["lines"][0]
    assert line["article_id"] is None, "der alte Name ist weg, nicht versteckt"
    assert [s["article"]["id"] for s in line["suggestions"]] == [rice]
