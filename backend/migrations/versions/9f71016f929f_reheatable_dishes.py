"""reheatable dishes

Revision ID: 9f71016f929f
Revises: 8e6b1f6de5e7
Create Date: 2026-10-13 12:00:00.000000

"aufwärmbar" pro Gericht. Was sich nicht aufwärmen lässt, darf nicht übrig bleiben: der
Planer schlägt es nur in einer Größe vor, die genau aufgeht. Alle bestehenden Gerichte
bleiben aufwärmbar - nur eine neue Spalte.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = '9f71016f929f'
down_revision: str | None = '8e6b1f6de5e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dish",
        sa.Column("reheatable", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )


def downgrade() -> None:
    op.drop_column("dish", "reheatable")
