"""Harte Kriterien (general_plan.md §4): scheidet ein Gericht für einen Slot aus?

Gibt bei Ablehnung *alle* Gruende zurück, nicht nur den ersten - die Kandidatenliste
zeigt sie an, damit "warum ist mein Gericht nicht dabei?" beantwortbar bleibt.
"""

from __future__ import annotations

from .enums import Effort, SlotSpecial, TimeBudget
from .model import DishSpec, Eligibility, Plan, SlotSpec

# Welcher Aufwand passt in welches Zeitbudget?
_EFFORT_FITS: dict[TimeBudget, frozenset[Effort]] = {
    TimeBudget.NORMAL: frozenset({Effort.QUICK, Effort.NORMAL}),
    TimeBudget.LITTLE: frozenset({Effort.QUICK}),
    TimeBudget.NONE: frozenset(),  # nur Reste
}

_EFFORT_LABEL = {
    Effort.QUICK: "schnell",
    Effort.NORMAL: "normal",
}
_BUDGET_LABEL = {
    TimeBudget.NORMAL: "normale Zeit",
    TimeBudget.LITTLE: "wenig Zeit",
    TimeBudget.NONE: "keine Zeit",
}


def eligible(
    dish: DishSpec,
    slot: SlotSpec,
    plan: Plan,
    *,
    factor: int = 1,
) -> Eligibility:
    reasons: list[str] = []

    if slot.special is SlotSpecial.EATING_OUT:
        return Eligibility.no("Slot ist als 'auswärts' markiert")
    if slot.demand == 0:
        return Eligibility.no("Slot braucht keine Portionen")

    if not dish.suits(slot.key.meal):
        meal = "Mittag" if slot.key.meal_order == 0 else "Abend"
        reasons.append(f"nicht für {meal} vorgesehen")

    if slot.time_budget is TimeBudget.NONE:
        reasons.append("keine Zeit - hier gibt es nur Reste")
    elif dish.effort not in _EFFORT_FITS[slot.time_budget]:
        reasons.append(
            f"Aufwand '{_EFFORT_LABEL[dish.effort]}' passt nicht zu "
            f"'{_BUDGET_LABEL[slot.time_budget]}'"
        )

    if slot.packed_portions > 0 and not dish.packable:
        reasons.append("nicht mitnehmbar, Slot braucht Mitnehm-Portionen")

    if factor not in dish.factors:
        reasons.append(factor_reason(dish, factor))

    available = dish.portions_for(factor)
    if not dish.reheatable and available > slot.demand:
        rest = available - slot.demand
        reasons.append(
            f"nicht aufwärmbar - {rest} Portion{'en blieben' if rest > 1 else ' bliebe'} übrig"
        )
    if available < slot.demand:
        reasons.append(
            f"{available} Portionen reichen nicht für {slot.demand} "
            f"({slot.eaters_home} zu Hause + {slot.packed_portions} mitnehmen)"
        )

    # Ein Gericht pro Woche nur einmal kochen. Wiederholung läuft ueber Reste oder
    # Vervielfachen, nicht ueber zweimaliges Kochen.
    for key, assignment in plan.assignments.items():
        if key != slot.key and assignment.cooks and assignment.dish_id == dish.id:
            reasons.append("diese Woche schon eingeplant")
            break

    return Eligibility.no(*reasons) if reasons else Eligibility.yes()



def factor_reason(dish: DishSpec, factor: int) -> str:
    """Warum dieses Gericht nicht so oft auf einmal gekocht wird."""
    if dish.portions == 3:
        return "3-Portionen-Gerichte werden nicht vervielfacht"
    if dish.portions == 2 and factor > 2:
        return "2-Portionen-Gerichte werden höchstens verdoppelt"
    verb = {2: "verdoppeln", 3: "verdreifachen"}.get(factor, f"{factor}-fach kochen")
    return f"{verb} ist bei diesem Gericht nicht vorgesehen"
