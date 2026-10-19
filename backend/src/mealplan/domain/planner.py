"""Kandidatenlisten und Auto-Vorschlag (ARCHITECTURE.md §4, general_plan.md §4).

Bewusst kein Constraint-Solver: greedy in Reihenfolge der Slot-Schwierigkeit, danach
lokale Suche (paarweise Tauschs + Einzel-Reroll) mit harter Iterationsgrenze. Bei ~100
Gerichten x 14 Slots liegt das deutlich unter einer Sekunde.

Der Zufall ist immer geseeded (`week.planner_seed`): jeder Vorschlag ist reproduzierbar,
und Tests sind stabil. Für Abwechslung sorgt ein neuer Seed pro Klick (services/planning.py)
plus `weights.randomness`: zufällige Zusatzpunkte, die nur beim Auswählen zählen - die
angezeigte Begründung bleibt die echte Passung.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .eligibility import eligible
from .enums import AssignmentKind, SlotSpecial, TimeBudget
from .leftovers import PortionLedger
from .model import (
    FACTOR_WORD,
    Assignment,
    Candidate,
    Plan,
    PlanningSnapshot,
    SlotKey,
    SlotSpec,
)
from .optimizer import optimize
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

    for pool in [] if slot.fresh_only else ledger.available_at(slot.key):
        dish = snap.dish_or_none(pool.dish_id)
        if dish is None:
            continue
        if slot.packed_portions > 0 and not dish.packable:
            continue
        if pool.portions < slot.demand:
            continue
        breakdown = score_leftover(
            pool, slot, snap, repeat=_earlier_leftover_meal(plan, pool.source, slot.key)
        )
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
        rejected = None
        fits = False
        for factor in dish.factors:
            verdict = eligible(dish, slot, plan, factor=factor)
            if not verdict.ok:
                rejected = verdict  # die Faktoren steigen: der größte erklärt am meisten
                continue
            fits = True
            breakdown = score(dish, slot, plan, snap, factor=factor, ledger=ledger)
            word = FACTOR_WORD.get(factor)
            out.append(
                Candidate(
                    assignment=Assignment.dish(dish.id, factor=factor, score=breakdown),
                    label=f"{dish.name} ({word})" if word else dish.name,
                    score=breakdown,
                    warnings=_warnings(breakdown),
                )
            )
        # "Passt nicht" nur, wenn das Gericht in *keiner* Größe passt: ein Burger für
        # eine Person ist kein Ausschluss, wenn er doppelt gekocht den Slot deckt.
        if include_ineligible and not fits and rejected is not None:
            out.append(
                Candidate(
                    assignment=Assignment.dish(dish.id),
                    label=dish.name,
                    score=score(dish, slot, plan, snap, ledger=ledger),
                    warnings=rejected.reasons,
                )
            )

    eligible_only = [c for c in out if not _is_ineligible(c)]
    eligible_only.sort(key=lambda c: (-c.total, c.label))
    if not include_ineligible:
        return eligible_only
    rest = [c for c in out if _is_ineligible(c)]
    rest.sort(key=lambda c: c.label)
    return eligible_only + rest


def _earlier_leftover_meal(plan: Plan, source: SlotKey, key: SlotKey) -> bool:
    """Isst eine frühere Mahlzeit schon Reste aus demselben Topf?"""
    return any(
        other.index < key.index and assignment.leftover_source == source
        for other, assignment in plan.items()
        if other != key
    )


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

    Der Optimierer plant die Woche als Ganzes (optimizer.py); der Greedy-Plan ist seine
    Startlösung und bleibt, falls er keine bessere findet.
    """
    fixed: dict[SlotKey, Assignment] = {**(keep or {}), **(pinned or {})}
    greedy = propose_greedy(snap, fixed, seed=seed)
    found = optimize(snap, fixed, seed=seed, hint=greedy)
    if found is None:
        return greedy
    best = rescore(found, snap)
    return best if best.total_score() > greedy.total_score() else greedy


def propose_greedy(
    snap: PlanningSnapshot, fixed: dict[SlotKey, Assignment], *, seed: int = 0
) -> Plan:
    """Mahlzeit für Mahlzeit, die schwierigsten zuerst, danach paarweise tauschen.

    Schnell und ordentlich, aber blind für Reste-Ketten: am Montagabend weiß er nicht,
    dass ein 3er-Gericht den Dienstagmittag deckt.
    """
    rng = random.Random(seed)

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
        chosen = _pick(options, rng, snap.weights.randomness)
        plan = plan.with_(slot.key, chosen.assignment)
        _book(chosen.assignment, slot, snap, ledger)

    # 4. Lokale Suche.
    plan = _improve(plan, snap, fixed=set(fixed))
    return rescore(plan, snap)


