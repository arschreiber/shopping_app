"""Wochen-Router: Raster, Vorschlag, Kandidaten, Zuweisung, Diagnostik."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ...domain.enums import Meal
from ...domain.model import Assignment, SlotKey
from ...services import planning as service
from ...services import weeks as weeks_service
from ..deps import SessionDep
from ..mapping import candidate_out, warning_out, week_out
from ..schemas.common import (
    AssignmentIn,
    CancelIn,
    CandidateOut,
    GridIn,
    PinIn,
    ProposeIn,
    WarningOut,
    WeekOut,
)

router = APIRouter(prefix="/api/weeks", tags=["weeks"])


def _week_response(session, iso: str) -> WeekOut:
    week = weeks_service.get_or_create_week(session, iso)
    snapshot, plan = service.build_context(session, week)
    from ...domain.diagnostics import diagnose

    return week_out(week, plan, snapshot, diagnose(plan, snapshot))


@router.get("/{iso}", response_model=WeekOut)
def get_week(session: SessionDep, iso: str) -> WeekOut:
    return _week_response(session, iso)


@router.put("/{iso}/grid", response_model=WeekOut)
def put_grid(session: SessionDep, iso: str, payload: GridIn) -> WeekOut:
    weeks_service.update_grid(
        session,
        iso,
        slots=[
            weeks_service.SlotInput(
                day=row.day,
                meal=row.meal,
                eaters_home=row.eaters_home,
                packed_portions=row.packed_portions,
                packed_fresh=row.packed_fresh,
                time_budget=row.time_budget,
                special=row.special,
                pinned=row.pinned,
            )
            for row in payload.slots
        ],
        version=payload.version,
    )
    return _week_response(session, iso)


@router.post("/{iso}/copy-from/{source_iso}", response_model=WeekOut)
def copy_from(
    session: SessionDep, iso: str, source_iso: str, grid_only: bool = True
) -> WeekOut:
    """"wie letzte Woche" - standardmaessig nur das Raster, nicht der Plan."""
    weeks_service.copy_from(
        session, target_iso=iso, source_iso=source_iso, grid_only=grid_only
    )
    return _week_response(session, iso)


@router.get("/{iso}/slots/{day}/{meal}/candidates", response_model=list[CandidateOut])
def slot_candidates(
    session: SessionDep,
    iso: str,
    day: int,
    meal: Meal,
    include_ineligible: bool = Query(default=False),
) -> list[CandidateOut]:
    """Sortierte Kandidatenliste mit Score-Begründung und Warnungen."""
    options, snapshot = service.slot_candidates(
        session, iso, day, meal, include_ineligible=include_ineligible
    )
    return [candidate_out(candidate, snapshot) for candidate in options]


@router.post("/{iso}/propose", response_model=WeekOut)
def propose(session: SessionDep, iso: str, payload: ProposeIn) -> WeekOut:
    result = service.propose_week(
        session,
        iso,
        keep_pins=payload.keep_pins,
        only_empty=payload.only_empty,
        version=payload.version,
    )
    return week_out(result.week, result.plan, result.snapshot, result.warnings)


@router.post("/{iso}/slots/{day}/{meal}/reroll", response_model=WeekOut)
def reroll(session: SessionDep, iso: str, day: int, meal: Meal) -> WeekOut:
    result = service.reroll_slot(session, iso, day, meal)
    return week_out(result.week, result.plan, result.snapshot, result.warnings)


@router.put("/{iso}/slots/{day}/{meal}/assignment", response_model=WeekOut)
def put_assignment(
    session: SessionDep, iso: str, day: int, meal: Meal, payload: AssignmentIn
) -> WeekOut:
    source = None
    if payload.leftover_source_day is not None and payload.leftover_source_meal is not None:
        source = SlotKey.of(payload.leftover_source_day, payload.leftover_source_meal)
    assignment = Assignment(
        kind=payload.kind,
        dish_id=payload.dish_id,
        factor=payload.factor,
        leftover_source=source,
        portions_used=payload.portions_used,
    )
    result = service.set_assignment(
        session, iso, day, meal, assignment=assignment, version=payload.version
    )
    return week_out(result.week, result.plan, result.snapshot, result.warnings)


@router.delete("/{iso}/slots/{day}/{meal}/assignment", response_model=WeekOut)
def clear_assignment(session: SessionDep, iso: str, day: int, meal: Meal) -> WeekOut:
    result = service.clear_slot(session, iso, day, meal)
    return week_out(result.week, result.plan, result.snapshot, result.warnings)


@router.put("/{iso}/slots/{day}/{meal}/pin", response_model=WeekOut)
def set_pin(session: SessionDep, iso: str, day: int, meal: Meal, payload: PinIn) -> WeekOut:
    service.toggle_pin(session, iso, day, meal, pinned=payload.pinned)
    return _week_response(session, iso)


@router.put("/{iso}/slots/{day}/{meal}/cancelled", response_model=WeekOut)
def set_cancelled(
    session: SessionDep, iso: str, day: int, meal: Meal, payload: CancelIn
) -> WeekOut:
    """Gericht ausgefallen (oder doch gekocht) - zählt dann nicht für die Abwechslung."""
    service.set_cancelled(session, iso, day, meal, cancelled=payload.cancelled)
    return _week_response(session, iso)


@router.delete("/{iso}/assignments", response_model=WeekOut)
def clear_week(session: SessionDep, iso: str, keep_pinned: bool = True) -> WeekOut:
    week = weeks_service.get_or_create_week(session, iso)
    weeks_service.clear_assignments(session, week, keep_pinned=keep_pinned)
    return _week_response(session, iso)


@router.get("/{iso}/diagnostics", response_model=list[WarningOut])
def diagnostics(session: SessionDep, iso: str) -> list[WarningOut]:
    warnings, _snapshot = service.diagnostics(session, iso)
    return [warning_out(w) for w in warnings]
