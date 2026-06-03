"""Profile fields on users + status/deadline fields on competitions.

Revision ID: 003_profile_comp
Revises: 002_leaderboard
Create Date: 2026-06-02

All columns are additive and nullable — safe, no data migration required.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_profile_comp"
down_revision: Union[str, None] = "002_leaderboard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users: Kaggle-imported profile details
    op.add_column("users", sa.Column("thumbnail_url", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("profile_url", sa.String(300), nullable=True))
    op.add_column("users", sa.Column("tier", sa.String(50), nullable=True))

    # competitions: real status fields so tab filtering / badges are accurate
    op.add_column("competitions", sa.Column("deadline", sa.DateTime(), nullable=True))
    op.add_column("competitions", sa.Column("category", sa.String(50), nullable=True))
    op.add_column("competitions", sa.Column("enabled_date", sa.DateTime(), nullable=True))
    op.add_column(
        "competitions",
        sa.Column("is_simulation", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("competitions", "is_simulation")
    op.drop_column("competitions", "enabled_date")
    op.drop_column("competitions", "category")
    op.drop_column("competitions", "deadline")
    op.drop_column("users", "tier")
    op.drop_column("users", "profile_url")
    op.drop_column("users", "thumbnail_url")
