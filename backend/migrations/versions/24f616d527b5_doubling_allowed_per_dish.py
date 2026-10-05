"""doubling allowed per dish

Revision ID: 24f616d527b5
Revises: acf03dd2bade
Create Date: 2026-09-24 23:04:12.585812

Bewusst *ohne* `batch_alter_table`: SQLite kennt kein ALTER für Constraints, deshalb
baut der Batch-Modus die Tabelle neu (anlegen, kopieren, `drop table dish`, umbenennen).
Mit `foreign_keys=ON` reißt dieses DROP alle Kinderzeilen mit - Zutaten und Kategorien
wären weg. `add column` beherrscht SQLite dagegen nativ.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = '24f616d527b5'
down_revision: str | None = 'acf03dd2bade'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Bestand bleibt verdoppelbar: bisher galt das für jedes 2-Portionen-Gericht.
    op.add_column(
        'dish',
        sa.Column('allow_double', sa.Boolean(), nullable=False, server_default=sa.text('1')),
    )


def downgrade() -> None:
    op.drop_column('dish', 'allow_double')
