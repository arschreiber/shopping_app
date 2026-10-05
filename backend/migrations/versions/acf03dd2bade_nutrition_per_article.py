"""nutrition per article

Revision ID: acf03dd2bade
Revises: 8bf1f127767c
Create Date: 2026-09-24 22:09:58.137942

Ohne `batch_alter_table`: der Batch-Modus baut die Tabelle unter SQLite neu und nimmt
beim `drop table` per `foreign_keys=ON` alle Kinderzeilen mit (siehe 24f616d527b5).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = 'acf03dd2bade'
down_revision: str | None = '8bf1f127767c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ('kcal', 'carbs_g', 'fat_g', 'protein_g'):
        op.add_column('article', sa.Column(column, sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade() -> None:
    for column in ('protein_g', 'fat_g', 'carbs_g', 'kcal'):
        op.drop_column('article', column)
