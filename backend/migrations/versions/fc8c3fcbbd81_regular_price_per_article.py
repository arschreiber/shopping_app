"""regular price per article

Revision ID: fc8c3fcbbd81
Revises: 9d7cd547a923
Create Date: 2026-10-12 12:00:00.000000

Normalpreis pro Artikel - was man ohne Angebot zahlt, meist für die Eigenmarke. Eingegeben
wird er so, wie man einkauft ("250 g für 1,29 €"), darum zwei Spalten statt eines
Grundpreises. Unabhängig vom Richtpreis: ein Markenangebot kann sich auch über dem
Normalpreis lohnen. Nur neue Spalten.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = 'fc8c3fcbbd81'
down_revision: str | None = '9d7cd547a923'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("article", sa.Column("regular_pack_amount", sa.Numeric(10, 3), nullable=True))
    op.add_column("article", sa.Column("regular_pack_price", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("article", "regular_pack_price")
    op.drop_column("article", "regular_pack_amount")
