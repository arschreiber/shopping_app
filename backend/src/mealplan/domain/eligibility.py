"""Harte Kriterien (general_plan.md §4): scheidet ein Gericht für einen Slot aus?

Gibt bei Ablehnung *alle* Gruende zurück, nicht nur den ersten - die Kandidatenliste
zeigt sie an, damit "warum ist mein Gericht nicht dabei?" beantwortbar bleibt.
"""

from __future__ import annotations

from .enums import Effort, SlotSpecial, TimeBudget
from .model import DishSpec, Eligibility, Plan, SlotSpec

# Welcher Aufwand passt in welches Zeitbudget?
_EFFORT_FITS: dict[TimeBudget, frozenset[Effort]] = {
    TimeBudget.PLENTY: frozenset({Effort.QUICK, Effort.NORMAL, Effort.ELABORATE}),
    TimeBudget.LITTLE: frozenset({Effort.QUICK}),
    TimeBudget.NONE: frozenset(),
}

_EFFORT_LABEL = {
    Effort.QUICK: "schnell",
    Effort.NORMAL: "normal",
    Effort.ELABORATE: "aufwendig",
}
_BUDGET_LABEL = {
    TimeBudget.PLENTY: "viel Zeit",
    TimeBudget.LITTLE: "wenig Zeit",
    TimeBudget.NONE: "keine Zeit",
}


def eligible(
    dish: DishSpec,
    slot: SlotSpec,
    plan: Plan,
    *,
    doubled: bool = False,
) -> Eligibility:
    reasons: list[str] = []

    if slot.special is SlotSpecial.EATING_OUT:
        return Eligibility.no("Slot ist als 'auswärts' markiert")
    if slot.demand == 0:
        return Eligibility.no("Slot braucht keine Portionen")

    if not dish.suits(slot.key.meal):
        meal = "Mittag" if slot.key.meal_order == 0 else "Abend"
        reasons.append(f"nicht für {meal} vorgesehen")

    if dish.effort not in _EFFORT_FITS[slot.time_budget]:
        reasons.append(
            f"Aufwand '{_EFFORT_LABEL[dish.effort]}' passt nicht zu "
            f"'{_BUDGET_LABEL[slot.time_budget]}'"
        )

    if slot.packed_portions > 0 and not dish.packable:
        reasons.append("nicht mitnehmbar, Slot braucht Mitnehm-Portionen")

    if doubled and not dish.can_double:
        reasons.append("nur 2-Portionen-Gerichte sind verdoppelbar")

    available = dish.portions_for(doubled=doubled)
    if available < slot.demand:
        reasons.append(
            f"{available} Portionen reichen nicht für {slot.demand} "
            f"({slot.eaters_home} zu Hause + {slot.packed_portions} mitnehmen)"
        )

    # Ein Gericht pro Woche nur einmal kochen. Wiederholung läuft ueber Reste oder
    # Verdoppeln, nicht ueber zweimaliges Kochen.
    for key, assignment in plan.assignments.items():
        if key != slot.key and assignment.cooks and assignment.dish_id == dish.id:
            reasons.append("diese Woche schon eingeplant")
            break

    return Eligibility.no(*reasons) if reasons else Eligibility.yes()
