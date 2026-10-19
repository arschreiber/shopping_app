"""Plan-Warnungen (general_plan.md §5 Phase 1).

"dreimal Reis", "Dienstag nichts zum Mitnehmen", "Aufwand passt nicht zur Zeit",
"Portion bleibt übrig". Die Warnungen sind das Sicherheitsnetz gegen den
Auto-Vorschlag - sie erklaeren, was der Score nur gewichtet hat.
"""

from __future__ import annotations

from collections import Counter

from .eligibility import eligible
from .enums import AssignmentKind, CategoryAxis, SlotSpecial, TimeBudget, WarningLevel
from .leftovers import PortionLedger
from .model import Plan, PlanningSnapshot, PlanWarning

MAX_SAME_CATEGORY_PER_WEEK = 2
SMALL_POOL_THRESHOLD = 3

_AXIS_LABEL = {
    CategoryAxis.SIDE: "Beilage",
    CategoryAxis.PROTEIN: "Protein",
    CategoryAxis.CUISINE: "Küche",
}


def diagnose(plan: Plan, snap: PlanningSnapshot) -> list[PlanWarning]:
    out: list[PlanWarning] = []
    out += _unfilled(plan, snap)
    out += _packed_demand(plan, snap)
    out += _effort_mismatch(plan, snap)
    out += _repetition(plan, snap)
    out += _waste(plan, snap)
    out += _small_pool(plan, snap)
    return out


def _unfilled(plan: Plan, snap: PlanningSnapshot) -> list[PlanWarning]:
    """Offene Slots melden - aber nicht in einer noch unberührten Woche.

    Wer die Woche gerade geöffnet hat, weiß, dass nichts drinsteht: die leeren Karten
    sagen es. Vierzehn Warnungen darüber machen die Liste unbrauchbar für das, wofür sie
    da ist - echte Probleme im halbfertigen Plan.
    """
    if not any(not a.is_empty for a in plan.assignments.values()):
        return []
    out = []
    for slot in snap.slots:
        if not slot.needs_cooking or slot.special is not SlotSpecial.NONE:
            continue
        if plan.get(slot.key).is_empty:
            # Bei "keine Zeit" hilft nicht "etwas wählen", sondern vorher mehr kochen.
            text = (
                f"{slot.key}: keine Zeit, aber keine Reste da - vorher "
                f"{slot.demand} Portion(en) mehr kochen"
                if slot.time_budget is TimeBudget.NONE
                else f"{slot.key}: noch nichts geplant ({slot.demand} Portionen offen)"
            )
            out.append(PlanWarning(WarningLevel.WARN, "slot_empty", text, slot.key))
    return out


def _packed_demand(plan: Plan, snap: PlanningSnapshot) -> list[PlanWarning]:
    """Slot braucht Mitnehm-Portionen, das Gericht kann das nicht - oder sie sollen frisch
    sein, und es stehen Reste drin (das Raster wurde nach der Planung geändert)."""
    out = []
    for slot in snap.slots:
        if slot.packed_portions == 0:
            continue
        assignment = plan.get(slot.key)
        dish = snap.dish_or_none(assignment.dish_id)
        if assignment.is_empty:
            out.append(
                PlanWarning(
                    WarningLevel.ERROR,
                    "packed_missing",
                    f"{slot.key}: {slot.packed_portions} Portion(en) zum Mitnehmen, "
                    "aber nichts geplant",
                    slot.key,
                )
            )
        elif dish is not None and not dish.packable:
            out.append(
                PlanWarning(
                    WarningLevel.ERROR,
                    "not_packable",
                    f"{slot.key}: {dish.name} ist nicht mitnehmbar",
                    slot.key,
                )
            )
        elif assignment.kind is AssignmentKind.LEFTOVER and slot.fresh_only:
            out.append(
                PlanWarning(
                    WarningLevel.ERROR,
                    "fresh_leftover",
                    f"{slot.key}: soll frisch mitgenommen werden, geplant sind aber Reste",
                    slot.key,
                )
            )
    return out


def _effort_mismatch(plan: Plan, snap: PlanningSnapshot) -> list[PlanWarning]:
    out = []
    for slot in snap.slots:
        assignment = plan.get(slot.key)
        if assignment.kind is not AssignmentKind.DISH or assignment.dish_id is None:
            continue
        dish = snap.dish(assignment.dish_id)
        verdict = eligible(dish, slot, plan.without(slot.key), factor=assignment.factor)
        if not verdict.ok:
            out.append(
                PlanWarning(
                    WarningLevel.WARN,
                    "not_eligible",
                    f"{slot.key}: {dish.name} - {', '.join(verdict.reasons)}",
                    slot.key,
                )
            )
    return out


def _repetition(plan: Plan, snap: PlanningSnapshot) -> list[PlanWarning]:
    """"dreimal Reis": zählt Kategorien ueber die gekochten Gerichte der Woche."""
    out = []
    for axis in (CategoryAxis.SIDE, CategoryAxis.PROTEIN):
        counter: Counter[str] = Counter()
        for assignment in plan.assignments.values():
            if assignment.kind is not AssignmentKind.DISH or assignment.dish_id is None:
                continue
            dish = snap.dish_or_none(assignment.dish_id)
            if dish is None:
                continue
            counter.update(dish.category(axis))
        for name, count in counter.items():
            if count > MAX_SAME_CATEGORY_PER_WEEK:
                out.append(
                    PlanWarning(
                        WarningLevel.WARN,
                        "repetition",
                        f"{count}× {name} diese Woche ({_AXIS_LABEL[axis]})",
                    )
                )
    return out


def _waste(plan: Plan, snap: PlanningSnapshot) -> list[PlanWarning]:
    try:
        ledger = PortionLedger.of(plan, snap)
    except ValueError as exc:
        return [PlanWarning(WarningLevel.ERROR, "ledger_broken", str(exc))]
    out = []
    for pool in ledger.wasted():
        dish = snap.dish_or_none(pool.dish_id)
        name = dish.name if dish else "Gericht"
        out.append(
            PlanWarning(
                WarningLevel.INFO,
                "leftover_unused",
                f"{pool.source}: {pool.portions} Portion(en) {name} bleiben übrig",
                pool.source,
            )
        )
    return out


def _small_pool(plan: Plan, snap: PlanningSnapshot) -> list[PlanWarning]:
    """Warnung bei zu kleinem Kandidatenpool (general_plan.md §8 Nr. 7)."""
    from .planner import candidates

    out = []
    for slot in snap.slots:
        if not slot.needs_cooking or slot.special is not SlotSpecial.NONE:
            continue
        if slot.time_budget is TimeBudget.NONE:
            continue  # dort gibt es ohnehin nur Reste - eine Auswahl ist nicht gemeint
        count = len(candidates(slot, plan.without(slot.key), snap))
        if count < SMALL_POOL_THRESHOLD:
            out.append(
                PlanWarning(
                    WarningLevel.INFO,
                    "small_pool",
                    f"{slot.key}: nur {count} passende Gerichte - Vorschlag ist kaum eine Wahl",
                    slot.key,
                )
            )
    return out
