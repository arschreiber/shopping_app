"""Score-Gewichte (ARCHITECTURE.md §4 Nr. 2).

Die Defaults entsprechen general_plan.md §4. Sie sind *Startwerte* für Spike 4: zur
Laufzeit kommen die Gewichte aus der Tabelle `setting`, nicht aus dem Code. `from_mapping`
ist die eine Stelle, an der Settings-JSON zu Gewichten wird.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class PlannerWeights:
    # --- Abwechslung: gleiche Beilage / gleiches Protein wie am Vortag, gestaffelt
    same_side_adjacent: float = -12.0
    same_side_same_week: float = -3.0
    same_protein_adjacent: float = -14.0
    same_protein_same_week: float = -4.0
    same_cuisine_adjacent: float = -5.0
    same_cuisine_same_week: float = -1.5
    variety_span_slots: int = 3  # bis zu welchem Abstand "adjacent" gilt

    # --- Rotation: lange nicht gekocht -> Bonus, kuerzlich gekocht -> Abzug
    rotation_per_week: float = 1.5
    rotation_cap: float = 12.0
    never_cooked_bonus: float = 12.0  # maximal überfällig, wie `rotation_cap`
    cooked_within_two_weeks: float = -18.0

    # --- Bewertung (1..5, neutral bei 3)
    rating_per_star: float = 3.0

    # --- Angebote (Phase 2; ohne Angebotsdaten schlicht 0)
    offer_per_euro: float = 3.0
    offer_cap: float = 15.0

    # --- Portionen und Reste
    exact_portions: float = 5.0  # nichts bleibt übrig
    waste_per_portion: float = -4.0  # Reste, die kein Slot mehr braucht
    surplus_usable_per_portion: float = 1.5  # Überschuss, den ein spaeterer Slot brauchen kann
    leftover_covers_demand: float = 10.0  # eine Reste-*Zuweisung* deckt diesen Slot
    leftover_assignment: float = 7.0  # Reste-Karte statt neu kochen (kein Einkauf)
    doubling: float = -2.0  # verdoppeln ist Mehraufwand

    # --- Aufwand vs. Zeitbudget
    effort_slack: float = 2.0  # aufwendiges Gericht an einem Tag mit viel Zeit
    quick_when_little_time: float = 3.0

    def to_mapping(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, data: Any) -> Self:
        """Tolerant: unbekannte Keys werden ignoriert, fehlende bleiben Default."""
        if not isinstance(data, dict):
            return cls()
        known = {f.name: f.type for f in fields(cls)}
        kwargs: dict[str, Any] = {}
        for key, value in data.items():
            if key not in known:
                continue
            try:
                kwargs[key] = int(value) if known[key] == "int" else float(value)
            except (TypeError, ValueError):
                continue
        return cls(**kwargs)


DEFAULT_WEIGHTS = PlannerWeights()
