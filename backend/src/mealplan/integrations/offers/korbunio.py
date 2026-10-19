"""Korbunio-Adapter (general_plan.md §7 Strategie Nr. 1, Phase 2).

Korbunio (github.com/lesecuritae/Korbunio) läuft als Sidecar im Compose-Netz und holt
die Prospekte von den Händlerseiten bzw. aus marktguru. Unser Code beschränkt sich
darauf, dessen Antwort in unser Schema zu überführen - stirbt das Projekt, wird genau
diese Datei ersetzt.

Format geprüft am 5.10.2026 gegen Version 0.1.57 (PLZ 49078):
`POST /api/v1/compare` mit `postal_code`, `retailers`, optional `rewe_market_id` /
`netto_market_id`, ohne `keywords` = der ganze Prospekt, höchstens 100 pro Seite.
Was dabei auffiel und hier abgefangen wird:

- Ein "statt"-Preis fehlt fast immer: `regular_price` ist dann gleich dem Angebotspreis.
  Nur ein *höherer* regulärer Preis wird zum `old_price`.
- `valid_from`/`valid_until` liefert nur Rewe; sonst steht die Gültigkeit als Text in
  `validity` ("05.10.–10.10.2026"). Fehlt beides, gilt das Angebot bis Samstag.
- Bei Edeka nimmt Korbunio den ersten Markt zur PLZ und lässt sich nicht umstimmen.
  Welchen Markt es genommen hat, steht in `retailer_markets` - das reichen wir durch.
- Aldi Nord (geprüft 13.10.2026): bei Obst und Gemüse ist `pack` leer, die Packung
  steht hinten im Text ("Klasse 1; Ursprung siehe Etikett · 2er-Schale") - die wird
  zur Packung.
"""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

from ...domain.enums import Chain
from ...ports import OfferSnapshotData, RawOffer, StoreRef

LOG = logging.getLogger(__name__)

# Unsere Kette -> Korbunios Händlername
RETAILER: dict[Chain, str] = {
    Chain.EDEKA: "EDEKA",
    Chain.REWE: "REWE",
    Chain.NETTO_MD: "Netto Marken-Discount",
    Chain.ALDI_NORD: "ALDI Nord",
    Chain.COMBI: "Combi",
}
# Nur bei diesen Ketten lässt sich ein bestimmter Markt wählen.
MARKET_PARAM: dict[Chain, str] = {
    Chain.REWE: "rewe_market_id",
    Chain.NETTO_MD: "netto_market_id",
}
PAGE_SIZE = 100  # Korbunios Obergrenze
MAX_PAGES = 20  # ein Prospekt hat 150-300 Angebote; das hier ist nur die Notbremse

_VALIDITY = re.compile(
    r"(\d{1,2})\.(\d{1,2})\.(\d{4})?\s*[–—-]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})?"
)


class KorbunioOfferSource:
    name = "korbunio"

    def __init__(self, base_url: str, *, timeout: float = 90.0) -> None:
        # Großzügig: eine neue PLZ lädt Korbunio erst von allen Händlerseiten (10-20 s).
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def fetch(self, store: StoreRef) -> OfferSnapshotData:
        now = datetime.now().astimezone()
        chain = Chain(store.chain)
        retailer = RETAILER.get(chain)
        if retailer is None:
            return self._failed(store, now, f"Korbunio kennt die Kette {chain.value} nicht")

        request: dict = {
            "postal_code": store.postal_code,
            "retailers": [retailer],
            "view": "all",
            "sort": "product",
            "page_size": PAGE_SIZE,
            # Produktbilder zum Nachprüfen eines Angebots; ohne den Schalter lässt
            # Korbunio sie weg.
            "include_image_urls": True,
        }
        if store.market_id and (param := MARKET_PARAM.get(chain)):
            request[param] = store.market_id

        pages: list[dict] = []
        try:
            with httpx.Client(timeout=self._timeout) as client:
                for page in range(1, MAX_PAGES + 1):
                    response = client.post(
                        f"{self._base}/api/v1/compare", json={**request, "page": page}
                    )
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict) or not isinstance(data.get("offers"), list):
                        raise ValueError("unbekanntes Antwortformat (kein 'offers')")
                    pages.append(data)
                    if not data.get("has_next"):
                        break
        except (httpx.HTTPError, ValueError) as exc:
            LOG.warning("Korbunio-Abruf für Laden %s fehlgeschlagen: %s", store.id, exc)
            return self._failed(store, now, _describe(exc))

        today = now.date()
        offers = tuple(
            _to_offer(row, today)
            for page in pages
            for row in page["offers"]
            if isinstance(row, dict) and row.get("retailer") == retailer
        )
        return OfferSnapshotData(
            store_id=store.id,
            source=self.name,
            fetched_at=now,
            offers=offers,
            ok=True,
            raw_payload={"pages": [_without_links(page) for page in pages]},
            error=None if offers else _why_empty(pages[0], retailer),
            market_label=_market_label(pages[0], retailer),
            market_url=_market_url(pages[0], retailer),
            source_detail=(pages[0].get("source_states") or {}).get(retailer) or None,
        )

    def _failed(self, store: StoreRef, now: datetime, error: str) -> OfferSnapshotData:
        return OfferSnapshotData(
            store_id=store.id, source=self.name, fetched_at=now, offers=(), ok=False,
            error=error,
        )


