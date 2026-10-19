"""Wochen-Endpunkte: Raster, Vorschlag, Kandidaten, Pins, Locking."""

from __future__ import annotations

import pytest

ISO = "2026-W37"


def grid_payload(week: dict, **overrides) -> dict:
    """Raster aus einer WeekOut-Antwort in ein GridIn ueberfuehren."""
    slots = []
    for slot in week["slots"]:
        key = f"{slot['day']}{slot['meal'][0]}"
        row = {
            "day": slot["day"],
            "meal": slot["meal"],
            "eaters_home": slot["eaters_home"],
            "packed_portions": slot["packed_portions"],
            "time_budget": slot["time_budget"],
            "special": slot["special"],
            "pinned": slot["pinned"],
        }
        row.update(overrides.get(key, {}))
        slots.append(row)
    return {"slots": slots, "version": week["version"]}


def test_opening_a_week_creates_the_default_grid(client):
    week = client.get(f"/api/weeks/{ISO}").json()
    assert week["iso"] == ISO
    assert week["start_date"] == "2026-09-07"  # Montag
    assert len(week["slots"]) == 14
    assert week["needed_count"] == 14


def test_invalid_iso_week_is_rejected(client):
    response = client.get("/api/weeks/2026-W99")
    assert response.status_code == 422


def test_grid_update_bumps_the_version(client):
    week = client.get(f"/api/weeks/{ISO}").json()
    updated = client.put(
        f"/api/weeks/{ISO}/grid",
        json=grid_payload(
            week,
            **{"1L": {"eaters_home": 0}, "0D": {"packed_portions": 1}},
        ),
    ).json()
    assert updated["version"] == week["version"] + 1
    by_key = {(s["day"], s["meal"]): s for s in updated["slots"]}
    assert by_key[(1, "LUNCH")]["eaters_home"] == 0
    assert by_key[(0, "DINNER")]["packed_portions"] == 1
    assert by_key[(0, "DINNER")]["demand"] == 3


def test_stale_version_is_a_conflict(client):
    """Laptop und Handy gleichzeitig (ARCHITECTURE.md §3, §6)."""
    week = client.get(f"/api/weeks/{ISO}").json()
    payload = grid_payload(week)
    assert client.put(f"/api/weeks/{ISO}/grid", json=payload).status_code == 200

    response = client.put(f"/api/weeks/{ISO}/grid", json=payload)  # gleiche alte Version
    assert response.status_code == 409
    assert response.json()["current_version"] == week["version"] + 1


@pytest.mark.optimizer
def test_propose_fills_the_week_with_reasons(client, seeded):
    week = client.post(f"/api/weeks/{ISO}/propose", json={}).json()
    filled = [s for s in week["slots"] if s["assignment"]]
    assert len(filled) >= 10
    first = filled[0]["assignment"]
    assert first["score"]["reasons"], "Jeder Vorschlag braucht seine Begründung"
    assert first["score"]["total"] == sum(
        c["delta"] for c in first["score"]["contributions"]
    )


def test_each_proposal_draws_a_new_plan(client, seeded):
    """Gleiches Raster, neuer Klick: ein neuer Plan - sonst kommt immer dasselbe raus."""
    plans = []
    for _ in range(3):
        week = client.post(f"/api/weeks/{ISO}/propose", json={}).json()
        plans.append(
            tuple((s["day"], (s["assignment"] or {}).get("dish_name")) for s in week["slots"])
        )
    assert len(set(plans)) > 1


def test_pins_survive_a_new_proposal(client, seeded):
    week = client.post(f"/api/weeks/{ISO}/propose", json={}).json()
    target = next(s for s in week["slots"] if s["assignment"])
    dish_name = target["assignment"]["dish_name"]

    client.put(
        f"/api/weeks/{ISO}/slots/{target['day']}/{target['meal']}/pin", json={"pinned": True}
    )
    client.delete(f"/api/weeks/{ISO}/assignments")  # keep_pinned=True
    after = client.post(f"/api/weeks/{ISO}/propose", json={}).json()
    kept = next(
        s for s in after["slots"] if s["day"] == target["day"] and s["meal"] == target["meal"]
    )
    assert kept["assignment"]["dish_name"] == dish_name


