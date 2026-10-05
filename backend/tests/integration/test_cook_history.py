"""Was zählt als gekocht? Der Plan selbst - außer einem Gericht, das ausgefallen ist.

Davon lebt die Abwechslung über die Wochen ("seit 5 Wochen nicht gekocht" gibt Bonus,
"vor 1 Woche gekocht" Abzug). Bis hierhin zählte nur ein ausdrücklich bestätigtes
"gekocht", für das es keinen Knopf gab - also galt jedes Gericht jede Woche als "noch nie
gekocht".
"""

from __future__ import annotations

from datetime import date

from mealplan.db.mappers import calendar_weeks_ago

PAST = "2026-W37"  # 7.-13.9.2026, Mittwoch = 9.9.
NEXT = "2026-W38"
FUTURE = "2099-W10"
LATER = "2099-W11"


def _dish(client, *, skip: int = 0) -> dict:
    return [d for d in client.get("/api/dishes").json() if d["portions"] == 2][skip]


def _plan(client, iso: str, dish: dict, day: int = 2, meal: str = "DINNER") -> dict:
    response = client.put(
        f"/api/weeks/{iso}/slots/{day}/{meal}/assignment",
        json={"kind": "DISH", "dish_id": dish["id"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _slot(week: dict, day: int = 2, meal: str = "DINNER") -> dict:
    return next(s for s in week["slots"] if s["day"] == day and s["meal"] == meal)


def _history(client, dish: dict) -> tuple[str | None, int | None]:
    row = client.get(f"/api/dishes/{dish['id']}").json()
    return row["last_cooked"], row["weeks_since_cooked"]


def _rotation_rules(candidates: list[dict], dish: dict) -> set[str]:
    option = next(
        c for c in candidates
        if c["assignment"]["kind"] == "DISH" and c["assignment"]["dish_id"] == dish["id"]
    )
    return {c["rule"] for c in option["score"]["contributions"]}


def test_a_planned_dish_counts_as_cooked_once_its_day_has_come(client, seeded):
    dish = _dish(client)
    _plan(client, PAST, dish)

    weeks = calendar_weeks_ago(date(2026, 9, 9), date.today())
    assert _history(client, dish) == ("2026-09-09", weeks)


def test_weeks_ago_are_calendar_weeks():
    """Wie beim Planen - sonst hieße Mittwoch letzter Woche am Montag "diese Woche"."""
    monday = date(2026, 10, 5)
    assert calendar_weeks_ago(date(2026, 9, 30), monday) == 1  # Mi davor, 5 Tage
    assert calendar_weeks_ago(date(2026, 9, 28), monday) == 1  # Mo davor, 7 Tage
    assert calendar_weeks_ago(date(2026, 9, 27), monday) == 2  # So vorletzter Woche
    assert calendar_weeks_ago(monday, date(2026, 10, 11)) == 0  # dieselbe Woche


def test_a_dish_planned_for_later_has_not_been_cooked_yet(client, seeded):
    dish = _dish(client)
    _plan(client, FUTURE, dish)

    assert _history(client, dish) == (None, None)


def test_the_next_week_avoids_what_the_week_before_has_planned(client, seeded):
    dish = _dish(client)
    _plan(client, PAST, dish)
    options = client.get(f"/api/weeks/{NEXT}/slots/2/DINNER/candidates").json()
    assert "cooked_recently" in _rotation_rules(options, dish)

    # Auch im Voraus: wer Woche 11 plant, während 10 noch bevorsteht, will 10 nicht
    # wiederholen.
    _plan(client, FUTURE, dish)
    options = client.get(f"/api/weeks/{LATER}/slots/2/DINNER/candidates").json()
    assert "cooked_recently" in _rotation_rules(options, dish)


def test_a_week_is_not_its_own_history(client, seeded):
    """Sonst bekäme jedes Gericht der Woche beim Neu-Bewerten einen Abzug für sich selbst."""
    dish = _dish(client)
    _plan(client, PAST, dish)
    client.put(f"/api/weeks/{PAST}/slots/2/DINNER/pin", json={"pinned": True})

    week = client.post(f"/api/weeks/{PAST}/propose", json={"only_empty": True}).json()
    rules = {c["rule"] for c in _slot(week)["assignment"]["score"]["contributions"]}
    assert "cooked_recently" not in rules
    assert "never_cooked" in rules


def test_a_cancelled_dish_does_not_count_as_cooked(client, seeded):
    dish = _dish(client)
    before = _plan(client, PAST, dish)

    week = client.put(
        f"/api/weeks/{PAST}/slots/2/DINNER/cancelled", json={"cancelled": True}
    ).json()
    assert _slot(week)["assignment"]["cancelled"] is True
    assert _slot(week)["assignment"]["dish_name"] == dish["name"], "der Plan bleibt stehen"
    assert week["version"] == before["version"] + 1, "andere Geräte sollen es mitbekommen"
    assert _history(client, dish) == (None, None)

    week = client.put(
        f"/api/weeks/{PAST}/slots/2/DINNER/cancelled", json={"cancelled": False}
    ).json()
    assert _slot(week)["assignment"]["cancelled"] is False
    assert _history(client, dish)[0] == "2026-09-09"


def test_replanning_the_slot_drops_the_cancellation(client, seeded):
    first, second = _dish(client), _dish(client, skip=1)
    _plan(client, PAST, first)
    client.put(f"/api/weeks/{PAST}/slots/2/DINNER/cancelled", json={"cancelled": True})

    week = _plan(client, PAST, second)
    assert _slot(week)["assignment"]["cancelled"] is False
    assert _history(client, second)[0] == "2026-09-09"
    assert _history(client, first) == (None, None), "das ausgefallene bleibt ausgefallen"


def test_only_a_dish_whose_day_has_come_can_be_cancelled(client, seeded):
    dish = _dish(client)
    _plan(client, FUTURE, dish)
    ahead = client.put(
        f"/api/weeks/{FUTURE}/slots/2/DINNER/cancelled", json={"cancelled": True}
    )
    assert ahead.status_code == 422
    assert "noch nicht dran" in ahead.json()["detail"]

    empty = client.put(
        f"/api/weeks/{PAST}/slots/3/DINNER/cancelled", json={"cancelled": True}
    )
    assert empty.status_code == 422
    assert "kein Gericht" in empty.json()["detail"]


def test_a_confirmed_cooking_still_counts_without_a_plan(client, seeded):
    dish = _dish(client)
    client.post("/api/cook-log", json={"dish_id": dish["id"], "cooked_at": "2026-09-01"})
    assert _history(client, dish)[0] == "2026-09-01"
