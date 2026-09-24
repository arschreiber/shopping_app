"""Korbunio-Adapter (general_plan.md §7 Strategie Nr. 1, Phase 2).

Korbunio läuft als Sidecar und kennt Edeka (marktgenau), Aldi Nord, Netto MD und Rewe.
Unser Code beschraenkt sich darauf, dessen Antwort in unser Schema zu ueberfuehren -
stirbt das Projekt, wird genau diese Datei ersetzt.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx

from ...ports import OfferSnapshotData, OfferSource, RawOffer

LOG = logging.getLogger(__name__)


class KorbunioOfferSource(OfferSource):
    name = "korbunio"

    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def fetch(
        self, store_id: int, market_id: str | None, queries: list[str]
    ) -> OfferSnapshotData:
        now = datetime.now().astimezone()
        payload = {"zipCode": market_id, "queries": queries}
        try:
            response = httpx.post(
                f"{self._base}/api/v1/compare", json=payload, timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            LOG.warning("Korbunio-Abruf fehlgeschlagen: %s", exc)
            return OfferSnapshotData(
                store_id=store_id,
                source=self.name,
                fetched_at=now,
                offers=(),
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
            )

        offers = tuple(_to_offer(row) for row in _iter_rows(data))
        return OfferSnapshotData(
            store_id=store_id,
            source=self.name,
            fetched_at=now,
            offers=offers,
            ok=True,
            raw_payload=data if isinstance(data, dict) else {"items": data},
        )


def _iter_rows(data) -> list[dict]:
    """Defensiv gegen Formatwechsel: Liste, `results` oder `offers`."""
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("results", "offers", "items", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _to_offer(row: dict) -> RawOffer:
    return RawOffer(
        raw_name=str(row.get("name") or row.get("title") or row.get("product") or "?"),
        price=_decimal(row.get("price") or row.get("offerPrice")),
        old_price=_decimal(row.get("oldPrice") or row.get("regularPrice")),
        brand=row.get("brand"),
        base_price=row.get("basePrice") or row.get("unitPrice"),
        valid_from=_date(row.get("validFrom")),
        valid_to=_date(row.get("validTo") or row.get("validUntil")),
        image_url=row.get("image") or row.get("imageUrl"),
    )


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", ".").replace("€", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _date(value) -> date | None:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
