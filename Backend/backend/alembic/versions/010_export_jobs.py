"""Add resumable top-100 export jobs."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import INTEGER as MySQLInteger

revision: str = "010_export_jobs"
down_revision: Union[str, None] = "009_top100_archives"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UINT = MySQLInteger(unsigned=True)


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("id", _UINT, autoincrement=True, nullable=False),
        sa.Column("job_uuid", sa.String(36), nullable=False),
        sa.Column("user_id", _UINT, nullable=False),
        sa.Column("competition_id", _UINT, nullable=False),
        sa.Column("snapshot_id", _UINT, nullable=True),
        sa.Column("target", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), server_default="queued", nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("total_players", _UINT, server_default="100", nullable=False),
        sa.Column("resolved_players", _UINT, server_default="0", nullable=False),
        sa.Column("completed_players", _UINT, server_default="0", nullable=False),
        sa.Column("total_episodes", _UINT, server_default="0", nullable=False),
        sa.Column("completed_episodes", _UINT, server_default="0", nullable=False),
        sa.Column("current_rank", _UINT, nullable=True),
        sa.Column("download_job_ids", sa.JSON(), nullable=True),
        sa.Column("dataset_ref", sa.String(200), nullable=True),
        sa.Column("result_url", sa.String(600), nullable=True),
        sa.Column("destination", sa.String(600), nullable=True),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["leaderboard_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_uuid"),
    )
    op.create_index("ix_export_jobs_job_uuid", "export_jobs", ["job_uuid"], unique=True)
    op.create_index("ix_export_jobs_user_id", "export_jobs", ["user_id"])
    op.create_index("ix_export_jobs_competition_id", "export_jobs", ["competition_id"])
    op.create_index("ix_export_jobs_status", "export_jobs", ["status"])
    op.add_column("download_jobs", sa.Column("export_job_id", _UINT, nullable=True))
    op.create_index("ix_download_jobs_export_job_id", "download_jobs", ["export_job_id"])
    op.create_foreign_key(
        "fk_download_jobs_export_job",
        "download_jobs",
        "export_jobs",
        ["export_job_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_download_jobs_export_job", "download_jobs", type_="foreignkey")
    op.drop_index("ix_download_jobs_export_job_id", table_name="download_jobs")
    op.drop_column("download_jobs", "export_job_id")
    op.drop_table("export_jobs")
