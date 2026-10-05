"""Planungs-Use-Cases: Kandidaten, Vorschlag, Zuweisung, Diagnostik.

Duenne Schicht: Snapshot bauen -> Domänenfunktion -> Ergebnis persistieren. Die Logik
selbst liegt in `domain/` und ist ohne DB testbar.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..db import mappers
from ..db import models as m
from ..domain.diagnostics import diagnose
from ..domain.enums import AssignmentKind, Meal, SlotSpecial
from ..domain.model import (
    Assignment,
    Candidate,
    Plan,
    PlanningSnapshot,
    PlanWarning,
    SlotKey,
)
from ..domain.planner import candidates as domain_candidates
from ..domain.planner import propose, reroll, reroll_options, rescore
from . import settings_store
from .articles import ValidationError
from .weeks import ConflictError, get_or_create_week


@dataclass(frozen=True, slots=True)
class PlanResult:
    week: m.Week
    plan: Plan
    snapshot: PlanningSnapshot
    warnings: list[PlanWarning]


def build_context(session: Session, week: m.Week) -> tuple[PlanningSnapshot, Plan]:
    snapshot = mappers.build_snapshot(
        session,
        week,
        weights=settings_store.weights(session),
        leftover_shelf_life_days=settings_store.leftover_shelf_life(session),
        offer_savings=_offer_savings(session, week),
    )
    return snapshot, mappers.plan_from_week(week)


def _offer_savings(session: Session, week: m.Week) -> dict[int, float]:
    """Phase 2: Angebots-Bonus pro Gericht. Ohne Angebotsdaten leer."""
    from .offers import savings_by_dish

    return savings_by_dish(session, week)


def slot_candidates(
    session: Session, iso: str, day: int, meal: Meal, *, include_ineligible: bool = False
) -> tuple[list[Candidate], PlanningSnapshot]:
    week = get_or_create_week(session, iso)
    snapshot, plan = build_context(session, week)
    key = SlotKey.of(day, meal)
    slot = snapshot.slot(key)
    options = domain_candidates(
        slot, plan.without(key), snapshot, include_ineligible=include_ineligible
    )
    return options, snapshot


def propose_week(
    session: Session,
    iso: str,
    *,
    keep_pins: bool = True,
    only_empty: bool = False,
    version: int | None = None,
) -> PlanResult:
    week = get_or_create_week(session, iso)
    if version is not None and version != week.version:
        raise ConflictError(week.version)

    snapshot, current = build_context(session, week)
    pinned = {
        slot_key: current.get(slot_key)
        for slot_key in current.assignments
        if keep_pins and snapshot.slot(slot_key).pinned
    }
    keep = {}
    if only_empty:
        keep = {
            key: assignment
            for key, assignment in current.assignments.items()
            if not assignment.is_empty and key not in pinned
        }

    # Neuer Seed pro Klick: sonst liefert dieselbe Woche immer denselben Plan. Er wird an
    # der Woche gespeichert - der gespeicherte Plan bleibt nachstellbar.
    week.planner_seed = random.Random(week.planner_seed).randrange(1, 2**31)
    plan = propose(snapshot, pinned, seed=week.planner_seed, keep=keep)
    _persist(session, week, plan, snapshot)
    return PlanResult(week, plan, snapshot, diagnose(plan, snapshot))


def reroll_slot(
    session: Session, iso: str, day: int, meal: Meal, *, version: int | None = None
) -> PlanResult:
    week = get_or_create_week(session, iso)
    if version is not None and version != week.version:
        raise ConflictError(week.version)
    snapshot, current = build_context(session, week)
    key = SlotKey.of(day, meal)
    if snapshot.slot(key).pinned:
        raise ValidationError(f"{key} ist gepinnt - erst lösen, dann würfeln")

    # Ein stilles "nichts passiert" wäre die schlechtere Antwort: bei einem kleinen
    # Gerichte-Pool ist jedes andere Gericht schon in der Woche verplant, und der
    # Nutzer soll das erfahren statt zweimal zu klicken.
    if not reroll_options(snapshot, current, key):
        raise ValidationError(
            f"Keine Alternative für {key} - alle passenden Gerichte sind diese Woche "
            "schon verplant. Mehr Gerichte erfassen oder einen anderen Slot ändern."
        )

    # Neuer Seed pro Würfeln, an der Woche persistiert: der Vorschlag bleibt
    # reproduzierbar (ARCHITECTURE.md §4 Nr. 3).
    week.planner_seed = random.Random(week.planner_seed + key.index).randrange(1, 2**31)
    plan = reroll(snapshot, current, key, seed=week.planner_seed)
    _persist(session, week, plan, snapshot)
    return PlanResult(week, plan, snapshot, diagnose(plan, snapshot))


def set_assignment(
    session: Session,
    iso: str,
    day: int,
    meal: Meal,
    *,
    assignment: Assignment,
    version: int | None = None,
) -> PlanResult:
    week = get_or_create_week(session, iso)
    if version is not None and version != week.version:
        raise ConflictError(week.version)
    snapshot, current = build_context(session, week)
    key = SlotKey.of(day, meal)
    slot_spec = snapshot.slot(key)

    # Hier isst niemand: ein Gericht stünde unsichtbar hinter der "niemand da"-Karte.
    feeds = assignment.cooks or assignment.kind is AssignmentKind.LEFTOVER
    if feeds and not slot_spec.needs_cooking:
        raise ValidationError(f"{key}: hier isst niemand - nichts zu planen")

    if assignment.kind is AssignmentKind.DISH:
        if assignment.dish_id is None:
            raise ValidationError("Gericht fehlt")
        _validate_dish_choice(snapshot, current, key, assignment)
    elif assignment.kind is AssignmentKind.LEFTOVER:
        _validate_leftover_choice(snapshot, current, key, assignment)
    elif assignment.kind is AssignmentKind.PANTRY and slot_spec.special is SlotSpecial.NONE:
        raise ValidationError(
            "'aus Vorhandenem' setzt einen entsprechend markierten Slot voraus"
        )

    plan = rescore(current.without(key).with_(key, assignment), snapshot)
    _persist(session, week, plan, snapshot)
    return PlanResult(week, plan, snapshot, diagnose(plan, snapshot))


def _validate_dish_choice(
    snapshot: PlanningSnapshot, plan: Plan, key: SlotKey, assignment: Assignment
) -> None:
    from ..domain.eligibility import eligible, factor_reason

    dish = snapshot.dish_or_none(assignment.dish_id)
    if dish is None:
        raise ValidationError(f"Gericht {assignment.dish_id} ist nicht planbar (archiviert?)")
    # Manuelle Wahl darf Warnungen erzeugen, aber keine unmögliche Woche: wie oft ein
    # Gericht auf einmal gekocht wird und das Portionsdefizit sind nicht verhandelbar.
    if assignment.factor not in dish.factors:
        raise ValidationError(factor_reason(dish, assignment.factor))
    verdict = eligible(dish, snapshot.slot(key), plan.without(key), factor=assignment.factor)
    if not verdict.ok:
        blocking = [reason for reason in verdict.reasons if "reichen nicht" in reason]
        if blocking:
            raise ValidationError("; ".join(blocking))


def _validate_leftover_choice(
    snapshot: PlanningSnapshot, plan: Plan, key: SlotKey, assignment: Assignment
) -> None:
    from ..domain.leftovers import PortionLedger

    if assignment.leftover_source is None:
        raise ValidationError("Quelle der Reste fehlt")
    if snapshot.slot(key).fresh_only:
        raise ValidationError(f"{key} wird frisch mitgenommen - dafür wird gekocht, keine Reste")
    ledger = PortionLedger.of(plan.without(key), snapshot)
    pools = [p for p in ledger.available_at(key) if p.source == assignment.leftover_source]
    if not pools:
        raise ValidationError(
            f"Von {assignment.leftover_source} sind keine Reste (mehr) verfügbar"
        )
    wanted = assignment.portions_used or 0
    if wanted > pools[0].portions:
        raise ValidationError(
            f"Nur {pools[0].portions} Portion(en) von {assignment.leftover_source} übrig"
        )
    demand = snapshot.slot(key).demand
    if pools[0].portions < demand:
        raise ValidationError(
            f"{pools[0].portions} Portion(en) von {assignment.leftover_source} decken "
            f"{key} nicht ({demand} gebraucht)"
        )


def clear_slot(
    session: Session, iso: str, day: int, meal: Meal, *, version: int | None = None
) -> PlanResult:
    return set_assignment(
        session, iso, day, meal, assignment=Assignment.empty(), version=version
    )


def toggle_pin(session: Session, iso: str, day: int, meal: Meal, *, pinned: bool) -> m.Week:
    week = get_or_create_week(session, iso)
    for slot in week.slots:
        if slot.day == day and slot.meal == meal.value:
            slot.pinned = pinned
            week.version += 1
            return week
    raise ValidationError(f"Slot {day}/{meal.value} gehört nicht zur Woche")


def set_cancelled(
    session: Session,
    iso: str,
    day: int,
    meal: Meal,
    *,
    cancelled: bool,
    today: date | None = None,
) -> m.Week:
    """Ein geplantes Gericht ist ausgefallen - oder doch gekocht worden.

    Ausgefallen zählt nicht als gekocht (`mappers.last_cooked`), sonst bekäme es
    wochenlang einen Abzug für ein Essen, das es nie gab. Am Plan selbst ändert sich
    nichts: der Tag ist vorbei, eingekauft ist auch.
    """
    week = get_or_create_week(session, iso)
    slot = next((s for s in week.slots if s.day == day and s.meal == meal.value), None)
    if slot is None:
        raise ValidationError(f"Slot {day}/{meal.value} gehört nicht zur Woche")
    key = SlotKey.of(day, meal)
    assignment = slot.assignment
    if assignment is None or assignment.kind != AssignmentKind.DISH.value:
        raise ValidationError(f"{key}: hier ist kein Gericht geplant, das ausfallen könnte")
    served = mappers.week_start(week.iso_year, week.iso_week) + timedelta(days=day)
    if served > (today or date.today()):
        raise ValidationError(f"{key} ist noch nicht dran - statt 'ausgefallen' einfach umplanen")

    entries = [entry for entry in slot.cook_entries if entry.dish_id == assignment.dish_id]
    if cancelled and not entries:
        slot.cook_entries.append(
            m.CookLog(dish_id=assignment.dish_id, cooked_at=served, confirmed=False)
        )
    for entry in entries:
        if cancelled:
            entry.confirmed = False
        elif not entry.confirmed and entry.rating is None and entry.note is None:
            # Zurück auf "zählt, weil geplant" - eine leere Zeile sagt nichts mehr.
            slot.cook_entries.remove(entry)
            session.delete(entry)
        else:
            entry.confirmed = True
    week.version += 1
    session.flush()
    return week


def diagnostics(session: Session, iso: str) -> tuple[list[PlanWarning], PlanningSnapshot]:
    week = get_or_create_week(session, iso)
    snapshot, plan = build_context(session, week)
    return diagnose(plan, snapshot), snapshot


# ----------------------------------------------------------------------- Persistierung


def _persist(session: Session, week: m.Week, plan: Plan, snapshot: PlanningSnapshot) -> None:
    """Schreibt den Plan zurück. Reste-Quellen werden auf DB-Slot-IDs übersetzt."""
    slot_ids = mappers.slot_ids_by_key(week)
    by_key = {SlotKey.of(slot.day, Meal(slot.meal)): slot for slot in week.slots}

    for key, slot in by_key.items():
        assignment = plan.get(key)
        if assignment.is_empty:
            slot.assignment = None
            continue
        source_id = (
            slot_ids.get(assignment.leftover_source) if assignment.leftover_source else None
        )
        payload = {
            "kind": assignment.kind.value,
            "dish_id": assignment.dish_id,
            "factor": assignment.factor,
            "leftover_source_slot_id": source_id,
            "portions_used": assignment.portions_used,
            "score_snapshot": mappers.breakdown_to_json(assignment.score),
        }
        if slot.assignment is None:
            slot.assignment = m.SlotAssignment(slot_id=slot.id, **payload)
        else:
            for field, value in payload.items():
                setattr(slot.assignment, field, value)

    week.version += 1
    session.flush()