def _describe(exc: Exception) -> str:
    if isinstance(exc, httpx.ConnectError):
        return "Korbunio nicht erreichbar - läuft der Container (Profil 'offers')?"
    if isinstance(exc, httpx.TimeoutException):
        return "Korbunio hat nicht rechtzeitig geantwortet"
    if isinstance(exc, httpx.HTTPStatusError):
        detail = ""
        with contextlib.suppress(ValueError, AttributeError):
            detail = str(exc.response.json().get("detail") or "")
        code = exc.response.status_code
        return f"Korbunio antwortet {code}" + (f": {detail}" if detail else "")
    return f"{type(exc).__name__}: {exc}"


def _why_empty(page: dict, retailer: str) -> str:
    warnings = [w for w in page.get("warnings") or [] if isinstance(w, str) and retailer in w]
    if warnings:
        return warnings[0]
    state = (page.get("source_states") or {}).get(retailer)
    return f"keine Angebote ({state})" if state else "keine Angebote"


def _market_label(page: dict, retailer: str) -> str | None:
    for market in page.get("retailer_markets") or []:
        if isinstance(market, dict) and market.get("retailer") == retailer:
            label = str(market.get("label") or "").removeprefix("Angebote zu ").strip()
            return label or None
    return None


def _market_url(page: dict, retailer: str) -> str | None:
    for market in page.get("retailer_markets") or []:
        if isinstance(market, dict) and market.get("retailer") == retailer:
            return _http(market.get("url"))
    return None


def _http(value) -> str | None:
    """Nur echte Web-Adressen weitergeben - die Oberfläche macht Links daraus."""
    text = str(value or "").strip()
    return text if text.startswith(("https://", "http://")) else None


def _without_links(page: dict) -> dict:
    """Für das Nachverarbeiten aufheben - ohne Korbunios signierte Ergebnis-Links."""
    return {key: value for key, value in page.items() if key not in ("result_url", "search_id")}


def _to_offer(row: dict, today: date) -> RawOffer:
    price = _decimal(row.get("checkout_price"))
    if price is None:
        price = _decimal(row.get("effective_price"))
    regular = _decimal(row.get("regular_price"))
    valid_from, valid_to = _date(row.get("valid_from")), _date(row.get("valid_until"))
    if valid_to is None:
        valid_from, valid_to = _validity_text(row.get("validity"), today) or (valid_from, None)
    if valid_to is None:
        valid_to = _saturday(today)
    return RawOffer(
        raw_name=str(row.get("product") or row.get("name") or "?").strip(),
        price=price,
        old_price=regular if regular and price and regular > price else None,
        brand=(row.get("brand") or None),
        base_price=(row.get("unit_price") or None),
        pack=_pack(row),
        category=(row.get("category") or None),
        valid_from=valid_from,
        valid_to=valid_to,
        image_url=_http(row.get("image_url")),
        description=(str(row.get("description") or "").strip() or None),
        source_url=_http(row.get("product_url")) or _http(row.get("source_url")),
    )


def _pack(row: dict) -> str | None:
    """Die Packung - bei Aldi notfalls das kurze Ende des Texts nach "·"."""
    pack = str(row.get("pack") or "").strip()
    if pack:
        return pack
    *text, tail = str(row.get("description") or "").rsplit("·", 1)
    tail = tail.strip()
    return tail if text and 0 < len(tail) <= 30 and "http" not in tail else None


def _validity_text(text, today: date) -> tuple[date, date] | None:
    """"05.10.–10.10.2026" / "05.10. – 10.10.2026" -> (5.10., 10.10.)."""
    match = _VALIDITY.search(str(text or ""))
    if not match:
        return None
    d1, m1, y1, d2, m2, y2 = match.groups()
    end_year = int(y2 or y1 or today.year)
    try:
        end = date(end_year, int(m2), int(d2))
        start = date(int(y1) if y1 else end_year, int(m1), int(d1))
        if start > end:  # "28.12.–02.01.2027"
            start = start.replace(year=start.year - 1)
    except ValueError:
        return None
    return start, end


def _saturday(today: date) -> date:
    """Prospekte laufen Mo-Sa; sonntags gilt schon der nächste."""
    return today + timedelta(days=(5 - today.weekday()) % 7)


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", ".").replace("€", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
