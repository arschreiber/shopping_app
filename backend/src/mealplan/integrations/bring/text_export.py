"""Text-Export als zweite `ShoppingListSync`-Implementierung (ARCHITECTURE.md §5).

Der Montag darf nicht am Bring!-Backend hängen. Bricht der Push, zeigt die UI die
Liste als Text zum Teilen - das ist langsamer, aber nie kaputt.
"""

from __future__ import annotations

from ...ports import ShoppingListSync, SyncItem, SyncResult, SyncState


class TextExportSync(ShoppingListSync):
    name = "text"

    def push(self, desired: list[SyncItem], state: SyncState) -> SyncResult:
        # Bewusst leere created/updated/removed: hier passiert nichts Externes, und die
        # Sync-Historie soll nicht behaupten, Bring! haette Einträge bekommen.
        return SyncResult(ok=True, text_fallback=render(desired), list_uuid=state.list_uuid)


def render(items: list[SyncItem]) -> str:
    if not items:
        return "Einkaufsliste ist leer."
    lines = [f"- {item.name}" + (f": {item.spec}" if item.spec else "") for item in items]
    return "Einkaufsliste\n" + "\n".join(sorted(lines))
