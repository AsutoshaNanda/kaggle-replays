"""Cache episode lists on submissions (rate-limit-safe episode IDs).

Revision ID: 004_episode_cache
Revises: 003_profile_comp
Create Date: 2026-06-03

Additive + nullable only — no data migration required. Stores each submission's
episode list ([{"id","outcome"}, ...]) plus the time it was last synced, so the
UI serves episode IDs from the DB instead of calling Kaggle on every page view.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_episode_cache"
down_revision: Union[str, None] = "003_profile_comp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("episodes_json", sa.JSON(), nullable=True))
    op.add_column("submissions", sa.Column("episodes_synced_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("submissions", "episodes_synced_at")
    op.drop_column("submissions", "episodes_json")
