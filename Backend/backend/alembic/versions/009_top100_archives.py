"""Track leaderboard replay resolution and player ZIP names."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_top100_archives"
down_revision: Union[str, None] = "008_single_item_download"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leaderboard_entries", sa.Column("episodes_resolved_at", sa.DateTime(), nullable=True))
    op.add_column("download_jobs", sa.Column("archive_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("download_jobs", "archive_name")
    op.drop_column("leaderboard_entries", "episodes_resolved_at")
