"""offer sources per store

Revision ID: 691ed28ec893
Revises: 9e59545e8814
Create Date: 2026-10-05 18:00:00.000000

Phase 2, Stufe 1: Läden bekommen eine eigene PLZ (Korbunio findet einen Rewe-Markt nur
über dessen PLZ), Angebote Packungsgröße und Warengruppe, und ein Abruf merkt sich,
welchen Markt die Quelle genommen hat und woran er gescheitert ist. Nur neue Spalten -
SQLite kann das ohne Tabellen-Umbau.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = '691ed28ec893'
down_revision: str | None = '9e59545e8814'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("store", sa.Column("postal_code", sa.String(length=5), nullable=True))
    op.add_column("offer", sa.Column("pack", sa.String(length=60), nullable=True))
    op.add_column("offer", sa.Column("category", sa.String(length=60), nullable=True))
    op.add_column(
        "offer_snapshot", sa.Column("market_label", sa.String(length=200), nullable=True)
    )
    op.add_column("offer_snapshot", sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("offer_snapshot", "error")
    op.drop_column("offer_snapshot", "market_label")
    op.drop_column("offer", "category")
    op.drop_column("offer", "pack")
    op.drop_column("store", "postal_code")