def test_candidates_are_sorted_and_explained(client, seeded):
    options = client.get(f"/api/weeks/{ISO}/slots/0/DINNER/candidates").json()
    assert options
    assert [o["score"]["total"] for o in options] == sorted(
        (o["score"]["total"] for o in options), reverse=True
    )
    assert all(o["eligible"] for o in options)


def test_candidates_can_explain_the_excluded_dishes(client, seeded):
    week = client.get(f"/api/weeks/{ISO}").json()
    client.put(
        f"/api/weeks/{ISO}/grid", json=grid_payload(week, **{"0D": {"time_budget": "LITTLE"}})
    )
    options = client.get(
        f"/api/weeks/{ISO}/slots/0/DINNER/candidates",
        params={"include_ineligible": True},
    ).json()
    blocked = [o for o in options if not o["eligible"]]
    assert blocked
    assert any("Aufwand" in w for o in blocked for w in o["warnings"])


def test_manual_assignment_and_clearing(client, seeded):
    dishes = client.get("/api/dishes").json()
    dish = next(d for d in dishes if d["portions"] == 2)
    response = client.put(
        f"/api/weeks/{ISO}/slots/2/DINNER/assignment",
        json={"kind": "DISH", "dish_id": dish["id"]},
    )
    assert response.status_code == 200
    slot = next(s for s in response.json()["slots"] if s["day"] == 2 and s["meal"] == "DINNER")
    assert slot["assignment"]["dish_name"] == dish["name"]

    cleared = client.delete(f"/api/weeks/{ISO}/slots/2/DINNER/assignment").json()
    slot = next(s for s in cleared["slots"] if s["day"] == 2 and s["meal"] == "DINNER")
    assert slot["assignment"] is None


def test_assignment_rejects_too_few_portions(client, seeded):
    week = client.get(f"/api/weeks/{ISO}").json()
    client.put(
        f"/api/weeks/{ISO}/grid",
        json=grid_payload(week, **{"0D": {"eaters_home": 2, "packed_portions": 2}}),
    )
    small = next(d for d in client.get("/api/dishes").json() if d["portions"] == 2)
    response = client.put(
        f"/api/weeks/{ISO}/slots/0/DINNER/assignment",
        json={"kind": "DISH", "dish_id": small["id"]},
    )
    assert response.status_code == 422
    assert "reichen nicht" in response.json()["detail"]



def test_a_single_portion_dish_is_assigned_with_its_factor(client):
    """Ein Burger-Rezept für eine Person, doppelt gekocht für die zwei zu Hause."""
    burger = client.post(
        "/api/dishes", json={"name": "Burger", "portions": 1, "allow_double": True}
    ).json()
    assert burger["factors"] == [1, 2]

    week = client.put(
        f"/api/weeks/{ISO}/slots/2/DINNER/assignment",
        json={"kind": "DISH", "dish_id": burger["id"], "factor": 2},
    ).json()
    slot = next(s for s in week["slots"] if s["day"] == 2 and s["meal"] == "DINNER")
    assert slot["assignment"]["factor"] == 2
    assert slot["assignment"]["portions"] == 2

    tripled = client.put(
        f"/api/weeks/{ISO}/slots/3/DINNER/assignment",
        json={"kind": "DISH", "dish_id": burger["id"], "factor": 3},
    )
    assert tripled.status_code == 422
    assert "verdreifachen ist bei diesem Gericht nicht vorgesehen" in tripled.json()["detail"]

def test_reroll_changes_one_slot(client, seeded):
    """Ein belegter Slot, freier Pool: würfeln liefert etwas anderes."""
    dish = client.get("/api/dishes").json()[0]
    client.put(
        f"/api/weeks/{ISO}/slots/2/DINNER/assignment",
        json={"kind": "DISH", "dish_id": dish["id"]},
    )
    after = client.post(f"/api/weeks/{ISO}/slots/2/DINNER/reroll").json()
    slot = next(s for s in after["slots"] if s["day"] == 2 and s["meal"] == "DINNER")
    assert slot["assignment"]["dish_name"] != dish["name"]


