"""offer details and target prices

Revision ID: 9d7cd547a923
Revises: 691ed28ec893
Create Date: 2026-10-11 12:00:00.000000

Zwei Wünsche aus dem Alltag mit den ersten Angeboten:

- Ein Angebot soll sich nachprüfen lassen: Prospekttext, Produktbild, Link zur Quelle,
  und beim Abruf die Angebotsseite des Markts samt Art der Quelle.
- Ein Richtpreis pro Artikel (€/kg, €/l oder €/Stück), über dem ein Angebot nicht zählt.
  Dafür wird der Grundpreis jedes Angebots beim Speichern vergleichbar gemacht.

Nur neue Spalten. Bestehende Angebote bekommen die Details erst mit dem nächsten Abruf.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = '9d7cd547a923'
down_revision: str | None = '691ed28ec893'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("article", sa.Column("max_unit_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("offer", sa.Column("description", sa.String(length=300), nullable=True))
    op.add_column("offer", sa.Column("image_url", sa.String(length=500), nullable=True))
    op.add_column("offer", sa.Column("source_url", sa.String(length=500), nullable=True))
    op.add_column("offer", sa.Column("unit_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("offer", sa.Column("unit_price_unit", sa.String(length=10), nullable=True))
    op.add_column(
        "offer_snapshot", sa.Column("market_url", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "offer_snapshot", sa.Column("source_detail", sa.String(length=60), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("offer_snapshot", "source_detail")
    op.drop_column("offer_snapshot", "market_url")
    op.drop_column("offer", "unit_price_unit")
    op.drop_column("offer", "unit_price")
    op.drop_column("offer", "source_url")
    op.drop_column("offer", "image_url")
    op.drop_column("offer", "description")
    op.drop_column("article", "max_unit_price")
