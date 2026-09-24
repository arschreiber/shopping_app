"""Bring!-Adapter (general_plan.md §6, ARCHITECTURE.md §5).

Drei Dinge sind hier bewusst so gebaut:

1. **Push ist ein Diff, kein Neuschreiben.** Der Soll-Zustand wird gegen die
   gespeicherten eigenen UUIDs verglichen: create / update-spec / remove. Einträge
   ohne unsere UUID werden *nie* angefasst - so kann der Sync keine Duplikate und keine
   Verluste erzeugen (Plan §8 Nr. 8).
2. **Eigenes Bot-Konto.** Zugangsdaten kommen aus der Konfiguration und gehören einem
   separaten Bring!-Account (`name+app@...`), der zur gemeinsamen Liste eingeladen ist.
3. **Fehler bleiben lokal.** Jede Ausnahme wird zu `SyncResult(ok=False, ...)` mit
   Text-Fallback. Ein Bring!-Bruch legt den Montag nicht still.

`bring-api` ist async; die Synchronisation nach aussen ist bewusst blockierend, weil
die App genau einen Writer hat und der Push ein Nutzer-Klick ist.
"""

from __future__ import annotations

import asyncio
import logging

from ...ports import ShoppingListSync, SyncItem, SyncResult, SyncState
from .text_export import render

LOG = logging.getLogger(__name__)


class BringSync(ShoppingListSync):
    name = "bring"

    def __init__(self, email: str, password: str, list_name: str | None = None) -> None:
        self._email = email
        self._password = password
        self._list_name = list_name

    # ------------------------------------------------------------------ oeffentlich

    def push(self, desired: list[SyncItem], state: SyncState) -> SyncResult:
        try:
            return asyncio.run(self._push(desired, state))
        except Exception as exc:
            LOG.warning("Bring!-Push fehlgeschlagen: %s", exc, exc_info=True)
            return SyncResult(
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                text_fallback=render(desired),
                list_uuid=state.list_uuid,
            )

    # --------------------------------------------------------------------- intern

    async def _push(self, desired: list[SyncItem], state: SyncState) -> SyncResult:
        import aiohttp
        from bring_api import Bring

        async with aiohttp.ClientSession() as http:
            bring = Bring(http, self._email, self._password)
            await bring.login()
            list_uuid = state.list_uuid or await self._resolve_list(bring)

            known = {item.article_id: item for item in state.items}
            wanted = {item.article_id: item for item in desired}

            created: list[SyncItem] = []
            updated: list[SyncItem] = []
            removed: list[str] = []
            uuids: dict[int, str] = {}

            for article_id, item in wanted.items():
                previous = known.get(article_id)
                if previous is None or previous.item_uuid is None:
                    await bring.save_item(list_uuid, item.name, item.spec)
                    created.append(item)
                elif previous.name != item.name or (previous.spec or "") != item.spec:
                    # Namenswechsel = altes Item weg, neues hin: der Name ist in Bring!
                    # der Schluessel für Icon und Kategorie.
                    if previous.name != item.name:
                        await bring.remove_item(list_uuid, previous.name)
                        await bring.save_item(list_uuid, item.name, item.spec)
                    else:
                        await bring.save_item(list_uuid, item.name, item.spec)
                    updated.append(item)
                uuids[article_id] = previous.item_uuid if previous else item.name

            # Was wir mal geschrieben haben und jetzt nicht mehr wollen, nehmen wir
            # zurück - aber nur das.
            for article_id, previous in known.items():
                if article_id not in wanted:
                    await bring.remove_item(list_uuid, previous.name)
                    removed.append(previous.name)

            return SyncResult(
                ok=True,
                created=tuple(created),
                updated=tuple(updated),
                removed=tuple(removed),
                list_uuid=list_uuid,
                item_uuids=uuids,
            )

    async def _resolve_list(self, bring) -> str:
        lists = await bring.load_lists()
        entries = getattr(lists, "lists", lists)
        if not entries:
            raise RuntimeError("Der Bring!-Account sieht keine Liste - Einladung fehlt?")
        if self._list_name:
            for entry in entries:
                if getattr(entry, "name", None) == self._list_name:
                    return getattr(entry, "listUuid", None) or entry.list_uuid
            raise RuntimeError(f"Bring!-Liste '{self._list_name}' nicht gefunden")
        first = entries[0]
        return getattr(first, "listUuid", None) or first.list_uuid
