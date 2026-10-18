"""error_groups, collector_cursors, errorlogs.fingerprint (+ backfill)

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-10-18 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "error_groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fingerprint", sa.Text(), nullable=False, unique=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("errortype", sa.Text(), nullable=True),
        sa.Column("sample", sa.Text(), nullable=False),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("ignored", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "collector_cursors",
        sa.Column("container", sa.Text(), primary_key=True),
        sa.Column("last_ts", sa.DateTime(), nullable=False),
    )
    with op.batch_alter_table("errorlogs") as batch:
        batch.add_column(sa.Column("fingerprint", sa.Text(), nullable=True))
        batch.create_index("ix_errorlogs_fingerprint", ["fingerprint"])

    _backfill(op.get_bind())


def _backfill(bind) -> None:
    from routes.collector.parse import fingerprint, mask_secrets

    names = dict(bind.execute(sa.text("SELECT id, name FROM projects")).all())
    rows = bind.execute(
        sa.text("SELECT id, project_id, errortype, message, level, timestamp FROM errorlogs ORDER BY timestamp, id")
    ).all()
    groups: dict[str, dict] = {}
    for id_, pid, etype, msg, level, ts in rows:
        msg = mask_secrets(msg)  # 묶음 지문·대표 메시지는 가린 문장 기준 (record_entry 와 동일)
        fp = fingerprint(names.get(pid, ""), level.upper(), msg)
        bind.execute(sa.text("UPDATE errorlogs SET fingerprint=:fp WHERE id=:id"), {"fp": fp, "id": id_})
        g = groups.get(fp)
        if g is None:
            groups[fp] = {"fingerprint": fp, "project_id": pid, "level": level.upper(), "errortype": etype,
                          "sample": msg, "first_seen": ts, "last_seen": ts, "count": 1}
        else:
            g["count"] += 1
            g["last_seen"] = ts
    if groups:
        bind.execute(
            sa.text(
                "INSERT INTO error_groups (fingerprint, project_id, level, errortype, sample, first_seen, last_seen, count, ignored) "
                "VALUES (:fingerprint, :project_id, :level, :errortype, :sample, :first_seen, :last_seen, :count, 0)"
            ),
            list(groups.values()),
        )


def downgrade() -> None:
    with op.batch_alter_table("errorlogs") as batch:
        batch.drop_index("ix_errorlogs_fingerprint")
        batch.drop_column("fingerprint")
    op.drop_table("collector_cursors")
    op.drop_table("error_groups")