def test_reroll_says_so_when_the_pool_is_exhausted(client, seeded):
    """Bei 14 Gerichten auf 14 Slots gibt es keine Alternative - das muss man erfahren.
    Ohne Reste: sonst kocht der Planer weniger als 14 Gerichte und es bleiben welche."""
    client.put("/api/settings", json={"planner_weights": {"leftover_covers_demand": -100}})
    week = client.post(f"/api/weeks/{ISO}/propose", json={}).json()
    target = next(s for s in week["slots"] if s["assignment"])
    response = client.post(
        f"/api/weeks/{ISO}/slots/{target['day']}/{target['meal']}/reroll"
    )
    assert response.status_code == 422
    assert "Keine Alternative" in response.json()["detail"]


def test_reroll_refuses_a_pinned_slot(client, seeded):
    client.put(f"/api/weeks/{ISO}/slots/3/DINNER/pin", json={"pinned": True})
    response = client.post(f"/api/weeks/{ISO}/slots/3/DINNER/reroll")
    assert response.status_code == 422
    assert "gepinnt" in response.json()["detail"]


def test_copy_from_takes_the_grid_but_not_the_plan(client, seeded):
    week = client.get(f"/api/weeks/{ISO}").json()
    client.put(
        f"/api/weeks/{ISO}/grid",
        json=grid_payload(week, **{"1L": {"eaters_home": 0}, "0D": {"packed_portions": 1}}),
    )
    client.post(f"/api/weeks/{ISO}/propose", json={})

    target = client.post(f"/api/weeks/2026-W38/copy-from/{ISO}").json()
    by_key = {(s["day"], s["meal"]): s for s in target["slots"]}
    assert by_key[(1, "LUNCH")]["eaters_home"] == 0
    assert by_key[(0, "DINNER")]["packed_portions"] == 1
    assert all(s["assignment"] is None for s in target["slots"])


def test_fresh_take_along_survives_saving_and_copying(client):
    week = client.get(f"/api/weeks/{ISO}").json()
    saved = client.put(
        f"/api/weeks/{ISO}/grid",
        json=grid_payload(
            week,
            **{
                "0D": {"eaters_home": 1, "packed_portions": 1, "packed_fresh": True},
                "1D": {"packed_portions": 0, "packed_fresh": True},  # nichts mitzunehmen
            },
        ),
    ).json()
    by_key = {(s["day"], s["meal"]): s for s in saved["slots"]}
    assert by_key[(0, "DINNER")]["packed_fresh"] is True
    assert by_key[(1, "DINNER")]["packed_fresh"] is False

    copied = client.post(f"/api/weeks/2026-W38/copy-from/{ISO}").json()
    by_key = {(s["day"], s["meal"]): s for s in copied["slots"]}
    assert by_key[(0, "DINNER")]["packed_fresh"] is True


def test_leftovers_are_refused_where_food_is_cooked_fresh(client, seeded):
    three = next(
        d for d in client.get("/api/dishes").json() if d["portions"] == 3 and d["packable"]
    )
    client.put(
        f"/api/weeks/{ISO}/slots/0/DINNER/assignment",
        json={"kind": "DISH", "dish_id": three["id"]},
    )  # 3 Portionen für 2 Esser: eine bleibt übrig
    leftover = {
        "kind": "LEFTOVER",
        "dish_id": three["id"],
        "leftover_source_day": 0,
        "leftover_source_meal": "DINNER",
        "portions_used": 1,
    }

    def tuesday_lunch(fresh: bool) -> int:
        week = client.get(f"/api/weeks/{ISO}").json()
        client.put(
            f"/api/weeks/{ISO}/grid",
            json=grid_payload(
                week, **{"1L": {"eaters_home": 0, "packed_portions": 1, "packed_fresh": fresh}}
            ),
        )
        return client.put(f"/api/weeks/{ISO}/slots/1/LUNCH/assignment", json=leftover)

    refused = tuesday_lunch(fresh=True)
    assert refused.status_code == 422
    assert "frisch" in refused.json()["detail"]
    assert tuesday_lunch(fresh=False).status_code == 200  # vorgekocht: Reste sind recht


