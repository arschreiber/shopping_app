"""fresh take-along per slot

Revision ID: bb1c22ee6a86
Revises: b3bfea125ad2
Create Date: 2026-10-03 12:00:00.000000

Mitnehm-Portionen sind entweder vorgekocht (bevorzugt Reste - wie bisher) oder werden in
derselben Mahlzeit frisch gekocht, etwa fürs Abendessen vor einem Termin. Nur eine neue
Spalte: `add column` kann SQLite nativ, ohne die Tabelle neu zu bauen.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = 'bb1c22ee6a86'
down_revision: str | None = 'b3bfea125ad2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Bestand bleibt "vorgekocht" - genau das bisherige Verhalten.
    op.add_column(
        'slot',
        sa.Column('packed_fresh', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    )


def downgrade() -> None:
    op.drop_column('slot', 'packed_fresh')
