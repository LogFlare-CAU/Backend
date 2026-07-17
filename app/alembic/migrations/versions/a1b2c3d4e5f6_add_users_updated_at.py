"""Add users.updated_at

Revision ID: a1b2c3d4e5f6
Revises: e8e593517107
Create Date: 2026-07-15 20:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e8e593517107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(), nullable=True, comment="마지막 수정 시각"),
    )


def downgrade() -> None:
    op.drop_column("users", "updated_at")