def test_eating_out_is_stored_as_nobody_home(client):
    """"auswärts" und "niemand da" sind dasselbe - auch für einen alten Client."""
    week = client.get(f"/api/weeks/{ISO}").json()
    saved = client.put(
        f"/api/weeks/{ISO}/grid",
        json=grid_payload(week, **{"2D": {"special": "EATING_OUT", "eaters_home": 2}}),
    ).json()
    slot = next(s for s in saved["slots"] if s["day"] == 2 and s["meal"] == "DINNER")
    assert (slot["special"], slot["eaters_home"], slot["packed_portions"]) == ("NONE", 0, 0)


def test_nobody_home_takes_the_dish_and_its_leftovers_off_the_plan(client, seeded):
    """Stand das Gericht weiter hinter der "niemand da"-Karte, landeten seine Zutaten
    trotzdem auf der Einkaufsliste."""
    three = next(
        d for d in client.get("/api/dishes").json() if d["portions"] == 3 and d["packable"]
    )
    week = client.get(f"/api/weeks/{ISO}").json()
    client.put(
        f"/api/weeks/{ISO}/grid", json=grid_payload(week, **{"1L": {"eaters_home": 1}})
    )
    client.put(
        f"/api/weeks/{ISO}/slots/0/DINNER/assignment",
        json={"kind": "DISH", "dish_id": three["id"]},
    )
    planned = client.put(
        f"/api/weeks/{ISO}/slots/1/LUNCH/assignment",
        json={
            "kind": "LEFTOVER",
            "dish_id": three["id"],
            "leftover_source_day": 0,
            "leftover_source_meal": "DINNER",
            "portions_used": 1,
        },
    ).json()
    assert client.get(f"/api/weeks/{ISO}/shopping-list").json()["items"]

    after = client.put(
        f"/api/weeks/{ISO}/grid",
        json=grid_payload(planned, **{"0D": {"eaters_home": 0, "packed_portions": 0}}),
    ).json()
    assert all(s["assignment"] is None for s in after["slots"])
    assert client.get(f"/api/weeks/{ISO}/shopping-list").json()["items"] == []


def test_nothing_can_be_planned_where_nobody_eats(client, seeded):
    week = client.get(f"/api/weeks/{ISO}").json()
    client.put(
        f"/api/weeks/{ISO}/grid", json=grid_payload(week, **{"2D": {"eaters_home": 0}})
    )
    dish = client.get("/api/dishes").json()[0]
    response = client.put(
        f"/api/weeks/{ISO}/slots/2/DINNER/assignment",
        json={"kind": "DISH", "dish_id": dish["id"]},
    )
    assert response.status_code == 422
    assert "niemand" in response.json()["detail"]

def test_diagnostics_report_the_open_slots(client, seeded):
    """Erst ab dem ersten belegten Slot sind Lücken eine Warnung."""
    assert not [
        w for w in client.get(f"/api/weeks/{ISO}/diagnostics").json()
        if w["code"] == "slot_empty"
    ]

    dish = client.get("/api/dishes").json()[0]
    client.put(
        f"/api/weeks/{ISO}/slots/0/DINNER/assignment",
        json={"kind": "DISH", "dish_id": dish["id"]},
    )
    warnings = client.get(f"/api/weeks/{ISO}/diagnostics").json()
    assert any(w["code"] == "slot_empty" for w in warnings)


def test_slots_arrive_in_the_order_people_read_them(client):
    """Mittag vor Abend - der Raster-Editor rendert in Array-Reihenfolge."""
    week = client.get(f"/api/weeks/{ISO}").json()
    order = [(slot["day"], slot["meal"]) for slot in week["slots"]]
    expected = [(day, meal) for day in range(7) for meal in ("LUNCH", "DINNER")]
    assert order == expected
