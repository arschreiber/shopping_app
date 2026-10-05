"""Wochen-Use-Cases: Raster anlegen, kopieren, optimistisches Locking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.mappers import week_start
from ..domain.enums import AssignmentKind, Meal, SlotSpecial, TimeBudget
from .articles import ValidationError


class ConflictError(RuntimeError):
    """Optimistischer Lock-Konflikt -> HTTP 409 (ARCHITECTURE.md §6)."""

    def __init__(self, current_version: int) -> None:
        super().__init__(
            f"Die Woche wurde inzwischen geaendert (Version {current_version}). "
            "Bitte neu laden."
        )
        self.current_version = current_version


@dataclass(frozen=True, slots=True)
class SlotInput:
    day: int
    meal: Meal
    eaters_home: int
    packed_portions: int
    time_budget: TimeBudget
    special: SlotSpecial = SlotSpecial.NONE
    pinned: bool = False
    packed_fresh: bool = False


def parse_iso(iso: str) -> tuple[int, int]:
    """`2026-W37` -> (2026, 37)."""
    try:
        year_part, week_part = iso.upper().split("-W")
        year, week = int(year_part), int(week_part)
        date.fromisocalendar(year, week, 1)  # validiert die Kombination
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"'{iso}' ist keine ISO-Woche (erwartet z. B. 2026-W37)") from exc
    return year, week


def format_iso(iso_year: int, iso_week: int) -> str:
    return f"{iso_year}-W{iso_week:02d}"


def get_week(session: Session, iso: str) -> m.Week | None:
    year, week = parse_iso(iso)
    return session.scalar(
        select(m.Week).where(m.Week.iso_year == year, m.Week.iso_week == week)
    )


def get_or_create_week(session: Session, iso: str) -> m.Week:
    """Eine Woche existiert erst, wenn sie geöffnet wird - dann mit Standardraster.

    Öffnen Laptop und Handy dieselbe neue Woche im selben Moment, finden beide sie noch
    nicht und legen beide an. `ON CONFLICT DO NOTHING` lässt den zweiten dann leer
    ausgehen statt an UNIQUE(iso_year, iso_week) zu scheitern; er liest die Woche des
    ersten. Dessen Slots stehen dann schon: SQLite lässt den zweiten Schreiber warten,
    bis der erste committet hat, und der legt Woche und Slots in einem Zug an.
    """
    existing = get_week(session, iso)
    if existing is not None:
        return existing
    year, week_no = parse_iso(iso)
    created = session.execute(
        sqlite_insert(m.Week)
        .values(iso_year=year, iso_week=week_no, planner_seed=year * 100 + week_no)
        .on_conflict_do_nothing(index_elements=["iso_year", "iso_week"])
    ).rowcount
    week = get_week(session, iso)
    assert week is not None  # gerade angelegt oder vom Gleichzeitigen übernommen
    if created:
        for day in range(7):
            for meal in (Meal.LUNCH, Meal.DINNER):
                session.add(m.Slot(week_id=week.id, day=day, meal=meal.value))
        session.flush()
        session.refresh(week)
    return week


def update_grid(
    session: Session, iso: str, *, slots: list[SlotInput], version: int | None = None
) -> m.Week:
    """Wochenraster speichern. `version` prueft den optimistischen Lock."""
    week = get_or_create_week(session, iso)
    if version is not None and version != week.version:
        raise ConflictError(week.version)

    by_key = {(slot.day, slot.meal): slot for slot in week.slots}
    cleared: set[int] = set()
    for row in slots:
        slot = by_key.get((row.day, row.meal.value))
        if slot is None:
            raise ValidationError(f"Slot {row.day}/{row.meal.value} gehört nicht zur Woche")
        if not 0 <= row.eaters_home <= 2:
            raise ValidationError("Esser zu Hause muss zwischen 0 und 2 liegen")
        if not 0 <= row.packed_portions <= 2:
            raise ValidationError("Mitnehm-Portionen müssen zwischen 0 und 2 liegen")
        special, eaters, packed = row.special, row.eaters_home, row.packed_portions
        if special is SlotSpecial.EATING_OUT:
            # "auswärts" ist dasselbe wie "niemand da" - ein Zustand, nicht zwei, die
            # sich nur in der Darstellung unterscheiden.
            special, eaters, packed = SlotSpecial.NONE, 0, 0
        slot.eaters_home = eaters
        slot.packed_portions = packed
        # Ohne Mitnehm-Portion gibt es nichts frisch mitzunehmen - kein verstecktes "frisch".
        slot.packed_fresh = row.packed_fresh and packed > 0
        slot.time_budget = row.time_budget.value
        slot.special = special.value
        slot.pinned = row.pinned
        # Isst hier niemand, fällt das Gericht weg - sonst stünde es unsichtbar hinter der
        # "niemand da"-Karte und seine Zutaten weiter auf der Einkaufsliste.
        if eaters + packed == 0 and slot.assignment is not None:
            slot.assignment = None
            cleared.add(slot.id)
    # Reste-Karten, deren Quelle gerade weggefallen ist, gleich mit.
    for slot in week.slots:
        if slot.assignment is not None and slot.assignment.leftover_source_slot_id in cleared:
            slot.assignment = None
    week.version += 1
    session.flush()
    return week


def set_stores(
    session: Session, iso: str, *, primary_id: int | None, secondary_id: int | None
) -> m.Week:
    week = get_or_create_week(session, iso)
    week.primary_store_id = primary_id
    week.secondary_store_id = secondary_id
    week.version += 1
    return week


def copy_from(
    session: Session, *, target_iso: str, source_iso: str, grid_only: bool = True
) -> m.Week:
    """"wie letzte Woche" (general_plan.md §5 Phase 1).

    Standard ist `grid_only`: das Raster (Bürotage, Zeitbudget) wiederholt sich, der
    Plan selbst nicht - sonst kocht man jede Woche dasselbe.
    """
    source = get_week(session, source_iso)
    if source is None:
        raise ValidationError(f"Woche {source_iso} gibt es nicht")
    target = get_or_create_week(session, target_iso)

    source_slots = {(s.day, s.meal): s for s in source.slots}
    target_ids = {(s.day, s.meal): s for s in target.slots}
    for key, origin in source_slots.items():
        slot = target_ids[key]
        slot.eaters_home = origin.eaters_home
        slot.packed_portions = origin.packed_portions
        slot.packed_fresh = origin.packed_fresh
        slot.time_budget = origin.time_budget
        slot.special = origin.special
        slot.pinned = False
        if not grid_only and origin.assignment is not None:
            _copy_assignment(session, origin, slot, target_ids)

    target.primary_store_id = source.primary_store_id
    target.secondary_store_id = source.secondary_store_id
    target.version += 1
    session.flush()
    session.refresh(target)
    return target


def _copy_assignment(
    session: Session, origin: m.Slot, target: m.Slot, target_ids: dict
) -> None:
    assignment = origin.assignment
    assert assignment is not None
    source_slot_id = None
    if assignment.leftover_source_slot_id is not None:
        origin_week_slots = {s.id: (s.day, s.meal) for s in origin.week.slots}
        key = origin_week_slots.get(assignment.leftover_source_slot_id)
        if key is not None:
            source_slot_id = target_ids[key].id
    target.assignment = m.SlotAssignment(
        slot_id=target.id,
        kind=assignment.kind,
        dish_id=assignment.dish_id,
        factor=assignment.factor,
        leftover_source_slot_id=source_slot_id,
        portions_used=assignment.portions_used,
        score_snapshot=None,  # Begründung gilt nur für die Woche, in der sie entstand
    )


def previous_iso(iso: str) -> str:
    year, week = parse_iso(iso)
    start = week_start(year, week)
    previous = start.fromordinal(start.toordinal() - 7)
    iso_cal = previous.isocalendar()
    return format_iso(iso_cal.year, iso_cal.week)


def clear_assignments(session: Session, week: m.Week, *, keep_pinned: bool = True) -> None:
    for slot in week.slots:
        if keep_pinned and slot.pinned:
            continue
        slot.assignment = None
    week.version += 1


def week_summary(week: m.Week) -> dict:
    planned = sum(
        1
        for slot in week.slots
        if slot.assignment is not None
        and slot.assignment.kind in {AssignmentKind.DISH.value, AssignmentKind.LEFTOVER.value}
    )
    needed = sum(
        1
        for slot in week.slots
        if slot.eaters_home + slot.packed_portions > 0
        and slot.special != SlotSpecial.EATING_OUT.value
    )
    return {"planned": planned, "needed": needed}
