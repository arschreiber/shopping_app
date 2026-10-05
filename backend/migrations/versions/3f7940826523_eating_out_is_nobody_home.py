"""eating out is nobody home

Revision ID: 3f7940826523
Revises: bb1c22ee6a86
Create Date: 2026-10-04 12:00:00.000000

"auswärts" und "niemand da" bedeuten im Raster dasselbe: hier wird nicht gekocht. Statt
zwei Zuständen, die sich nur in der Darstellung unterscheiden, gibt es nur noch
"niemand da" (0 zu Hause, 0 mitnehmen). Reine Datenmigration, das Schema bleibt.
"""
from __future__ import annotations

from alembic import op


revision: str = '3f7940826523'
down_revision: str | None = 'bb1c22ee6a86'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ein auswärts-Slot hatte kein Gericht (das Raster hat es beim Speichern entfernt);
    # sicher ist sicher - samt Reste-Karten, die aus ihm ziehen würden.
    op.execute(
        "delete from slot_assignment where slot_id in "
        "(select id from slot where special = 'EATING_OUT') "
        "or leftover_source_slot_id in (select id from slot where special = 'EATING_OUT')"
    )
    op.execute(
        "update slot set special = 'NONE', eaters_home = 0, packed_portions = 0, "
        "packed_fresh = 0 where special = 'EATING_OUT'"
    )


def downgrade() -> None:
    # Nicht umkehrbar: welche "niemand da"-Slots früher "auswärts" hießen, ist nicht
    # mehr bekannt - und für den Planer war es ohnehin dasselbe.
    pass
