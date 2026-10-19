"""fcm_tokens.token_idx: bind FCM rows to the login token that registered them

Revision ID: c3d4e5f6a7b8
Revises: b7c1d2e3f4a5
Create Date: 2026-10-19 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b7c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_fcm_tokens_token_idx_tokens"
IX_NAME = "ix_fcm_tokens_token_idx"


def upgrade() -> None:
    # 기존 행은 token_idx NULL(레거시): last_delivery 30일 이내면 계속 전송, 이후 정리된다.
    # 앱이 다시 등록하면 로그인 토큰에 묶인다.
    with op.batch_alter_table("fcm_tokens") as batch:
        batch.add_column(
            sa.Column(
                "token_idx",
                sa.Integer(),
                nullable=True,
                comment="등록한 로그인 토큰 고유번호",
            )
        )
        batch.create_foreign_key(
            FK_NAME, "tokens", ["token_idx"], ["idx"], ondelete="CASCADE"
        )
        batch.create_index(IX_NAME, ["token_idx"])


def downgrade() -> None:
    with op.batch_alter_table("fcm_tokens") as batch:
        batch.drop_index(IX_NAME)
        batch.drop_constraint(FK_NAME, type_="foreignkey")
        batch.drop_column("token_idx")
