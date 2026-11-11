"""label micros per article

Revision ID: d4a8b1c35e72
Revises: c7d2e4f19a60
Create Date: 2026-11-10 23:00:00.000000

Vitamine und Mineralstoffe vom Etikett, je Artikel als JSON `{Code: Wert}` (je 100 g /
100 ml / Stück, Anzeigeeinheit). Sie gelten je Nährstoff vor dem BLS - für Produkte,
die der BLS nicht kennt (Proteinpulver) oder die angereichert sind.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = 'd4a8b1c35e72'
down_revision: str | None = 'c7d2e4f19a60'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("article", sa.Column("label_micros", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("article", "label_micros")
