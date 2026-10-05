"""Weiche Kriterien (general_plan.md §4) -> `ScoreBreakdown`.

Kernentscheidung aus ARCHITECTURE.md §4: Der Score ist *immer* eine Liste benannter
Beiträge, nie eine Zahl. Die Begründung in der UI ("mitnehmbar, 3 Portionen, seit 5
Wochen nicht gekocht, Lachs im Angebot") ist derselbe Datensatz, rueckwaerts gelesen -
es gibt keinen zweiten Erklaerungspfad und damit keine zweite Wahrheit.
"""

from __future__ import annotations

from decimal import Decimal

from .enums import CategoryAxis as Axis
from .leftovers import LeftoverPool, PortionLedger
from .model import (
    Contribution,
    DishSpec,
    Plan,
    PlanningSnapshot,
    ScoreBreakdown,
    SlotSpec,
)

_AXIS_LABEL = {Axis.SIDE: "Beilage", Axis.PROTEIN: "Protein", Axis.CUISINE: "Küche"}


def _ledger_for(plan: Plan, snap: PlanningSnapshot) -> PortionLedger:
    """Ledger aus dem übergebenen Plan - ohne ihn wäre jeder Überschuss "Abfall"."""
    try:
        return PortionLedger.of(plan, snap)
    except (ValueError, KeyError):
        return PortionLedger(snap)


def score(
    dish: DishSpec,
    slot: SlotSpec,
    plan: Plan,
    snap: PlanningSnapshot,
    *,
    factor: int = 1,
    ledger: PortionLedger | None = None,
) -> ScoreBreakdown:
    w = snap.weights
    ledger = ledger if ledger is not None else _ledger_for(plan, snap)
    out: list[Contribution] = [Contribution("base", 0.0, "")]

    out.extend(_variety(dish, slot, plan, snap))
    out.extend(_rotation(dish, w))
    out.extend(_rating(dish, w))
    out.extend(_offers(dish, w))
    out.extend(_portions(dish, slot, snap, factor=factor, ledger=ledger))

    # Mehraufwand ist nur der große Topf. Ein 1-Portionen-Rezept doppelt zu kochen ist
    # sein normaler Gebrauch - bestraft, würde es gegen jedes 2er-Gericht verlieren.
    if factor > 1 and dish.portions > 1:
        out.append(Contribution("doubling", w.doubling, "verdoppelt (Mehraufwand)"))

    return ScoreBreakdown.of(out)


def score_leftover(
    pool: LeftoverPool,
    slot: SlotSpec,
    snap: PlanningSnapshot,
) -> ScoreBreakdown:
    """Reste-Karte als Kandidat: kein Einkauf, kein Kochen, keine Verschwendung."""
    w = snap.weights
    dish = snap.dish(pool.dish_id)
    out: list[Contribution] = [
        Contribution("base", 0.0, ""),
        Contribution(
            "leftover_assignment",
            w.leftover_assignment,
            f"Reste von {pool.source} - kein Einkauf, kein Kochen",
        ),
    ]
    covered = min(pool.portions, slot.demand)
    if covered:
        out.append(
            Contribution(
                "leftover_covers_demand",
                w.leftover_covers_demand * (covered / max(slot.demand, 1)),
                f"deckt {covered} von {slot.demand} Portionen",
            )
        )
    if pool.portions > slot.demand:
        out.append(
            Contribution(
                "leftover_rest",
                0.0,
                f"{pool.portions - slot.demand} Portion(en) bleiben weiterhin übrig",
            )
        )
    out.extend(_rating(dish, w))
    return ScoreBreakdown.of(out)


# ------------------------------------------------------------------------- Einzelregeln


