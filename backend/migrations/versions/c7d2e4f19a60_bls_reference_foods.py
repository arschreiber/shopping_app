"""bls reference foods

Revision ID: c7d2e4f19a60
Revises: a3c5e8d21b47
Create Date: 2026-11-10 21:00:00.000000

Mikronährstoffe aus dem Bundeslebensmittelschlüssel (BLS 4.0, CC BY 4.0): eine
Referenztabelle `bls_food` (nur die Nährstoffe, die die App zeigt) und je Artikel die
Verknüpfung dorthin. Bestehende Artikel bleiben offen, bis jemand sie zuordnet.

Ohne `batch_alter_table`, aus demselben Grund wie in acf03dd2bade.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = 'c7d2e4f19a60'
down_revision: str | None = 'a3c5e8d21b47'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bls_food",
        sa.Column("code", sa.String(length=10), primary_key=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("name_en", sa.String(length=300), nullable=True),
        sa.Column("nutrients", sa.JSON(), nullable=False),
    )
    op.add_column("article", sa.Column("bls_code", sa.String(length=10), nullable=True))
    op.add_column(
        "article", sa.Column("bls_grams_per_unit", sa.Numeric(10, 3), nullable=True)
    )
    op.add_column(
        "article",
        sa.Column("bls_skip", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("article", "bls_skip")
    op.drop_column("article", "bls_grams_per_unit")
    op.drop_column("article", "bls_code")
    op.drop_table("bls_food")
