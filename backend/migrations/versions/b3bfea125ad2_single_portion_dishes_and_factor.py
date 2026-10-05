"""single-portion dishes and cooking factor

Revision ID: b3bfea125ad2
Revises: 24f616d527b5
Create Date: 2026-10-03 00:40:00.000000

1-Portionen-Gerichte, die doppelt oder dreifach gekocht werden. Dafür wird aus
`slot_assignment.doubled` (ja/nein) ein Faktor 1..3, und `dish` bekommt `allow_triple`.

Die Spalten kann SQLite nativ anlegen und entfernen. Die erweiterte Prüfung
`portions in (1, 2, 3)` dagegen nicht: Ein CHECK lässt sich nur ändern, indem die Tabelle
neu gebaut wird (anlegen, kopieren, `drop table dish`, umbenennen). Mit `foreign_keys=ON`
reißt dieses DROP per ON DELETE CASCADE Zutaten, Kategorien, Kochhistorie und
Zuweisungen mit. Deshalb läuft genau dieser Neubau mit abgeschalteten Fremdschlüsseln,
und danach prüft `foreign_key_check`, dass keine Referenz ins Leere zeigt.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from alembic import op
import sqlalchemy as sa


revision: str = 'b3bfea125ad2'
down_revision: str | None = '24f616d527b5'
branch_labels = None
depends_on = None


@contextmanager
def _foreign_keys_off() -> Iterator[None]:
    # Die PRAGMA wirkt nur außerhalb einer Transaktion - daher der Autocommit-Block.
    context = op.get_context()
    with context.autocommit_block():
        op.execute("PRAGMA foreign_keys=OFF")
    try:
        yield
        dangling = op.get_bind().execute(sa.text("PRAGMA foreign_key_check")).fetchall()
        if dangling:
            raise RuntimeError(f"Neubau von 'dish' hat Referenzen verloren: {dangling}")
    finally:
        with context.autocommit_block():
            op.execute("PRAGMA foreign_keys=ON")


def _rebuild_portions_check(allowed: str) -> None:
    with _foreign_keys_off(), op.batch_alter_table('dish', recreate='always') as batch:
        batch.drop_constraint('ck_dish_portions', type_='check')
        batch.create_check_constraint('ck_dish_portions', f'portions in ({allowed})')


def upgrade() -> None:
    op.add_column(
        'slot_assignment',
        sa.Column('factor', sa.Integer(), nullable=False, server_default=sa.text('1')),
    )
    op.execute("update slot_assignment set factor = 2 where doubled")
    op.drop_column('slot_assignment', 'doubled')

    op.add_column(
        'dish',
        sa.Column('allow_triple', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    )
    _rebuild_portions_check('1, 2, 3')


def downgrade() -> None:
    # Ohne 1-Portionen-Gerichte: die gibt es im alten Schema nicht. Löschen statt
    # stillschweigend umdeuten - der Downgrade ist ein Notausgang, kein Alltag.
    op.execute("delete from dish where portions = 1")
    _rebuild_portions_check('2, 3')
    op.drop_column('dish', 'allow_triple')

    op.add_column(
        'slot_assignment',
        sa.Column('doubled', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    )
    op.execute("update slot_assignment set doubled = 1 where factor = 2")
    op.drop_column('slot_assignment', 'factor')
