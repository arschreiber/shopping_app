"""Standardwoche: das Raster, mit dem neue Wochen anfangen."""

from __future__ import annotations

URL = "/api/settings/standard-week"


def _standard(**overrides) -> dict:
    """Alle 14 Mahlzeiten auf "zwei zu Hause", einzelne per `"5L": {...}` geändert."""
    slots = []
    for day in range(7):
        for meal in ("LUNCH", "DINNER"):
            row = {
                "day": day,
                "meal": meal,
                "eaters_home": 2,
                "packed_portions": 0,
                "packed_fresh": False,
                "time_budget": "NORMAL",
            }
            row.update(overrides.get(f"{day}{meal[0]}", {}))
            slots.append(row)
    return {"slots": slots}


NOBODY = {"eaters_home": 0}
# Das Muster aus dem echten Plan: Wochenende frei, Dienstagabend nimmt einer frisch mit.
USUAL = _standard(
    **{
        "5L": NOBODY,
        "5D": NOBODY,
        "6L": NOBODY,
        "6D": NOBODY,
        "1D": {"eaters_home": 1, "packed_portions": 1, "packed_fresh": True},
        "3D": {"time_budget": "LITTLE"},
    }
)


def _by_key(slots: list[dict]) -> dict[tuple[int, str], dict]:
    return {(slot["day"], slot["meal"]): slot for slot in slots}


def test_without_a_standard_week_everyone_is_home(client):
    standard = client.get(URL).json()
    assert len(standard) == 14
    assert {(s["eaters_home"], s["packed_portions"], s["time_budget"]) for s in standard} == {
        (2, 0, "NORMAL")
    }


def test_a_new_week_starts_with_the_standard_week(client):
    saved = client.put(URL, json=USUAL)
    assert saved.status_code == 200, saved.text

    week = _by_key(client.get("/api/weeks/2026-W43").json()["slots"])
    assert week[(5, "LUNCH")]["demand"] == 0
    assert week[(6, "DINNER")]["demand"] == 0
    tuesday = week[(1, "DINNER")]
    assert (tuesday["eaters_home"], tuesday["packed_portions"], tuesday["packed_fresh"]) == (
        1,
        1,
        True,
    )
    assert week[(3, "DINNER")]["time_budget"] == "LITTLE"
    assert week[(0, "LUNCH")]["eaters_home"] == 2


def test_weeks_that_already_exist_stay_as_they_are(client):
    before = client.get("/api/weeks/2026-W43").json()
    client.put(URL, json=USUAL)
    after = client.get("/api/weeks/2026-W43").json()
    assert after["slots"] == before["slots"]
    assert after["version"] == before["version"]


def test_missing_meals_fall_back_to_everyone_home(client):
    saved = client.put(URL, json={"slots": [USUAL["slots"][10]]})  # nur Samstag Mittag
    assert saved.status_code == 200, saved.text
    standard = _by_key(saved.json())
    assert len(standard) == 14
    assert standard[(5, "LUNCH")]["eaters_home"] == 0
    assert standard[(5, "DINNER")]["eaters_home"] == 2


def test_the_standard_week_is_checked(client):
    too_many = client.put(URL, json=_standard(**{"0L": {"eaters_home": 3}}))
    assert too_many.status_code == 422

    twice = client.put(URL, json={"slots": [USUAL["slots"][0], USUAL["slots"][0]]})
    assert twice.status_code == 422
    assert "doppelt" in twice.json()["detail"]

    hidden_fresh = client.put(URL, json=_standard(**{"2D": {"packed_fresh": True}}))
    assert _by_key(hidden_fresh.json())[(2, "DINNER")]["packed_fresh"] is False


def test_copying_last_week_still_wins_over_the_standard(client):
    """"wie letzte Woche" bleibt für Ausnahmen: es überschreibt die Standardwoche."""
    client.put(URL, json=USUAL)
    source = client.get("/api/weeks/2026-W43").json()
    grid = [
        {key: slot[key] for key in (
            "day", "meal", "eaters_home", "packed_portions", "packed_fresh", "time_budget",
            "special", "pinned",
        )}
        for slot in source["slots"]
    ]
    for row in grid:
        if (row["day"], row["meal"]) == (5, "LUNCH"):
            row["eaters_home"] = 2
    client.put("/api/weeks/2026-W43/grid", json={"slots": grid, "version": source["version"]})

    copied = client.post("/api/weeks/2026-W44/copy-from/2026-W43").json()
    assert _by_key(copied["slots"])[(5, "LUNCH")]["eaters_home"] == 2
