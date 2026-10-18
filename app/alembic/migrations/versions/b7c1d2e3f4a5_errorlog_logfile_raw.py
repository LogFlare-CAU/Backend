"""Add errorlogs.logfile_id, errorlogs.raw, indexes; normalise level case

Revision ID: b7c1d2e3f4a5
Revises: a1b2c3d4e5f6
Create Date: 2026-10-18 17:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b7c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("errorlogs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "logfile_id", sa.Integer(), nullable=True, comment="연결된 로그 파일 ID (없으면 NULL)"
            )
        )
        batch_op.add_column(
            sa.Column("raw", sa.Text(), nullable=True, comment="원본 로그 페이로드 (최대 64KB)")
        )
        batch_op.create_foreign_key(
            "fk_errorlogs_logfile_id",
            "log_files",
            ["logfile_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_errorlogs_project_ts", ["project_id", "timestamp"])
        batch_op.create_index("ix_errorlogs_level", ["level"])
    op.execute("UPDATE errorlogs SET level = UPPER(level)")


def downgrade() -> None:
    with op.batch_alter_table("errorlogs") as batch_op:
        batch_op.drop_index("ix_errorlogs_level")
        batch_op.drop_index("ix_errorlogs_project_ts")
        batch_op.drop_constraint("fk_errorlogs_logfile_id", type_="foreignkey")
        batch_op.drop_column("raw")
        batch_op.drop_column("logfile_id")
