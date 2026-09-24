"""Kandidatenlisten und Auto-Vorschlag (ARCHITECTURE.md §4, general_plan.md §4).

Bewusst kein Constraint-Solver: greedy in Reihenfolge der Slot-Schwierigkeit, danach
lokale Suche (paarweise Tauschs + Einzel-Reroll) mit harter Iterationsgrenze. Bei ~100
Gerichten x 14 Slots liegt das deutlich unter einer Sekunde.

Der Zufall ist immer geseeded (`week.planner_seed`): jeder Vorschlag ist reproduzierbar,
"neu würfeln" ist ein neuer Seed - und Tests sind stabil.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .eligibility import eligible
from .enums import AssignmentKind, SlotSpecial, TimeBudget
from .leftovers import PortionLedger
from .model import (
    Assignment,
    Candidate,
    Plan,
    PlanningSnapshot,
    SlotKey,
    SlotSpec,
)
from .scoring import score, score_leftover

MAX_LOCAL_SEARCH_ITERATIONS = 200
REROLL_POOL = 5  # aus wie vielen Top-Kandidaten "neu würfeln" zieht


# ---------------------------------------------------------------------- Kandidatenliste


def candidates(
    slot: SlotSpec,
    plan: Plan,
    snap: PlanningSnapshot,
    *,
    ledger: PortionLedger | None = None,
    include_ineligible: bool = False,
) -> list[Candidate]:
    """Alle zulässigen Belegungen für einen Slot, nach Score sortiert."""
    if not slot.needs_cooking:
        return []
    ledger = ledger if ledger is not None else PortionLedger.of(plan.without(slot.key), snap)
    out: list[Candidate] = []

    for pool in ledger.available_at(slot.key):
        dish = snap.dish_or_none(pool.dish_id)
        if dish is None:
            continue
        if slot.packed_portions > 0 and not dish.packable:
            continue
        if pool.portions < slot.demand:
            continue
        breakdown = score_leftover(pool, slot, snap)
        portions = min(pool.portions, slot.demand)
        out.append(
            Candidate(
                assignment=Assignment.leftover(pool.source, dish.id, portions, score=breakdown),
                label=f"Reste: {dish.name} ({pool.source})",
                score=breakdown,
                warnings=_warnings(breakdown),
            )
        )

    for dish in snap.dishes:
        for doubled in (False, True):
            if doubled and not dish.can_double:
                continue
            verdict = eligible(dish, slot, plan, doubled=doubled)
            if not verdict.ok:
                if include_ineligible and not doubled:
                    out.append(
                        Candidate(
                            assignment=Assignment.dish(dish.id),
                            label=dish.name,
                            score=score(dish, slot, plan, snap, ledger=ledger),
                            warnings=verdict.reasons,
                        )
                    )
                continue
            breakdown = score(dish, slot, plan, snap, doubled=doubled, ledger=ledger)
            out.append(
                Candidate(
                    assignment=Assignment.dish(dish.id, doubled=doubled, score=breakdown),
                    label=f"{dish.name} (doppelt)" if doubled else dish.name,
                    score=breakdown,
                    warnings=_warnings(breakdown),
                )
            )

    eligible_only = [c for c in out if not _is_ineligible(c)]
    eligible_only.sort(key=lambda c: (-c.total, c.label))
    if not include_ineligible:
        return eligible_only
    rest = [c for c in out if _is_ineligible(c)]
    rest.sort(key=lambda c: c.label)
    return eligible_only + rest


def _is_ineligible(candidate: Candidate) -> bool:
    return candidate.assignment.score is None


_WARNING_RULES = {"waste", "leftover_short", "variety_side", "variety_protein"}


def _warnings(breakdown) -> tuple[str, ...]:
    return tuple(
        c.text
        for c in breakdown.contributions
        if c.rule in _WARNING_RULES and c.delta <= -4.0
    )


# ------------------------------------------------------------------------ Auto-Vorschlag


@dataclass(frozen=True, slots=True)
class _Difficulty:
    slot: SlotSpec
    pool_size: int

    @property
    def rank(self) -> tuple:
        """Erst die schwierigen Slots: Mitnehm-Bedarf, knappe Zeit, kleiner Pool."""
        return (
            -self.slot.packed_portions,
            0 if self.slot.time_budget is TimeBudget.LITTLE else 1,
            self.pool_size,
            self.slot.key.index,
        )


def propose(
    snap: PlanningSnapshot,
    pinned: dict[SlotKey, Assignment] | None = None,
    *,
    seed: int = 0,
    keep: dict[SlotKey, Assignment] | None = None,
) -> Plan:
    """Vorschlag für die ganze Woche. `pinned` bleibt fest, `keep` ebenfalls.

    `keep` sind Zuweisungen, die stehen bleiben sollen, ohne gepinnt zu sein - so
    funktioniert "nur leere Slots vorschlagen".
    """
    rng = random.Random(seed)
    fixed: dict[SlotKey, Assignment] = {**(keep or {}), **(pinned or {})}

    plan = Plan()
    ledger = PortionLedger(snap)

    # 1. Fixierte Slots zuerst buchen - sie verändern den Ledger für alle anderen.
    for key in sorted(fixed, key=lambda k: k.index):
        plan = plan.with_(key, fixed[key])
    _replay(plan, snap, ledger, only=set(fixed))

    # 2. Offene Slots nach Schwierigkeit sortieren.
    open_slots = [
        s
        for s in snap.slots
        if s.key not in fixed and s.needs_cooking and s.special is not SlotSpecial.EATING_OUT
    ]
    ranked = sorted(
        (
            _Difficulty(s, len(candidates(s, Plan(), snap, ledger=PortionLedger(snap))))
            for s in open_slots
        ),
        key=lambda d: d.rank,
    )

    # 3. Greedy fuellen.
    for entry in ranked:
        slot = entry.slot
        options = candidates(slot, plan, snap, ledger=ledger)
        if slot.special is SlotSpecial.FROM_PANTRY:
            options = [c for c in options if c.assignment.kind is AssignmentKind.LEFTOVER]
        if not options:
            plan = plan.with_(slot.key, Assignment.empty())
            continue
        chosen = _pick(options, rng)
        plan = plan.with_(slot.key, chosen.assignment)
        _book(chosen.assignment, slot, snap, ledger)

    # 4. Lokale Suche.
    plan = _improve(plan, snap, fixed=set(fixed))
    return rescore(plan, snap)


def _pick(options: list[Candidate], rng: random.Random) -> Candidate:
    """Bester Kandidat, mit leichtem Zufall bei praktisch gleichwertigen Optionen."""
    best = options[0].total
    tied = [c for c in options if best - c.total <= 0.5]
    return rng.choice(tied) if len(tied) > 1 else options[0]


def reroll(snap: PlanningSnapshot, plan: Plan, key: SlotKey, *, seed: int) -> Plan:
    """"Neu würfeln" für einen Slot: zieht aus den Top-Kandidaten, nie das Gleiche."""
    rng = random.Random(seed)
    slot = snap.slot(key)
    current = plan.get(key)
    without = plan.without(key)
    options = candidates(slot, without, snap)
    alternatives = [c for c in options if not c.assignment.same_choice(current)][:REROLL_POOL]
    if not alternatives:
        return plan
    chosen = rng.choice(alternatives)
    return rescore(without.with_(key, chosen.assignment), snap)


# ------------------------------------------------------------------------- Lokale Suche


def _improve(plan: Plan, snap: PlanningSnapshot, *, fixed: set[SlotKey]) -> Plan:
    """Paarweise Tauschs, solange der Gesamtscore steigt."""
    best = rescore(plan, snap)
    best_total = best.total_score()
    iterations = 0

    swappable = [
        key
        for key, assignment in best.items()
        if key not in fixed and assignment.kind is AssignmentKind.DISH
    ]

    improved = True
    while improved and iterations < MAX_LOCAL_SEARCH_ITERATIONS:
        improved = False
        for i, left in enumerate(swappable):
            for right in swappable[i + 1 :]:
                iterations += 1
                if iterations >= MAX_LOCAL_SEARCH_ITERATIONS:
                    break
                swapped = _try_swap(best, snap, left, right)
                if swapped is None:
                    continue
                total = swapped.total_score()
                if total > best_total + 1e-9:
                    best, best_total, improved = swapped, total, True
            if improved:
                break
    return best


def _try_swap(plan: Plan, snap: PlanningSnapshot, left: SlotKey, right: SlotKey) -> Plan | None:
    """Tauscht zwei Gerichte, wenn beide im anderen Slot zulässig bleiben."""
    a, b = plan.get(left), plan.get(right)
    if a.dish_id is None or b.dish_id is None:
        return None

    # Slots, aus denen eine Reste-Karte zieht, nicht anfassen - der Tausch könnte die
    # Quelle wegnehmen.
    sources = {
        x.leftover_source for x in plan.assignments.values() if x.leftover_source is not None
    }
    if left in sources or right in sources:
        return None

    stripped = plan.without(left).without(right)
    left_slot, right_slot = snap.slot(left), snap.slot(right)
    if not eligible(snap.dish(b.dish_id), left_slot, stripped, doubled=b.doubled).ok:
        return None
    if not eligible(snap.dish(a.dish_id), right_slot, stripped, doubled=a.doubled).ok:
        return None

    candidate = stripped.with_(
        left, Assignment.dish(b.dish_id, doubled=b.doubled)
    ).with_(right, Assignment.dish(a.dish_id, doubled=a.doubled))
    try:
        PortionLedger.of(candidate, snap)
    except ValueError:
        return None
    return rescore(candidate, snap)


# --------------------------------------------------------------------------- Rescoring


def rescore(plan: Plan, snap: PlanningSnapshot) -> Plan:
    """Rechnet alle Score-Begruendungen im Kontext des *fertigen* Plans neu.

    Während des Greedy-Fuellens kennt ein Slot die späteren Slots noch nicht; die
    eingefrorene Begründung soll aber den fertigen Plan erklaeren.
    """
    ledger = PortionLedger.of(plan, snap)
    out = plan
    for key, assignment in plan.items():
        slot = snap.slot(key)
        if assignment.kind is AssignmentKind.DISH and assignment.dish_id is not None:
            breakdown = score(
                snap.dish(assignment.dish_id),
                slot,
                plan.without(key),
                snap,
                doubled=assignment.doubled,
                ledger=ledger,
            )
            out = out.with_(key, Assignment(**{**_as_dict(assignment), "score": breakdown}))
        elif assignment.kind is AssignmentKind.LEFTOVER and assignment.leftover_source:
            pools = [
                p
                for p in PortionLedger.of(plan.without(key), snap).available_at(key)
                if p.source == assignment.leftover_source
            ]
            if pools:
                breakdown = score_leftover(pools[0], slot, snap)
                out = out.with_(key, Assignment(**{**_as_dict(assignment), "score": breakdown}))
    return out


def _as_dict(assignment: Assignment) -> dict:
    return {
        "kind": assignment.kind,
        "dish_id": assignment.dish_id,
        "doubled": assignment.doubled,
        "leftover_source": assignment.leftover_source,
        "portions_used": assignment.portions_used,
        "score": assignment.score,
    }


# ----------------------------------------------------------------------- Ledger-Buchung


def _book(
    assignment: Assignment, slot: SlotSpec, snap: PlanningSnapshot, ledger: PortionLedger
) -> None:
    if assignment.kind is AssignmentKind.DISH and assignment.dish_id is not None:
        dish = snap.dish(assignment.dish_id)
        ledger.record_cook(
            slot.key, dish.id, dish.portions_for(doubled=assignment.doubled), slot.demand
        )
    elif assignment.kind is AssignmentKind.LEFTOVER and assignment.leftover_source:
        ledger.record_leftover_use(assignment.leftover_source, assignment.portions_used or 0)


def _replay(
    plan: Plan, snap: PlanningSnapshot, ledger: PortionLedger, *, only: set[SlotKey]
) -> None:
    """Bucht bestehende Zuweisungen in den Ledger - Kochen vor Reste-Entnahme."""
    for key, assignment in plan.items():
        if key in only and assignment.kind is AssignmentKind.DISH:
            _book(assignment, snap.slot(key), snap, ledger)
    for key, assignment in plan.items():
        if key in only and assignment.kind is AssignmentKind.LEFTOVER:
            _book(assignment, snap.slot(key), snap, ledger)
