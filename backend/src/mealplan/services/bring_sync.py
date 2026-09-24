"""Push der Einkaufsliste nach Bring! (ARCHITECTURE.md §5).

Der Service baut den Soll-Zustand, lädt den bekannten Ist-Zustand aus
`bring_sync_item`, uebergibt beides dem Port und protokolliert das Ergebnis in
`sync_run`. Ein Bruch ist damit in der UI sichtbar (§8) statt still.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..domain.enums import ListStatus, SyncKind, SyncStatus
from ..ports import ShoppingListSync, SyncItem, SyncResult, SyncState, SyncStateItem
from .shopping_list import get_list, to_lines


@dataclass(frozen=True, slots=True)
class PushOutcome:
    result: SyncResult
    run_id: int
    items_sent: int


def build_desired(session: Session, iso: str) -> list[SyncItem]:
    """Soll-Zustand: alles, was nicht abgehakt ist.

    Der Name ist der Bring!-Katalogname, wenn einer zugeordnet ist - nur dann zeigt
    Bring! Icon und Kategorie (general_plan.md §8 Nr. 9). Die Menge wandert in die
    Spezifikation, weil Bring! kein strukturiertes Mengenfeld hat.
    """
    shopping = get_list(session, iso, rebuild_first=False)
    return [
        SyncItem(
            article_id=line.article_id,
            name=line.bring_name or line.article_name,
            spec=line.spec_text if line.quantity is not None else "",
        )
        for line in to_lines(session, shopping)
        if not line.have_already
    ]


def load_state(session: Session) -> SyncState:
    rows = list(session.scalars(select(m.BringSyncItem)))
    list_uuid = rows[0].bring_list_uuid if rows else None
    return SyncState(
        list_uuid=list_uuid,
        items=tuple(
            SyncStateItem(
                article_id=row.article_id,
                item_uuid=row.bring_item_uuid,
                name=row.last_name,
                spec=row.last_spec,
            )
            for row in rows
        ),
    )


def push(session: Session, iso: str, sync: ShoppingListSync) -> PushOutcome:
    desired = build_desired(session, iso)
    state = load_state(session)

    run = m.SyncRun(kind=SyncKind.BRING_PUSH.value, status=SyncStatus.OK.value)
    session.add(run)
    session.flush()

    result = sync.push(desired, state)

    run.finished_at = datetime.now(UTC)
    run.status = (SyncStatus.OK if result.ok else SyncStatus.FAILED).value
    run.error = result.error
    run.summary = {**result.summary, "adapter": sync.name, "items": len(desired)}

    if result.ok:
        _remember(session, desired, result)
        shopping = get_list(session, iso, rebuild_first=False)
        shopping.status = ListStatus.SENT.value
        shopping.sent_at = datetime.now(UTC)

    session.flush()
    return PushOutcome(result=result, run_id=run.id, items_sent=len(desired))


def _remember(session: Session, desired: list[SyncItem], result: SyncResult) -> None:
    """Merkt sich pro Artikel, was wir geschrieben haben - Grundlage des nächsten Diffs."""
    if not result.list_uuid:
        return
    existing = {
        row.article_id: row
        for row in session.scalars(
            select(m.BringSyncItem).where(m.BringSyncItem.bring_list_uuid == result.list_uuid)
        )
    }
    wanted_ids = {item.article_id for item in desired}
    now = datetime.now(UTC)

    for item in desired:
        row = existing.get(item.article_id)
        if row is None:
            session.add(
                m.BringSyncItem(
                    article_id=item.article_id,
                    bring_list_uuid=result.list_uuid,
                    bring_item_uuid=result.item_uuids.get(item.article_id),
                    last_name=item.name,
                    last_spec=item.spec,
                    last_pushed_at=now,
                )
            )
        else:
            row.bring_item_uuid = result.item_uuids.get(item.article_id, row.bring_item_uuid)
            row.last_name = item.name
            row.last_spec = item.spec
            row.last_pushed_at = now

    for article_id, row in existing.items():
        if article_id not in wanted_ids:
            session.delete(row)


def recent_runs(session: Session, *, limit: int = 20) -> list[m.SyncRun]:
    return list(
        session.scalars(
            select(m.SyncRun).order_by(m.SyncRun.started_at.desc()).limit(limit)
        )
    )


def last_run(session: Session, kind: SyncKind) -> m.SyncRun | None:
    return session.scalar(
        select(m.SyncRun)
        .where(m.SyncRun.kind == kind.value, m.SyncRun.status == SyncStatus.OK.value)
        .order_by(m.SyncRun.started_at.desc())
        .limit(1)
    )
