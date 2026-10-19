"""piece size per article

Revision ID: 8e6b1f6de5e7
Revises: fc8c3fcbbd81
Create Date: 2026-10-12 18:00:00.000000

Stückgewicht pro Artikel ("1 Avocado ≈ 200 g"): macht Angebote pro Stück mit Richt- und
Normalpreis eines Gramm-Artikels vergleichbar. Die Spalte gab es seit dem ersten Schema
als `piece_weight_g` (ungenutzt); sie heißt jetzt `piece_size`, weil sie in der Einheit
des Artikels zählt - bei Milliliter-Artikeln also ml ("1 Dose ≈ 400 ml").

Dazu `regular_pack_unit`: der Normalpreis darf auch pro Stück eingegeben werden
("1 Stück für 0,79 €").
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = '8e6b1f6de5e7'
down_revision: str | None = 'fc8c3fcbbd81'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite kann Spalten seit 3.25 umbenennen, ohne die Tabelle neu zu bauen.
    op.execute("ALTER TABLE article RENAME COLUMN piece_weight_g TO piece_size")
    op.add_column("article", sa.Column("regular_pack_unit", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("article", "regular_pack_unit")
    op.execute("ALTER TABLE article RENAME COLUMN piece_size TO piece_weight_g")
