"""Die ganze Woche auf einmal planen (general_plan.md §4: "Ein Constraint-Solver
(OR-Tools) ... kann später nachgerüstet werden").

Der Greedy-Planer füllte Mahlzeit für Mahlzeit und sah nicht, dass ein 3er-Gericht am
Vorabend den Mittag dessen deckt, der allein isst. Hier ist jede Belegung eine
Entscheidung - frisch gekocht in jeder erlaubten Größe oder Reste aus einem früheren
Topf -, und CP-SAT sucht die Kombination mit der besten Gesamtpunktzahl.

Eine Wahrheit: Das Modell rechnet mit denselben Regeln und Gewichten wie `scoring.py`
und `eligibility.py`; der fertige Plan wird mit `rescore` bewertet, und Tests prüfen,
dass beide Zahlen übereinstimmen. Exakt muss das Ergebnis nicht sein: nach einer festen
Rechenmenge gilt der beste bis dahin gefundene Plan. Die Rechenmenge ist
deterministisch, nicht die Uhrzeit - derselbe Seed ergibt denselben Plan.

Regeln, die nur der automatische Vorschlag kennt (von Hand geht beides):
  * keine Reste am selben Tag, Mittag -> Abend - außer abends ist "keine Zeit",
  * wo "keine Zeit" ist, wird nicht gekocht; dort kommen Reste hin, wenn es irgend geht.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ortools.sat.python import cp_model

from .eligibility import eligible
from .enums import AssignmentKind, SlotSpecial, TimeBudget
from .model import Assignment, DishSpec, Plan, PlanningSnapshot, SlotKey, SlotSpec
from .scoring import VARIETY_AXES, _offers, _rating, _rotation, variety_weight

SCALE = 100  # CP-SAT rechnet ganzzahlig: Punkte x 100, also auf den Cent genau
FILL = 100_000  # eine Mahlzeit leer zu lassen, die sich füllen lässt, ist nie besser
# Rechenmenge statt Zeitlimit - auf jedem Rechner dieselbe Suche, also derselbe Plan.
# Erst kurz mit einer Strategie: kleine Wochen sind damit bewiesen optimal, oft in
# Zehntelsekunden. Sonst 16 Strategien im Wechsel (deterministisch verzahnt), ab dem
# bis dahin besten Plan - auf dem Server ~2 Sekunden.
QUICK_TIME = 0.5
WORKERS = 16
DETERMINISTIC_TIME = 5.0
SAFETY_SECONDS = 15.0  # nur gegen Hänger; im Normalfall greift die Rechenmenge


@dataclass(frozen=True, slots=True)
class _Cook:
    key: SlotKey
    dish: DishSpec
    factor: int

    @property
    def produced(self) -> int:
        return self.dish.portions_for(self.factor)


def optimize(
    snap: PlanningSnapshot,
    fixed: dict[SlotKey, Assignment],
    *,
    seed: int,
    hint: Plan | None = None,
) -> Plan | None:
    """Bester gefundener Plan, ohne Score-Begründungen (die rechnet `rescore`).

    `None`, wenn das Modell keine Lösung hat - etwa weil feste Mahlzeiten sich
    widersprechen. Dann bleibt der Greedy-Plan.
    """
    model = _Model(snap, fixed, seed)
    if hint is not None:
        model.add_hint(hint)
    return model.solve(seed)


class _Model:
    def __init__(self, snap: PlanningSnapshot, fixed: dict[SlotKey, Assignment], seed: int):
        self.snap = snap
        self.fixed = fixed
        self.w = snap.weights
        self.m = cp_model.CpModel()
        self.objective: list = []
        rng = random.Random(seed)

        # Mahlzeiten im Modell: alles, wo gegessen wird - außer fest leeren/"Vorhandenem".
        self.slots: list[SlotSpec] = [
            slot
            for slot in snap.slots
            if slot.needs_cooking
            and not (slot.key in fixed and fixed[slot.key].kind in _UNMODELLED)
        ]
        self.cook: dict[tuple[SlotKey, int, int], cp_model.IntVar] = {}
        self.eat: dict[tuple[SlotKey, SlotKey, int], cp_model.IntVar] = {}
        self._decisions(rng)
        self._rules()
        self._variety()

    # ------------------------------------------------------------------ Entscheidungen

    def _decisions(self, rng: random.Random) -> None:
        fixed_cooked = {
            a.dish_id for a in self.fixed.values() if a.kind is AssignmentKind.DISH
        }
        for slot in self.slots:
            pinned = self.fixed.get(slot.key)
            if pinned is not None and pinned.kind is AssignmentKind.DISH:
                var = self._cook_var(slot.key, pinned.dish_id, pinned.factor)
                self.m.Add(var == 1)
                continue
            if pinned is not None or not self._may_cook(slot):
                continue
            for dish in self.snap.dishes:
                if dish.id in fixed_cooked:
                    continue
                # Zufall pro Mahlzeit und Gericht, um null herum: er mischt ähnlich gute
                # frische Gerichte, verschiebt aber nicht im Schnitt Reste gegen Kochen.
                noise = rng.uniform(-0.5, 0.5) * self.w.randomness
                for factor in dish.factors:
                    if eligible(dish, slot, Plan(), factor=factor).ok:
                        var = self._cook_var(slot.key, dish.id, factor)
                        self._add_objective(self._cook_points(slot, dish, factor) + noise, var)

        # Wo wird was gekocht? Einmal nachschlagbar statt bei jeder Reste-Frage alle
        # Entscheidungen durchzugehen.
        self.pots: dict[tuple[SlotKey, int], list] = {}
        for (k, d, _), v in self.cook.items():
            self.pots.setdefault((k, d), []).append(v)

        for target in self.slots:
            pinned = self.fixed.get(target.key)
            if pinned is not None and pinned.kind is AssignmentKind.LEFTOVER:
                if pinned.leftover_source is None or pinned.dish_id is None:
                    continue
                var = self._eat_var(pinned.leftover_source, target.key, pinned.dish_id)
                self.m.Add(var == 1)
                continue
            if pinned is not None or target.fresh_only:
                continue
            for source in self.slots:
                if not self._leftovers_reach(source, target):
                    continue
                for dish in self.snap.dishes:
                    if target.packed_portions > 0 and not dish.packable:
                        continue
                    if (source.key, dish.id) in self.pots:
                        self._eat_var(source.key, target.key, dish.id)

        for (source, target, dish_id), var in self.eat.items():
            self._add_objective(self._eat_points(source, target, dish_id), var)

    def _may_cook(self, slot: SlotSpec) -> bool:
        return (
            slot.special is not SlotSpecial.FROM_PANTRY
            and slot.time_budget is not TimeBudget.NONE
        )

    def _leftovers_reach(self, source: SlotSpec, target: SlotSpec) -> bool:
        if not source.key.index < target.key.index:
            return False
        if target.key.day > source.key.day + self.snap.leftover_shelf_life_days:
            return False
        # Mittags kochen, abends dasselbe essen: nur, wenn abends keine Zeit ist.
        return source.key.day != target.key.day or target.time_budget is TimeBudget.NONE

    def _cook_var(self, key: SlotKey, dish_id: int, factor: int) -> cp_model.IntVar:
        var = self.m.NewBoolVar(f"cook_{key.index}_{dish_id}_{factor}")
        self.cook[key, dish_id, factor] = var
        return var

    def _eat_var(self, source: SlotKey, target: SlotKey, dish_id: int) -> cp_model.IntVar:
        var = self.m.NewBoolVar(f"eat_{source.index}_{target.index}_{dish_id}")
        self.eat[source, target, dish_id] = var
        return var

    # ------------------------------------------------------------------- Punkte

    def _cook_points(self, slot: SlotSpec, dish: DishSpec, factor: int) -> float:
        """Was `scoring.score` gäbe, wenn niemand die Reste isst (Abwechslung extra)."""
        w = self.w
        points = sum(c.delta for c in (*_rotation(dish, w), *_rating(dish, w), *_offers(dish, w)))
        produced = dish.portions_for(factor)
        if produced == slot.demand:
            points += w.exact_portions
        elif produced > slot.demand:
            points += w.waste_per_portion * (produced - slot.demand)
        if factor > 1 and dish.portions > 1:
            points += w.doubling
        return points

    def _eat_points(self, source: SlotKey, target: SlotKey, dish_id: int) -> float:
        """Reste-Mahlzeit (`score_leftover`) plus: an der Quelle wird aus "übrig" "verwertet"."""
        w = self.w
        slot = self.snap.slot(target)
        points = w.leftover_assignment + w.leftover_covers_demand
        points += sum(c.delta for c in _rating(self.snap.dish(dish_id), w))
        if slot.demand == 1:
            points += w.leftover_alone
        if slot.time_budget is TimeBudget.LITTLE:
            points += w.leftover_little_time
        points += (w.surplus_usable_per_portion - w.waste_per_portion) * slot.demand
        return points

    def _add_objective(self, points: float, var) -> None:
        self.objective.append(round(points * SCALE) * var)

    # ------------------------------------------------------------------- Regeln

    def _rules(self) -> None:
        m = self.m
        for slot in self.slots:
            chosen = [v for (k, _, _), v in self.cook.items() if k == slot.key] + [
                v for (_, t, _), v in self.eat.items() if t == slot.key
            ]
            if chosen:
                m.Add(sum(chosen) <= 1)
                self.objective.append(FILL * sum(chosen))

        # Ein Gericht pro Woche nur einmal kochen - Wiederholung läuft über Reste.
        for dish in self.snap.dishes:
            cooked = [v for (_, d, _), v in self.cook.items() if d == dish.id]
            if len(cooked) > 1:
                m.Add(sum(cooked) <= 1)

        for source in self.slots:
            eaten_from = [(t, d, v) for (s, t, d), v in self.eat.items() if s == source.key]
            if not eaten_from:
                continue
            # Reste nur vom Gericht, das dort gekocht wird ...
            for _target, dish_id, var in eaten_from:
                m.Add(var <= sum(self.pots.get((source.key, dish_id), [])))
            # ... jede Reste-Mahlzeit ganz gedeckt, und nicht mehr, als übrig ist.
            surplus = sum(
                (self.snap.dish(d).portions_for(f) - source.demand) * v
                for (k, d, f), v in self.cook.items()
                if k == source.key
            )
            m.Add(sum(self.snap.slot(t).demand * v for t, _, v in eaten_from) <= surplus)
            # Zwei Reste-Mahlzeiten aus einem Topf dürfen sein, aber kosten etwas.
            if len(eaten_from) > 1:
                extra = m.NewIntVar(0, len(eaten_from), f"extra_{source.key.index}")
                m.Add(extra >= sum(v for _, _, v in eaten_from) - 1)
                self._add_objective(self.w.leftover_second_meal, extra)

    def _variety(self) -> None:
        """Gleiche Beilage/Protein/Küche wie eine andere Mahlzeit: `scoring._variety`.

        Über Kategorien statt über Gericht-Paare - das hält das Modell klein. Pro Achse
        zählt ein Paar Mahlzeiten einmal, auch wenn sie mehrere Kategorien teilen.
        """
        dishes = self.snap.dishes
        keys = [slot.key for slot in self.slots]
        fresh: dict[tuple[SlotKey, int], list] = {}
        eaten: dict[tuple[SlotKey, int], list] = {}
        for (k, d, _), v in self.cook.items():
            fresh.setdefault((k, d), []).append(v)
        for (_, t, d), v in self.eat.items():
            eaten.setdefault((t, d), []).append(v)

        for axis in VARIETY_AXES:
            categories = sorted({c for d in dishes for c in d.category(axis)})
            if not categories:
                continue
            has_fresh, has_any = {}, {}
            for k in keys:
                for c in categories:
                    ids = [d.id for d in dishes if c in d.category(axis)]
                    has_fresh[k, c] = [v for d in ids for v in fresh.get((k, d), [])]
                    leftovers = [v for d in ids for v in eaten.get((k, d), [])]
                    has_any[k, c] = has_fresh[k, c] + leftovers
            for i in keys:
                for j in keys:
                    if i == j:
                        continue
                    pairs = [
                        (has_fresh[i, c], has_any[j, c])
                        for c in categories
                        if has_fresh[i, c] and has_any[j, c]
                    ]
                    if not pairs:
                        continue
                    weight = variety_weight(axis, abs(i.index - j.index), self.w)
                    if weight == 0:
                        continue
                    conflict = self.m.NewBoolVar(f"same_{axis.value}_{i.index}_{j.index}")
                    for fresh_i, any_j in pairs:
                        self.m.Add(conflict >= sum(fresh_i) + sum(any_j) - 1)
                    self._add_objective(weight, conflict)
                    # Reste des eigenen Gerichts sind keine Wiederholung (`other.id == dish.id`).
                    for dish in dishes:
                        var = self.eat.get((i, j, dish.id))
                        if var is not None and dish.category(axis):
                            self._add_objective(-weight, var)

    # ------------------------------------------------------------------- Lösen

    def add_hint(self, plan: Plan) -> None:
        """Startlösung (der Greedy-Plan): der Optimierer beginnt nie schlechter."""
        chosen: set = set()
        for key, assignment in plan.items():
            if assignment.kind is AssignmentKind.DISH:
                chosen.add(("cook", key, assignment.dish_id, assignment.factor))
            elif assignment.kind is AssignmentKind.LEFTOVER:
                chosen.add(("eat", assignment.leftover_source, key, assignment.dish_id))
        for (k, d, f), v in self.cook.items():
            self.m.AddHint(v, ("cook", k, d, f) in chosen)
        for (s, t, d), v in self.eat.items():
            self.m.AddHint(v, ("eat", s, t, d) in chosen)

    def solve(self, seed: int) -> Plan | None:
        self.m.Maximize(sum(self.objective))
        # Ohne Zufall soll jeder Seed dieselbe Woche ergeben.
        solver_seed = seed % 2**31 if self.w.randomness > 0 else 0
        solver, status = self._run(1, QUICK_TIME, solver_seed)
        if status == cp_model.FEASIBLE:
            self._hint_from(solver)
        if status != cp_model.OPTIMAL:
            solver, status = self._run(WORKERS, DETERMINISTIC_TIME, solver_seed)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None

        plan = Plan()
        for slot in self.snap.slots:
            if slot.key in self.fixed:
                plan = plan.with_(slot.key, self.fixed[slot.key])
        for (k, d, f), v in self.cook.items():
            if k not in self.fixed and solver.Value(v):
                plan = plan.with_(k, Assignment.dish(d, factor=f))
        for (s, t, d), v in self.eat.items():
            if t not in self.fixed and solver.Value(v):
                plan = plan.with_(t, Assignment.leftover(s, d, self.snap.slot(t).demand))
        for slot in self.slots:
            if slot.key not in plan.assignments:
                plan = plan.with_(slot.key, Assignment.empty())
        return plan

    def _run(self, workers: int, budget: float, seed: int) -> tuple[cp_model.CpSolver, int]:
        solver = cp_model.CpSolver()
        params = solver.parameters
        params.num_workers = workers
        params.interleave_search = workers > 1
        params.max_deterministic_time = budget
        params.max_time_in_seconds = SAFETY_SECONDS
        params.random_seed = seed
        return solver, solver.Solve(self.m)

    def _hint_from(self, solver: cp_model.CpSolver) -> None:
        """Weiter ab dem besten Plan des kurzen Laufs."""
        self.m.ClearHints()
        for var in (*self.cook.values(), *self.eat.values()):
            self.m.AddHint(var, solver.Value(var))


# Fest vorgegeben und ohne Gericht: zählt weder als Topf noch als Reste-Esser.
_UNMODELLED = frozenset({AssignmentKind.EMPTY, AssignmentKind.PANTRY})
