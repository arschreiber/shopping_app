"""min offer amount

Revision ID: a3c5e8d21b47
Revises: 9f71016f929f
Create Date: 2026-10-13 22:00:00.000000

"Angebote erst ab ..." pro Artikel: Heidelbeeren zählen erst ab 400 g. Kleinere
Packungen gelten für den Artikel nicht - wie Angebote über dem Richtpreis. Bestehende
Artikel bleiben ohne Grenze.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = 'a3c5e8d21b47'
down_revision: str | None = '9f71016f929f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("article", sa.Column("min_offer_amount", sa.Numeric(10, 3), nullable=True))


def downgrade() -> None:
    op.drop_column("article", "min_offer_amount")
