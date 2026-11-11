"""Nährstoff-Rangliste über die API."""

from __future__ import annotations


def test_nutrient_list_starts_with_macros(client):
    codes = [n["code"] for n in client.get("/api/nutrients").json()]
    assert codes[:4] == ["kcal", "carbs_g", "fat_g", "protein_g"]
    assert "VITC" in codes


def test_articles_ranked_by_protein(client):
    for name, protein, kcal in (("Tofu", "16", "120"), ("Reis", "7", "350"), ("Gurke", None, None)):
        body = {"canonical_name": name, "unit": "G"}
        if protein:
            body |= {"protein_g": protein, "kcal": kcal}
        assert client.post("/api/articles", json=body).status_code == 201

    data = client.get("/api/nutrients/protein_g/articles").json()
    assert [e["name"] for e in data["entries"]] == ["Tofu", "Reis"]
    assert data["entries"][0]["per"] == "100 g"
    assert [m["name"] for m in data["missing"]] == ["Gurke"]

    dense = client.get("/api/nutrients/protein_g/articles", params={"basis": "kcal"}).json()
    assert dense["entries"][0]["per"] == "100 kcal"
    assert dense["entries"][0]["amount"] == "13.33"

    assert client.get("/api/nutrients/NOPE/articles").status_code == 422
