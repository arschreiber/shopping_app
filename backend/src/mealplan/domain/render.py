"""Plan als Text (pure). Traegt den Golden-File-Test und die CLI.

Gehoert in die Domäne, weil die Darstellung nur aus Domänen-Objekten ableitet und der
Golden-File-Test aus ARCHITECTURE.md §9 damit einen lesbaren Diff erzeugt: eine
Gewichtungsaenderung zeigt sich als Zeilen-Diff, nicht als Zahlensprung.
"""

from __future__ import annotations

from .enums import AssignmentKind, SlotSpecial, TimeBudget
from .model import Plan, PlanningSnapshot, PlanWarning

_BUDGET = {TimeBudget.NORMAL: "normal", TimeBudget.LITTLE: "wenig", TimeBudget.NONE: "keine"}
_SPECIAL = {
    SlotSpecial.NONE: "",
    SlotSpecial.EATING_OUT: " [auswärts]",
    SlotSpecial.FROM_PANTRY: " [aus Vorhandenem]",
}


def render_plan(plan: Plan, snap: PlanningSnapshot, *, with_reasons: bool = True) -> str:
    lines: list[str] = []
    for slot in sorted(snap.slots, key=lambda s: s.key.index):
        assignment = plan.get(slot.key)
        head = (
            f"{slot.key!s:<10} {slot.eaters_home}+{slot.packed_portions} P, "
            f"{_BUDGET[slot.time_budget]:>6} Zeit{_SPECIAL[slot.special]}"
        )
        lines.append(f"{head}  ->  {_describe(assignment, snap)}")
        if with_reasons and assignment.score is not None:
            for reason in assignment.score.reasons():
                lines.append(f"{'':<12}    · {reason}")
    lines.append("")
    lines.append(f"Gesamtscore: {plan.total_score():.1f}")
    return "\n".join(lines)


def _describe(assignment, snap: PlanningSnapshot) -> str:
    match assignment.kind:
        case AssignmentKind.EMPTY:
            return "-"
        case AssignmentKind.PANTRY:
            return "aus Vorhandenem"
        case AssignmentKind.LEFTOVER:
            dish = snap.dish_or_none(assignment.dish_id)
            name = dish.name if dish else "?"
            score = f" [{assignment.score.total:+.1f}]" if assignment.score else ""
            return (
                f"Reste: {name} ({assignment.leftover_source}, "
                f"{assignment.portions_used} P){score}"
            )
        case AssignmentKind.DISH:
            dish = snap.dish_or_none(assignment.dish_id)
            if dish is None:
                return "?"
            portions = dish.portions_for(assignment.factor)
            suffix = f" ×{assignment.factor}" if assignment.factor > 1 else ""
            score = f" [{assignment.score.total:+.1f}]" if assignment.score else ""
            return f"{dish.name}{suffix} ({portions} P){score}"
    return "?"


def render_warnings(warnings: list[PlanWarning]) -> str:
    if not warnings:
        return "keine Warnungen"
    icon = {"INFO": "i", "WARN": "!", "ERROR": "x"}
    return "\n".join(f"[{icon[w.level.value]}] {w.text}" for w in warnings)
