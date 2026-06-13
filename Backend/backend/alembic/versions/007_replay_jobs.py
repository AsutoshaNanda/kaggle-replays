"""Replay-by-id download jobs + datasets/competitions item filters.

Revision ID: 007_replay_jobs
Revises: 006_medal_filter
Create Date: 2026-06-13

Two additive changes:

* ``download_jobs.episode_ids`` (JSON, nullable) — lets a job download a specific
  set of replay episode IDs (e.g. a top performer's replays on the Top 10%
  Replays page) directly, with no owned submission. NULL for normal jobs.
* Widen ``item_filter_enum`` to include ``datasets`` and ``competitions`` so a
  collection download can target those item types (the worker already drills
  into them).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_replay_jobs"
down_revision: Union[str, None] = "006_medal_filter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_FILTERS = ("all", "notebooks", "discussions")
_NEW_FILTERS = ("all", "notebooks", "discussions", "datasets", "competitions")


def upgrade() -> None:
    op.add_column("download_jobs", sa.Column("episode_ids", sa.JSON(), nullable=True))
    op.alter_column(
        "download_jobs",
        "item_filter",
        existing_type=sa.Enum(*_OLD_FILTERS, name="item_filter_enum"),
        type_=sa.Enum(*_NEW_FILTERS, name="item_filter_enum"),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "download_jobs",
        "item_filter",
        existing_type=sa.Enum(*_NEW_FILTERS, name="item_filter_enum"),
        type_=sa.Enum(*_OLD_FILTERS, name="item_filter_enum"),
        existing_nullable=True,
    )
    op.drop_column("download_jobs", "episode_ids")
