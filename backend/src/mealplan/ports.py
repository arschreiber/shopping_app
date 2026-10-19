"""Ports (ARCHITECTURE.md §5) - die Versicherung gegen die 1-2 Brueche pro Jahr.

Jede fragile Integration liegt hinter einem `Protocol`. Bricht Bring! oder eine
Angebotsquelle, laehmt das ein Feature, nicht die App: `main.py` waehlt die
Implementierung, alles andere kennt nur diese Signaturen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

# ----------------------------------------------------------------------- Einkaufsliste


@dataclass(frozen=True, slots=True)
class SyncItem:
    """Ein Soll-Eintrag für die externe Liste."""

    article_id: int
    name: str  # Bring!-Katalogname, wenn vorhanden - sonst der kanonische Name
    spec: str  # "500 g" - Bring! hat kein strukturiertes Mengenfeld


@dataclass(frozen=True, slots=True)
class SyncStateItem:
    article_id: int
    item_uuid: str | None
    name: str
    spec: str | None


@dataclass(frozen=True, slots=True)
class SyncState:
    list_uuid: str | None
    items: tuple[SyncStateItem, ...] = ()


@dataclass(frozen=True, slots=True)
class SyncResult:
    ok: bool
    created: tuple[SyncItem, ...] = ()
    updated: tuple[SyncItem, ...] = ()
    removed: tuple[str, ...] = ()
    list_uuid: str | None = None
    item_uuids: dict[int, str] = field(default_factory=dict)
    text_fallback: str | None = None
    error: str | None = None

    @property
    def summary(self) -> dict:
        return {
            "created": [i.name for i in self.created],
            "updated": [i.name for i in self.updated],
            "removed": list(self.removed),
        }


@runtime_checkable
class ShoppingListSync(Protocol):
    name: str

    def push(self, desired: list[SyncItem], state: SyncState) -> SyncResult: ...


# ---------------------------------------------------------------------------- Angebote


@dataclass(frozen=True, slots=True)
class RawOffer:
    raw_name: str
    price: Decimal | None = None
    old_price: Decimal | None = None  # nur, wenn die Quelle einen höheren "statt"-Preis nennt
    brand: str | None = None
    base_price: str | None = None  # "5,08 €/kg"
    pack: str | None = None  # "250 g"
    category: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    image_url: str | None = None
    description: str | None = None  # Prospekttext: "versch. Sorten, 3+1 gratis"
    source_url: str | None = None  # das Angebot bei der Quelle, falls sie es verlinkt


@dataclass(frozen=True, slots=True)
class StoreRef:
    """Was eine Angebotsquelle über einen Laden wissen muss."""

    id: int
    chain: str
    postal_code: str
    market_id: str | None = None


@dataclass(frozen=True, slots=True)
class OfferSnapshotData:
    store_id: int
    source: str
    fetched_at: datetime
    offers: tuple[RawOffer, ...]
    ok: bool
    raw_payload: dict | None = None
    error: str | None = None
    market_label: str | None = None
    market_url: str | None = None  # Angebotsseite des Markts
    source_detail: str | None = None  # woher die Quelle es hat: "offiziell", "Marktguru"

    @property
    def usable(self) -> bool:
        """`status = OK` nur bei Treffern (ARCHITECTURE.md §5): ein leerer Abruf
        darf den letzten guten Snapshot nicht verdraengen."""
        return self.ok and len(self.offers) > 0


@runtime_checkable
class OfferSource(Protocol):
    """Liefert den *ganzen* aktuellen Prospekt eines Ladens. Zugeordnet wird bei uns -
    die Wortsuche der Quellen findet "Schafskäse" nicht, wenn man "Hirtenkäse" sucht."""

    name: str

    def fetch(self, store: StoreRef) -> OfferSnapshotData: ...


# ------------------------------------------------------------------------ Bring!-Katalog


@dataclass(frozen=True, slots=True)
class CatalogSuggestion:
    name: str
    category: str | None
    score: float


@runtime_checkable
class BringCatalog(Protocol):
    def suggest(self, name: str, *, limit: int = 5) -> list[CatalogSuggestion]: ...


# ------------------------------------------------------------------------------- LLM


@dataclass(frozen=True, slots=True)
class MatchVerdict:
    same: bool
    confidence: float = 0.0
    reason: str | None = None


@runtime_checkable
class LlmPort(Protocol):
    """Naht für später. MVP-Implementierung: `NullLlm` (ARCHITECTURE.md §0)."""

    def judge_match(self, offer_name: str, article_name: str) -> MatchVerdict: ...


class NullLlm:
    """Entscheidet nie - Grenzfaelle landen in der "Unzugeordnet"-Ansicht."""

    def judge_match(self, offer_name: str, article_name: str) -> MatchVerdict:
        return MatchVerdict(same=False, confidence=0.0, reason="kein LLM konfiguriert")