def _pick(options: list[Candidate], rng: random.Random, spread: float) -> Candidate:
    """Wählt aus den nach Score sortierten Kandidaten.

    Der Zufall entscheidet nur *zwischen frischen Gerichten*: jedes bekommt 0..`spread`
    Punkte dazu, das höchste gewinnt. Ob stattdessen Reste drankommen, entscheidet der
    echte Score wie ohne Zufall - sonst würde der Zufall mal Reste verschwenden und mal
    ein besseres frisches Essen verdrängen.
    """
    fresh = [c for c in options if c.assignment.kind is AssignmentKind.DISH]
    leftover = next((c for c in options if c.assignment.kind is not AssignmentKind.DISH), None)
    if not fresh:
        return options[0]
    if leftover is not None and leftover.total >= fresh[0].total:
        return leftover
    return max(fresh, key=lambda c: c.total + rng.uniform(0, spread))


def reroll_options(snap: PlanningSnapshot, plan: Plan, key: SlotKey) -> list[Candidate]:
    """Woraus "neu würfeln" zieht: die besten *verschiedenen* Gerichte.

    Jedes Gericht nur einmal, in seiner bestpassenden Größe - sonst belegen "Lachs" und
    "Lachs (doppelt)" zwei der Plätze. Und nie das aktuelle Gericht, auch nicht in
    anderer Größe oder als Reste: wer würfelt, will etwas anderes essen.
    """
    current = plan.get(key).dish_id
    seen: set[tuple] = set()
    out: list[Candidate] = []
    for candidate in candidates(snap.slot(key), plan.without(key), snap):
        assignment = candidate.assignment
        if current is not None and assignment.dish_id == current:
            continue
        identity = (assignment.kind, assignment.dish_id, assignment.leftover_source)
        if identity in seen:
            continue
        seen.add(identity)
        out.append(candidate)
        if len(out) == REROLL_POOL:
            break
    return out


def reroll(snap: PlanningSnapshot, plan: Plan, key: SlotKey, *, seed: int) -> Plan:
    """"Neu würfeln" für einen Slot: zieht aus den Top-Kandidaten, nie das Gleiche.

    Zog eine spätere Mahlzeit Reste aus diesem Slot, verliert sie mit dem alten Gericht
    ihre Quelle (`Plan.without`). Statt sie leer stehen zu lassen, wird sie gleich neu
    gefüllt - gern mit Resten des neuen Gerichts.
    """
    rng = random.Random(seed)
    options = reroll_options(snap, plan, key)
    if not options:
        return plan
    chosen = rng.choice(options)
    out = plan.without(key).with_(key, chosen.assignment)

    orphaned = sorted(
        (k for k, a in plan.items() if k != key and a.leftover_source == key),
        key=lambda k: k.index,
    )
    for orphan in orphaned:
        slot = snap.slot(orphan)
        refill = candidates(slot, out, snap)
        if slot.special is SlotSpecial.FROM_PANTRY:
            refill = [c for c in refill if c.assignment.kind is AssignmentKind.LEFTOVER]
        if refill:
            out = out.with_(orphan, _pick(refill, rng, snap.weights.randomness).assignment)
    return rescore(out, snap)


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
    if not eligible(snap.dish(b.dish_id), left_slot, stripped, factor=b.factor).ok:
        return None
    if not eligible(snap.dish(a.dish_id), right_slot, stripped, factor=a.factor).ok:
        return None

    candidate = stripped.with_(
        left, Assignment.dish(b.dish_id, factor=b.factor)
    ).with_(right, Assignment.dish(a.dish_id, factor=a.factor))
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
                factor=assignment.factor,
                ledger=ledger,
                final=True,
            )
            out = out.with_(key, Assignment(**{**_as_dict(assignment), "score": breakdown}))
        elif assignment.kind is AssignmentKind.LEFTOVER and assignment.leftover_source:
            pools = [
                p
                for p in PortionLedger.of(plan.without(key), snap).available_at(key)
                if p.source == assignment.leftover_source
            ]
            if pools:
                repeat = _earlier_leftover_meal(plan, assignment.leftover_source, key)
                breakdown = score_leftover(pools[0], slot, snap, repeat=repeat)
                out = out.with_(key, Assignment(**{**_as_dict(assignment), "score": breakdown}))
    return out


def _as_dict(assignment: Assignment) -> dict:
    return {
        "kind": assignment.kind,
        "dish_id": assignment.dish_id,
        "factor": assignment.factor,
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
            slot.key, dish.id, dish.portions_for(assignment.factor), slot.demand
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
