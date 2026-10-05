"""two effort levels

Revision ID: 9e59545e8814
Revises: 3f7940826523
Create Date: 2026-10-04 21:51:58.613827

Aufwand und Zeit haben nur noch zwei Stufen: ein Gericht ist "normal" oder "schnell",
eine Mahlzeit hat "normale" oder "wenig" Zeit. "aufwendig" wird "normal", "viel Zeit"
wird "normale Zeit", und "keine Zeit" (nur Reste) wird "wenig Zeit" - das, was dem am
nächsten kommt. Reine Datenmigration, die Spalten sind Strings ohne CHECK.
"""
from __future__ import annotations

from alembic import op


revision: str = '9e59545e8814'
down_revision: str | None = '3f7940826523'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("update dish set effort = 'NORMAL' where effort = 'ELABORATE'")
    op.execute("update slot set time_budget = 'NORMAL' where time_budget = 'PLENTY'")
    op.execute("update slot set time_budget = 'LITTLE' where time_budget = 'NONE'")


def downgrade() -> None:
    # "aufwendig" und "keine Zeit" lassen sich nicht zurückgewinnen; "normale Zeit" schon.
    op.execute("update slot set time_budget = 'PLENTY' where time_budget = 'NORMAL'")
