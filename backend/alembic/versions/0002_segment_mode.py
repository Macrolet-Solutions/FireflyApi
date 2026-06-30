"""add segment mode

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-30

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("firefly_segments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "mode",
                sa.String(length=16),
                nullable=False,
                server_default="static",
            )
        )
        batch_op.create_check_constraint(
            "ck_firefly_segments_mode",
            "mode IN ('static', 'dynamic')",
        )


def downgrade() -> None:
    with op.batch_alter_table("firefly_segments") as batch_op:
        batch_op.drop_constraint("ck_firefly_segments_mode", type_="check")
        batch_op.drop_column("mode")
