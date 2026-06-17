"""Single-item collection download jobs + kernel output/log.

Additive: ``download_jobs.collection_item_id`` (UINT, nullable) lets one job
target a single ``collection_items`` row instead of the whole collection. Plain
int (no FK) so job history survives a re-sync that prunes stale items. NULL for
whole-collection jobs and every non-collection job.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import INTEGER as MySQLInteger

revision: str = "008_single_item_download"
down_revision: Union[str, None] = "007_replay_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UINT = MySQLInteger(unsigned=True)


def upgrade() -> None:
    op.add_column("download_jobs", sa.Column("collection_item_id", _UINT, nullable=True))


def downgrade() -> None:
    op.drop_column("download_jobs", "collection_item_id")
