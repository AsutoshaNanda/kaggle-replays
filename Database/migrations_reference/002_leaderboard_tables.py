"""Leaderboard feature — snapshots, entries, top-performer episodes.

Revision ID: 002_leaderboard
Revises: 001_initial
Create Date: 2026-06-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "002_leaderboard"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UINT = mysql.INTEGER(unsigned=True)


def upgrade() -> None:
    op.create_table(
        "leaderboard_snapshots",
        sa.Column("id", UINT, autoincrement=True, nullable=False),
        sa.Column("competition_id", UINT, nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("total_teams", UINT, nullable=True),
        sa.Column("top10_cutoff_rank", UINT, nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("competition_id", "snapshot_date", name="uk_competition_date"),
    )
    op.create_index("idx_lb_competition", "leaderboard_snapshots", ["competition_id"])

    op.create_table(
        "leaderboard_entries",
        sa.Column("id", UINT, autoincrement=True, nullable=False),
        sa.Column("snapshot_id", UINT, nullable=False),
        sa.Column("team_id", sa.String(100), nullable=False),
        sa.Column("team_name", sa.String(300), nullable=True),
        sa.Column("rank", UINT, nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("is_top_10_percent", sa.Boolean(), nullable=False),
        sa.Column("best_submission_id", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(["snapshot_id"], ["leaderboard_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_lb_snapshot", "leaderboard_entries", ["snapshot_id"])
    op.create_index("idx_lb_top10", "leaderboard_entries", ["is_top_10_percent"])

    op.create_table(
        "top_performer_episodes",
        sa.Column("id", UINT, autoincrement=True, nullable=False),
        sa.Column("entry_id", UINT, nullable=False),
        sa.Column("episode_id", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["leaderboard_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_id", "episode_id", name="uk_entry_episode"),
    )
    op.create_index("idx_tpe_entry", "top_performer_episodes", ["entry_id"])


def downgrade() -> None:
    op.drop_table("top_performer_episodes")
    op.drop_table("leaderboard_entries")
    op.drop_table("leaderboard_snapshots")