def _variety(
    dish: DishSpec, slot: SlotSpec, plan: Plan, snap: PlanningSnapshot
) -> list[Contribution]:
    """Gleiche Beilage / gleiches Protein wie am Vortag -> Abzug, gestaffelt nach Abstand.

    Die Abzuege einer Achse werden *summiert*, nicht maximiert: sonst kostet das dritte
    Brot der Woche nicht mehr als das zweite, und `diagnose()` warnt vor einer
    Wiederholung, die der Score nie bestraft hat.
    """
    w = snap.weights
    out: list[Contribution] = []
    conflicts: dict[Axis, list[tuple[float, str]]] = {}

    for other_key, assignment in plan.assignments.items():
        if other_key == slot.key or assignment.dish_id is None:
            continue
        other = snap.dish_or_none(assignment.dish_id)
        if other is None or other.id == dish.id:
            continue
        distance = abs(other_key.index - slot.key.index)
        near = distance <= w.variety_span_slots

        for axis, (adjacent_weight, week_weight) in (
            (Axis.SIDE, (w.same_side_adjacent, w.same_side_same_week)),
            (Axis.PROTEIN, (w.same_protein_adjacent, w.same_protein_same_week)),
            (Axis.CUISINE, (w.same_cuisine_adjacent, w.same_cuisine_same_week)),
        ):
            shared = dish.category(axis) & other.category(axis)
            if not shared:
                continue
            weight = week_weight
            if near:
                # Näher = strenger: von `adjacent` linear auf `week` ausblenden.
                span = w.variety_span_slots + 1
                weight = adjacent_weight * (span - distance) / span
                weight = min(weight, week_weight)
            where = "am selben Tag" if other_key.day == slot.key.day else f"{other_key}"
            conflicts.setdefault(axis, []).append(
                (weight, f"gleiche{'s' if axis is Axis.PROTEIN else ''} "
                         f"{_AXIS_LABEL[axis]} wie {where} ({sorted(shared)[0]})")
            )

    for axis, entries in conflicts.items():
        total = sum(weight for weight, _ in entries)
        text = min(entries, key=lambda e: e[0])[1]
        if len(entries) > 1:
            text += f" (+{len(entries) - 1} weitere)"
        out.append(Contribution(f"variety_{axis.value.lower()}", round(total, 2), text))
    return out


def _rotation(dish: DishSpec, w) -> list[Contribution]:
    weeks = dish.weeks_since_cooked
    if weeks is None:
        return [Contribution("never_cooked", w.never_cooked_bonus, "noch nie gekocht")]
    if weeks <= 2:
        return [
            Contribution(
                "cooked_recently",
                w.cooked_within_two_weeks,
                f"vor {weeks} Woche{'n' if weeks != 1 else ''} gekocht"
                if weeks
                else "diese Woche schon gekocht",
            )
        ]
    bonus = min(weeks * w.rotation_per_week, w.rotation_cap)
    return [Contribution("rotation", round(bonus, 2), f"seit {weeks} Wochen nicht gekocht")]


def _rating(dish: DishSpec, w) -> list[Contribution]:
    if dish.rating is None:
        return []
    delta = (dish.rating - 3) * w.rating_per_star
    if delta == 0:
        return []
    stars = "★" * dish.rating
    return [Contribution("rating", round(delta, 2), f"Bewertung {stars}")]


def _offers(dish: DishSpec, w) -> list[Contribution]:
    if dish.offer_savings_eur <= 0:
        return []
    bonus = min(float(dish.offer_savings_eur) * w.offer_per_euro, w.offer_cap)
    savings = f"{dish.offer_savings_eur:.2f}".replace(".", ",")
    return [
        Contribution("offers", round(bonus, 2), f"Zutaten im Angebot (spart {savings} €)")
    ]


def _portions(
    dish: DishSpec,
    slot: SlotSpec,
    snap: PlanningSnapshot,
    *,
    factor: int,
    ledger: PortionLedger,
) -> list[Contribution]:
    w = snap.weights
    produced = dish.portions_for(factor)
    surplus = produced - slot.demand
    if surplus == 0:
        return [
            Contribution("exact_portions", w.exact_portions, f"{produced} Portionen passen genau")
        ]
    if surplus < 0:
        return []

    wasted = ledger.would_waste(slot.key, surplus)
    used = surplus - wasted
    out: list[Contribution] = []
    if used > 0:
        # Bewusst nur ein kleiner Bonus: der eigentliche Gewinn entsteht erst, wenn ein
        # spaeterer Slot die Reste wirklich *nimmt* - das bewertet `score_leftover`.
        # Ein großer Bonus hier würde jedes Gericht ins Verdoppeln treiben.
        out.append(
            Contribution(
                "surplus_usable",
                round(w.surplus_usable_per_portion * used, 2),
                f"{used} Portion{'en' if used != 1 else ''} Reste für einen späteren Slot",
            )
        )
    if wasted > 0:
        out.append(
            Contribution(
                "waste",
                round(w.waste_per_portion * wasted, 2),
                f"{wasted} Portion{'en' if wasted != 1 else ''} bleibt übrig",
            )
        )
    return out


def offer_savings(dish: DishSpec) -> Decimal:
    return dish.offer_savings_eur
