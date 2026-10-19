"""collector_cursors.pending, container_events

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-19 15:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("collector_cursors") as batch:
        batch.add_column(sa.Column("pending", sa.Text(), nullable=True))
    op.create_table(
        "container_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("container", sa.Text(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("pushed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("container", "event", "at", name="uq_container_events_key"),
    )
    op.create_index("ix_container_events_at", "container_events", ["at"])


def downgrade() -> None:
    op.drop_index("ix_container_events_at", table_name="container_events")
    op.drop_table("container_events")
    with op.batch_alter_table("collector_cursors") as batch:
        batch.drop_column("pending")
