"""BLS-Import, Zuordnung und Mikronährstoffe am Gericht - über Service und API."""

from __future__ import annotations

import json
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy.orm import sessionmaker

from mealplan.domain.micronutrients import IMPORTED_CODES
from mealplan.integrations.nutrients import bls
from mealplan.services import nutrients as service

# Je Lebensmittel nur die Werte, um die es geht - alle anderen Spalten bleiben leer,
# müssen aber da sein: der Leser prüft, dass der BLS jede erwartete Spalte hat.
FOODS = [
    ("G211100", "Spinat roh", "Spinach raw",
     {"ENERCC": 23, "PROT625": 2.9, "FAT": 0.4, "CHO": 0.6, "FE": 3.6, "VITC": 50, "VITB6": 220}),
    ("C352000", "Reis poliert, roh", "White rice raw",
     {"ENERCC": 351, "PROT625": 7.9, "FAT": 0.6, "CHO": 78, "FE": 0.8, "VITC": 0, "VITB6": 150}),
    ("Q180000", "Rapsöl/Rüböl", "Rapeseed oil", {"ENERCC": 900, "FAT": 100, "VITC": 0}),
]


def write_bls(folder: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    header = ["BLS Code", "Lebensmittelbezeichnung", "Food name"]
    for code in IMPORTED_CODES:
        header += [f"{code} Irgendwas [g/100g]", f"{code} Datenherkunft", f"{code} Referenz"]
    sheet.append(header)
    for code, name, name_en, values in FOODS:
        row = [code, name, name_en]
        for nutrient in IMPORTED_CODES:
            row += [values.get(nutrient), "Analyse", "-"]
        sheet.append(row)
    xlsx = folder / "BLS_4_0_Daten_2025_DE.xlsx"
    workbook.save(xlsx)
    archive = folder / "BLS_4_0_2025_DE.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.write(xlsx, f"BLS_4_0_2025_DE/{xlsx.name}")
    xlsx.unlink()
    return archive


@pytest.fixture
def bls_loaded(client, engine, tmp_path):
    source = write_bls(tmp_path)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        result = service.import_bls(session, source)
        session.commit()
    assert result.foods == 3
    return source


def article(client, name: str, unit: str = "G", **kwargs) -> int:
    response = client.post(
        "/api/articles", json={"canonical_name": name, "unit": unit, **kwargs}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_reader_keeps_unknown_values_out(tmp_path):
    rows = {r.code: r for r in bls.read_rows(write_bls(tmp_path), ["FE", "VITC"])}
    assert rows["G211100"].nutrients == {"FE": 3.6, "VITC": 50.0}
    assert "FE" not in rows["Q180000"].nutrients  # leere Zelle ist nicht null


def test_unchanged_file_is_not_imported_twice(bls_loaded, engine):
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        again = service.import_bls(session, bls_loaded)
    assert again.imported is False
    assert again.foods == 3


def test_link_via_api_and_dish_gets_micronutrients(client, bls_loaded):
    spinach = article(client, "Spinat")
    rice = article(client, "Reis", kcal="350", protein_g="7", carbs_g="78", fat_g="1")

    suggestions = client.get(f"/api/articles/{spinach}/bls-suggestions").json()
    assert suggestions[0]["code"] == "G211100"

    linked = client.put(f"/api/articles/{spinach}/bls", json={"code": "G211100"}).json()
    assert linked["bls_name"] == "Spinat roh"
    client.put(f"/api/articles/{rice}/bls", json={"code": "C352000"})

    dish = client.post(
        "/api/dishes",
        json={
            "name": "Spinatreis",
            "portions": 2,
            "ingredients": [
                {"article_id": spinach, "quantity": "300", "unit": "G"},
                {"article_id": rice, "quantity": "200", "unit": "G"},
            ],
        },
    ).json()
    micros = dish["nutrition"]["micros"]
    values = {v["code"]: v for v in micros["values"]}
    assert Decimal(values["FE"]["amount"]) == Decimal("6.2")
    assert Decimal(values["VITB6"]["amount"]) == Decimal("0.48")  # µg -> mg
    assert values["FE"]["share"] is not None
    assert micros["is_complete"] is True
    assert "Max Rubner-Institut" in micros["attribution"]

    # Etikett vor Datenbank: Reis behält seine 350 kcal, Spinat kommt aus dem BLS
    per_portion = dish["nutrition"]["per_portion"]
    assert Decimal(per_portion["kcal"]) == Decimal(384)  # (3·23 + 2·350) / 2

    # Die Gerichte-Liste bleibt schlank
    listed = client.get("/api/dishes").json()
    assert listed[0]["nutrition"]["micros"] is None


def test_preview_carries_micros_and_gaps(client, bls_loaded):
    spinach = article(client, "Spinat")
    whey = article(client, "Whey")
    client.put(f"/api/articles/{spinach}/bls", json={"code": "G211100"})
    client.put(f"/api/articles/{whey}/bls", json={"skip": True})

    preview = client.post(
        "/api/nutrition/preview",
        json={
            "portions": 1,
            "ingredients": [
                {"article_id": spinach, "quantity": "100", "unit": "G"},
                {"article_id": whey, "quantity": "30", "unit": "G"},
            ],
        },
    ).json()
    assert preview["micros"]["skipped_article_ids"] == [whey]
    assert preview["micros"]["is_complete"] is False


def test_unknown_code_is_rejected(client, bls_loaded):
    spinach = article(client, "Spinat")
    response = client.put(f"/api/articles/{spinach}/bls", json={"code": "NOPE"})
    assert response.status_code == 422


def test_search_endpoint(client, bls_loaded):
    hits = client.get("/api/articles/bls-search", params={"q": "reis roh"}).json()
    assert [h["code"] for h in hits] == ["C352000"]


def test_links_file_round_trip(client, bls_loaded, engine, tmp_path):
    oil = article(client, "Öl", "ML")
    spinach = article(client, "Spinat")
    article(client, "Monster Energy", "ML")
    client.put(f"/api/articles/{oil}/bls", json={"code": "Q180000", "grams_per_unit": "0.92"})

    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        exported = service.export_links(session)
    assert exported["Öl"] == {"code": "Q180000", "grams_per_unit": "0.92", "name": "Rapsöl/Rüböl"}

    decisions = {
        "Spinat": {"code": "G211100"},
        "Monster Energy": {"skip": True},
        "Öl": {"code": "G211100"},  # schon entschieden - bleibt
        "Gibt es nicht": {"code": "G211100"},
    }
    path = tmp_path / "links.json"
    path.write_text(json.dumps({"articles": decisions}), encoding="utf-8")
    with factory() as session:
        result = service.apply_links(session, service.read_links(path))
        session.commit()
    assert sorted(result.applied) == ["Monster Energy", "Spinat"]
    assert result.kept == ["Öl"]
    assert result.unknown == ["Gibt es nicht"]

    assert client.get(f"/api/articles/{spinach}").json()["bls_code"] == "G211100"
    assert client.get(f"/api/articles/{oil}").json()["bls_code"] == "Q180000"
    with factory() as session:
        assert [a.canonical_name for a in service.open_articles(session)] == []


def test_label_micros_round_trip_and_count_in_dishes(client, bls_loaded):
    whey = article(
        client, "Whey", label_micros={"CA": "1000", "FOLAC": "200", "VITB6": "2"}
    )
    client.put(f"/api/articles/{whey}/bls", json={"skip": True})
    data = client.get(f"/api/articles/{whey}").json()
    assert data["label_micros"] == {"CA": "1000", "FOLAC": "200", "VITB6": "2"}

    preview = client.post(
        "/api/nutrition/preview",
        json={"portions": 1, "ingredients": [{"article_id": whey, "quantity": "30", "unit": "G"}]},
    ).json()["micros"]
    values = {v["code"]: v for v in preview["values"]}
    assert Decimal(values["CA"]["amount"]) == Decimal(300)
    assert Decimal(values["FOL"]["amount"]) == Decimal(102)  # 200 · 1,7 · 0,3
    assert preview["skipped_article_ids"] == []

    cleared = client.patch(f"/api/articles/{whey}", json={"label_micros": None}).json()
    assert cleared["label_micros"] is None


def test_label_micros_reject_unknown_codes(client):
    response = client.post(
        "/api/articles", json={"canonical_name": "X", "unit": "G", "label_micros": {"FOO": "1"}}
    )
    assert response.status_code == 422


def test_micro_fields_list_folic_acid_next_to_folate(client):
    codes = [f["code"] for f in client.get("/api/articles/micro-fields").json()]
    assert codes[codes.index("FOL") + 1] == "FOLAC"
    assert len(codes) == 24


def test_article_carries_its_profile(client, bls_loaded):
    spinach = article(client, "Spinat", label_micros={"VITC": "30"})
    client.put(f"/api/articles/{spinach}/bls", json={"code": "G211100"})
    micros = {m["code"]: m for m in client.get(f"/api/articles/{spinach}").json()["micros"]}
    assert micros["FE"] == {"code": "FE", "amount": "3.6", "source": "bls", "share": "33"}
    assert micros["VITC"]["source"] == "label"
    assert Decimal(micros["VITC"]["amount"]) == Decimal(30)


def test_breakdown_shows_what_each_ingredient_brings(client, bls_loaded):
    spinach = article(client, "Spinat")
    rice = article(client, "Reis", kcal="350", protein_g="7", carbs_g="78", fat_g="1")
    client.put(f"/api/articles/{spinach}/bls", json={"code": "G211100"})
    client.put(f"/api/articles/{rice}/bls", json={"code": "C352000"})
    preview = client.post(
        "/api/nutrition/preview",
        json={
            "portions": 2,
            "ingredients": [
                {"article_id": spinach, "quantity": "300", "unit": "G"},
                {"article_id": rice, "quantity": "200", "unit": "G"},
                {"article_id": spinach, "quantity": "100", "unit": "G"},  # zweite Zeile
            ],
        },
    ).json()
    parts = {p["article_id"]: p["values"] for p in preview["breakdown"]}
    assert Decimal(parts[spinach]["FE"]) == Decimal("7.2")  # 400 g · 3,6 / 100 / 2
    assert Decimal(parts[rice]["FE"]) == Decimal("0.8")
    assert Decimal(parts[rice]["kcal"]) == Decimal(350)  # Etikett, je Portion
    assert Decimal(parts[spinach]["kcal"]) == Decimal(46)  # BLS 23 kcal · 4 / 2
