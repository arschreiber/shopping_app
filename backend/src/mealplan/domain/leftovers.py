"""Portions-Buchhaltung (ARCHITECTURE.md §4, general_plan.md §4 "Reste-Logik").

Die Stelle, an der Tandoor/Mealie/Grocy scheitern - und damit die Stelle mit den meisten
Tests. Ein 3-Portionen-Gericht für zwei Esser erzeugt eine Reste-Portion mit Haltbarkeit
1-2 Tage; die deckt bevorzugt den Mitnehm-Bedarf des nächsten Tages oder einen
Home-Office-Mittagsslot.

Invarianten (als Property-Tests abgesichert):
  * nie mehr Portionen entnehmen als produziert wurden,
  * nie ueber die Haltbarkeit hinaus entnehmen,
  * eine Reste-Zuweisung zieht immer aus genau einer Quelle.
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import AssignmentKind
from .model import Plan, PlanningSnapshot, SlotKey


@dataclass(frozen=True, slots=True)
class LeftoverPool:
    """Was an einem Slot übrig ist: Quelle, Gericht, Portionen, letzter Nutztag."""

    source: SlotKey
    dish_id: int
    portions: int
    last_usable_day: int

    def usable_at(self, key: SlotKey) -> bool:
        """Reste sind ab dem *nächsten* Slot nutzbar, bis die Haltbarkeit endet."""
        return key.index > self.source.index and key.day <= self.last_usable_day


class PortionLedger:
    """Fuehrt Produktion und Verbrauch von Portionen ueber eine Woche mit.

    Bewusst mutable und bewusst nicht Teil von `Plan`: der Planer baut den Ledger beim
    Durchlaufen der Slots auf und fragt ihn nach verfuegbaren Resten. Für eine fertige
    Woche gibt es `PortionLedger.of(plan, snap)`.
    """

    def __init__(self, snap: PlanningSnapshot) -> None:
        self._snap = snap
        self._produced: dict[SlotKey, int] = {}
        self._dish_of: dict[SlotKey, int] = {}
        self._consumed: dict[SlotKey, int] = {}

    # ---------------------------------------------------------------- Buchungen

    def record_cook(self, key: SlotKey, dish_id: int, produced: int, needed: int) -> None:
        if produced < needed:
            raise ValueError(
                f"{key}: {produced} Portionen gekocht, aber {needed} gebraucht"
            )
        self._produced[key] = produced - needed
        self._dish_of[key] = dish_id
        self._consumed.setdefault(key, 0)

    def record_leftover_use(self, source: SlotKey, portions: int) -> None:
        available = self.remaining(source)
        if portions > available:
            raise ValueError(
                f"{source}: {portions} Reste-Portionen angefordert, nur {available} da"
            )
        self._consumed[source] = self._consumed.get(source, 0) + portions

    def forget(self, key: SlotKey) -> None:
        """Slot-Zuweisung zurücknehmen (Reroll, Tausch)."""
        self._produced.pop(key, None)
        self._dish_of.pop(key, None)
        self._consumed.pop(key, None)

    # ---------------------------------------------------------------- Abfragen

    def remaining(self, source: SlotKey) -> int:
        return self._produced.get(source, 0) - self._consumed.get(source, 0)

    def available_at(self, key: SlotKey) -> list[LeftoverPool]:
        """Nutzbare Reste für diesen Slot, frischeste Quelle zuerst."""
        pools = [
            pool
            for source in sorted(self._produced, key=lambda k: -k.index)
            if (pool := self._pool(source)) is not None and pool.usable_at(key)
        ]
        return pools

    def _pool(self, source: SlotKey) -> LeftoverPool | None:
        remaining = self.remaining(source)
        if remaining <= 0:
            return None
        return LeftoverPool(
            source=source,
            dish_id=self._dish_of[source],
            portions=remaining,
            last_usable_day=source.day + self._snap.leftover_shelf_life_days,
        )

    def wasted(self) -> list[LeftoverPool]:
        """Portionen, die am Wochenende übrig bleiben - der Verschwendungs-Abzug."""
        return [p for source in self._produced if (p := self._pool(source)) is not None]

    def would_waste(self, key: SlotKey, surplus: int) -> int:
        """Wie viele von `surplus` Portionen kann kein spaeterer Slot mehr brauchen?

        Rein prospektiv, weil das Scoring die Frage stellt, *bevor* die späteren Slots
        belegt sind. Entscheidend: eine Reste-Karte muss den Bedarf eines Slots *ganz*
        decken - eine Portion fuettert keine zwei Esser. Wer hier nur Portionen
        gegenrechnet, erklaert eine Rest-Portion als "verwertbar", die `diagnose()`
        hinterher als übrig meldet. Genau diese Widerspruechlichkeit laesst
        Auto-Vorschläge willkuerlich wirken (general_plan.md §8 Nr. 7).
        """
        if surplus <= 0:
            return 0
        last_day = key.day + self._snap.leftover_shelf_life_days
        left = surplus
        for slot in sorted(self._snap.slots, key=lambda s: s.key.index):
            if left <= 0:
                break
            if slot.key.index <= key.index or slot.key.day > last_day:
                continue
            if slot.key in self._produced or slot.key in self._consumed:
                continue
            if not slot.needs_cooking:
                continue
            if slot.demand <= left:
                left -= slot.demand
        return left

    # ------------------------------------------------------------- Rekonstruktion

    @classmethod
    def of(cls, plan: Plan, snap: PlanningSnapshot) -> PortionLedger:
        """Ledger für einen fertigen Plan - für Diagnostik und Einkaufsliste."""
        ledger = cls(snap)
        for key, assignment in plan.items():
            slot = snap.slot(key)
            if assignment.kind is AssignmentKind.DISH and assignment.dish_id is not None:
                dish = snap.dish(assignment.dish_id)
                ledger.record_cook(
                    key,
                    dish.id,
                    dish.portions_for(assignment.factor),
                    slot.demand,
                )
        for _key, assignment in plan.items():
            if assignment.kind is AssignmentKind.LEFTOVER and assignment.leftover_source:
                ledger.record_leftover_use(
                    assignment.leftover_source, assignment.portions_used or 0
                )
        return ledger
