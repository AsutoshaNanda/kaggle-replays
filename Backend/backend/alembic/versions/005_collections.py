"""Collections downloader — collections/collection_items tables + job columns.

Revision ID: 005_collections
Revises: 004_episode_cache
Create Date: 2026-06-11

Adds the cached ``collections`` / ``collection_items`` tables and extends
``download_jobs`` so one jobs table serves both episode and collection
downloads: ``submission_id`` becomes nullable, and a ``job_type`` discriminator
plus collection-specific columns are added. The existing ``filter_mode`` ENUM
is untouched (collection jobs store its default and use ``item_filter``).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "005_collections"
down_revision: Union[str, None] = "004_episode_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UINT = mysql.INTEGER(unsigned=True)
UBIGINT = mysql.BIGINT(unsigned=True)


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", UINT, autoincrement=True, nullable=False),
        sa.Column("kaggle_id", UBIGINT, nullable=False),
        sa.Column("user_id", UINT, nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("item_count", UINT, server_default="0", nullable=False),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("items_synced_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kaggle_id", "user_id", name="uk_kaggle_user_collection"),
    )
    op.create_index("idx_collection_user", "collections", ["user_id"])

    op.create_table(
        "collection_items",
        sa.Column("id", UINT, autoincrement=True, nullable=False),
        sa.Column("collection_id", UINT, nullable=False),
        sa.Column("kaggle_doc_id", sa.String(100), nullable=False),
        # Plain VARCHAR, not a native ENUM: Kaggle may introduce new document
        # types (KERNEL/TOPIC/COMPETITION/DATASET/COMMENT/...) and an unknown
        # value must not break inserts.
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("votes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_comments", UINT, server_default="0", nullable=False),
        sa.Column("author_username", sa.String(100), nullable=True),
        sa.Column("author_tier", sa.String(50), nullable=True),
        sa.Column("medal", sa.String(20), nullable=True),
        sa.Column("url", sa.String(600), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=True),
        sa.Column("update_time", sa.DateTime(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "kaggle_doc_id", name="uk_collection_doc"),
    )
    op.create_index("idx_item_collection", "collection_items", ["collection_id"])

    op.alter_column("download_jobs", "submission_id", existing_type=UINT, nullable=True)
    op.add_column(
        "download_jobs",
        sa.Column(
            "job_type",
            sa.Enum("episodes", "collection", name="job_type_enum"),
            server_default="episodes",
            nullable=False,
        ),
    )
    op.add_column("download_jobs", sa.Column("collection_id", UINT, nullable=True))
    op.create_foreign_key(
        "fk_download_jobs_collection",
        "download_jobs",
        "collections",
        ["collection_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column(
        "download_jobs",
        sa.Column(
            "item_filter",
            sa.Enum("all", "notebooks", "discussions", name="item_filter_enum"),
            nullable=True,
        ),
    )
    op.add_column("download_jobs", sa.Column("per_competition_cap", UINT, nullable=True))


def downgrade() -> None:
    op.drop_column("download_jobs", "per_competition_cap")
    op.drop_column("download_jobs", "item_filter")
    op.drop_constraint("fk_download_jobs_collection", "download_jobs", type_="foreignkey")
    op.drop_column("download_jobs", "collection_id")
    op.drop_column("download_jobs", "job_type")
    op.alter_column("download_jobs", "submission_id", existing_type=UINT, nullable=False)
    op.drop_table("collection_items")
    op.drop_table("collections")
