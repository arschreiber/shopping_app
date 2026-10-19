"""Einstellungen aus der Tabelle `setting` (ARCHITECTURE.md §4 Nr. 2).

Die Planer-Gewichte kommen aus der DB, nicht aus dem Code - Spike 4 kalibriert ohne
Deploy. Defaults gelten, solange nichts gespeichert ist.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..domain.weights import DEFAULT_WEIGHTS, PlannerWeights

KEY_WEIGHTS = "planner_weights"
KEY_HOUSEHOLD = "household"
KEY_SHOPPING = "shopping"
KEY_STANDARD_WEEK = "standard_week"  # Raster, mit dem neue Wochen anfangen (weeks.py)

DEFAULT_HOUSEHOLD: dict[str, Any] = {"members": ["Person A", "Person B"]}
DEFAULT_SHOPPING: dict[str, Any] = {
    "split_threshold_eur": 5.0,
    "leftover_shelf_life_days": 2,
    "shopping_weekday": 0,  # Montag (general_plan.md §2)
}


def get(session: Session, key: str, default: Any = None) -> Any:
    row = session.get(m.Setting, key)
    return row.value if row is not None else default


def put(session: Session, key: str, value: Any) -> None:
    row = session.get(m.Setting, key)
    if row is None:
        session.add(m.Setting(key=key, value=value))
    else:
        row.value = value


def all_settings(session: Session) -> dict[str, Any]:
    rows = session.scalars(select(m.Setting)).all()
    stored = {row.key: row.value for row in rows}
    return {
        KEY_WEIGHTS: {**DEFAULT_WEIGHTS.to_mapping(), **stored.get(KEY_WEIGHTS, {})},
        KEY_HOUSEHOLD: {**DEFAULT_HOUSEHOLD, **stored.get(KEY_HOUSEHOLD, {})},
        KEY_SHOPPING: {**DEFAULT_SHOPPING, **stored.get(KEY_SHOPPING, {})},
    }


def weights(session: Session) -> PlannerWeights:
    return PlannerWeights.from_mapping(get(session, KEY_WEIGHTS, {}))


def shopping_settings(session: Session) -> dict[str, Any]:
    return {**DEFAULT_SHOPPING, **(get(session, KEY_SHOPPING, {}) or {})}


def leftover_shelf_life(session: Session) -> int:
    return int(shopping_settings(session)["leftover_shelf_life_days"])
