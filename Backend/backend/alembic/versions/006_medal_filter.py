"""Collection downloads — per-job medal filter for notebooks.

Revision ID: 006_medal_filter
Revises: 005_collections
Create Date: 2026-06-13

Adds ``download_jobs.medal_filter``: a comma-joined subset of
``gold,silver,bronze`` recorded on a collection job so the worker downloads only
notebooks of those medals (NULL = no filter / all). Stored as a small VARCHAR
rather than an ENUM since it holds a *combination* of medals.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_medal_filter"
down_revision: Union[str, None] = "005_collections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("download_jobs", sa.Column("medal_filter", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("download_jobs", "medal_filter")
