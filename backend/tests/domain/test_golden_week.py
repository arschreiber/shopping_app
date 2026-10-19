"""Golden-File-Test von `propose()` auf einer echten Woche (ARCHITECTURE.md §9).

Zweck: Eine Gewichtungsaenderung (Spike 4) erzeugt einen *lesbaren* Diff, kein
Zahlenraetsel. Zum Aktualisieren:

    UPDATE_GOLDEN=1 uv run pytest tests/domain/test_golden_week.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import full_week, slot, snapshot
from mealplan.domain.diagnostics import diagnose
from mealplan.domain.enums import AssignmentKind, Meal, SlotSpecial, TimeBudget
from mealplan.domain.planner import propose
from mealplan.domain.render import render_plan, render_warnings

GOLDEN = Path(__file__).parent / "golden" / "week_office_days.txt"
SEED = 20260907

pytestmark = pytest.mark.optimizer  # die Woche, wie die App sie vorschlägt


def realistic_week(big_pool):
    """Eine realistische Woche: Mo+Do Büro (Mittag mitnehmen), Mi wenig Zeit, Fr auswärts."""
    overrides = {
        # Montag: Einkaufstag, Mittag aus Vorhandenem
        "0L": slot(0, Meal.LUNCH, eaters_home=2, special=SlotSpecial.FROM_PANTRY),
        # Montag Abend kocht die Mitnehm-Portion für Dienstag mit
        "0D": slot(0, Meal.DINNER, eaters_home=2, packed_portions=1),
        "1L": slot(1, Meal.LUNCH, eaters_home=0),  # im Büro
        "2L": slot(2, Meal.LUNCH, eaters_home=2, time_budget=TimeBudget.LITTLE),
        "2D": slot(2, Meal.DINNER, eaters_home=2, time_budget=TimeBudget.LITTLE),
        "3D": slot(3, Meal.DINNER, eaters_home=2, packed_portions=2),
        "4L": slot(4, Meal.LUNCH, eaters_home=0),  # im Büro
        "4D": slot(4, Meal.DINNER, eaters_home=0, special=SlotSpecial.EATING_OUT),
    }
    return snapshot(full_week(**overrides), big_pool)


def test_golden_week(big_pool):
    snap = realistic_week(big_pool)
    plan = propose(snap, seed=SEED)
    rendered = (
        render_plan(plan, snap)
        + "\n\nWarnungen:\n"
        + render_warnings(diagnose(plan, snap))
        + "\n"
    )

    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(rendered, encoding="utf-8")

    assert GOLDEN.exists(), "Golden-File fehlt - mit UPDATE_GOLDEN=1 erzeugen"
    assert rendered == GOLDEN.read_text(encoding="utf-8")


# Der Optimierer rechnet pro Vorschlag ~2 s wie in der App: wenige Seeds, dafür echt.
@pytest.mark.parametrize("seed", [1])
def test_the_office_week_is_actually_solved(big_pool, seed):
    """Nicht nur stabil, sondern richtig: Mitnehm-Bedarf gedeckt, kein Slot leer - bei
    jedem Zufallswert, denn jeder Klick auf "Woche vorschlagen" zieht einen neuen."""
    snap = realistic_week(big_pool)
    plan = propose(snap, seed=seed)

    for s in snap.slots:
        assignment = plan.get(s.key)
        if s.special is SlotSpecial.EATING_OUT or s.demand == 0:
            assert assignment.is_empty, f"{s.key} sollte leer bleiben"
            continue
        if s.special is SlotSpecial.FROM_PANTRY:
            # "aus Vorhandenem": der Auto-Vorschlag laesst den Slot den Menschen -
            # ein Gericht, für das nichts eingekauft wird, wäre eine Falle.
            assert assignment.kind is not AssignmentKind.DISH
            continue
        assert not assignment.is_empty, f"{s.key} blieb leer"
        if s.packed_portions > 0:
            dish = snap.dish(assignment.dish_id)
            assert dish.packable, f"{s.key}: {dish.name} ist nicht mitnehmbar"
            assert dish.portions_for(assignment.factor) >= s.demand
