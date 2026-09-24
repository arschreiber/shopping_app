"""Bring!-Katalog (general_plan.md §8 Nr. 9).

Icon und Kategorie erscheinen in Bring! nur, wenn der Artikelname exakt einem
Katalogeintrag entspricht. Der Katalog ist frei abrufbar (~380 Artikel) und wird beim
Start nach `data/catalog/` gecacht - offline funktioniert die Zuordnung damit weiter.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from ...matching.normalize import rank
from ...ports import CatalogSuggestion

LOG = logging.getLogger(__name__)

CATALOG_URL = "https://web.getbring.com/locale/catalog.de-DE.json"
ARTICLES_URL = "https://web.getbring.com/locale/articles.de-DE.json"
CACHE_NAME = "catalog.de-DE.json"


class FileBringCatalog:
    """Liest den gecachten Katalog. Ohne Cache: leere Vorschläge, keine Ausnahme."""

    def __init__(self, catalog_dir: Path) -> None:
        self._dir = catalog_dir
        self._entries: dict[str, str | None] | None = None

    @property
    def path(self) -> Path:
        return self._dir / CACHE_NAME

    def _load(self) -> dict[str, str | None]:
        if self._entries is not None:
            return self._entries
        if not self.path.exists():
            LOG.info("Bring!-Katalog nicht gecacht (%s) - Vorschläge deaktiviert", self.path)
            self._entries = {}
            return self._entries
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOG.warning("Bring!-Katalog unlesbar: %s", exc)
            self._entries = {}
            return self._entries
        self._entries = _flatten(payload)
        return self._entries

    def suggest(self, name: str, *, limit: int = 5) -> list[CatalogSuggestion]:
        entries = self._load()
        if not entries:
            return []
        names = dict(enumerate(entries))
        ranked = rank(name, names, limit=limit)
        out = []
        for index, score in ranked:
            entry = names[index]
            out.append(CatalogSuggestion(name=entry, category=entries[entry], score=score))
        return out

    def is_cached(self) -> bool:
        return self.path.exists()

    def count(self) -> int:
        return len(self._load())


def _flatten(payload: dict) -> dict[str, str | None]:
    """Der Katalog ist nach Sektionen gruppiert: `{"catalog": {"sections": [...]}}`.

    Das Format hat sich schon geaendert (Plan §6: Locale-Bruch 03/2024), darum
    defensiv - unbekannte Struktur ergibt einen leeren Katalog, keinen Absturz.
    """
    out: dict[str, str | None] = {}
    catalog = payload.get("catalog", payload)
    sections = catalog.get("sections", []) if isinstance(catalog, dict) else []
    for section in sections:
        if not isinstance(section, dict):
            continue
        category = section.get("name") or section.get("sectionId")
        for item in section.get("items", []):
            if isinstance(item, dict):
                name = item.get("name") or item.get("itemId")
                if name:
                    out[str(name)] = category
            elif isinstance(item, str):
                out[item] = category
    return out


def refresh_cache(catalog_dir: Path, *, timeout: float = 15.0) -> int:
    """Lädt den Katalog neu. Gibt die Anzahl Einträge zurück, 0 bei Fehler."""
    catalog_dir.mkdir(parents=True, exist_ok=True)
    target = catalog_dir / CACHE_NAME
    try:
        response = httpx.get(CATALOG_URL, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        LOG.warning("Bring!-Katalog konnte nicht geladen werden: %s", exc)
        return 0
    entries = _flatten(payload)
    if not entries:
        LOG.warning("Bring!-Katalog hat ein unerwartetes Format - Cache nicht ersetzt")
        return 0
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return len(entries)
