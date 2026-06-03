"""Initial schema — users, sessions, competitions, submissions, jobs, logs.

Revision ID: 001_initial
Revises:
Create Date: 2026-06-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UINT = mysql.INTEGER(unsigned=True)
UBIGINT = mysql.BIGINT(unsigned=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UINT, autoincrement=True, nullable=False),
        sa.Column("kaggle_user", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kaggle_user"),
    )
    op.create_index("idx_kaggle_user", "users", ["kaggle_user"])

    op.create_table(
        "user_sessions",
        sa.Column("id", UINT, autoincrement=True, nullable=False),
        sa.Column("user_id", UINT, nullable=False),
        sa.Column("refresh_token", sa.String(512), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_token"),
    )
    op.create_index("idx_refresh", "user_sessions", ["refresh_token"])
    op.create_index("idx_user_active", "user_sessions", ["user_id", "revoked"])

    op.create_table(
        "playwright_sessions",
        sa.Column("id", UINT, autoincrement=True, nullable=False),
        sa.Column("user_id", UINT, nullable=False),
        sa.Column("session_path", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used", sa.DateTime(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "competitions",
        sa.Column("id", UINT, autoincrement=True, nullable=False),
        sa.Column("kaggle_id", UINT, nullable=False),
        sa.Column("user_id", UINT, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("slug", sa.String(300), nullable=False),
        sa.Column("team_id", sa.String(100), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kaggle_id", "user_id", name="uk_kaggle_user"),
    )
    op.create_index("idx_user", "competitions", ["user_id"])

    op.create_table(
        "submissions",
        sa.Column("id", UINT, autoincrement=True, nullable=False),
        sa.Column("kaggle_id", sa.String(100), nullable=False),
        sa.Column("user_id", UINT, nullable=False),
        sa.Column("competition_id", UINT, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("episode_count", UINT, nullable=True),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kaggle_id", "user_id", name="uk_kaggle_user"),
    )
    op.create_index("idx_competition", "submissions", ["competition_id"])

    op.create_table(
        "download_jobs",
        sa.Column("id", UINT, autoincrement=True, nullable=False),
        sa.Column("job_uuid", sa.String(36), nullable=False),
        sa.Column("user_id", UINT, nullable=False),
        sa.Column("submission_id", UINT, nullable=False),
        sa.Column("filter_mode", sa.Enum("all", "win", "lose", "draw", name="filter_mode_enum"), nullable=False),
        sa.Column("format_mode", sa.Enum("json", "zip", "both", name="format_mode_enum"), nullable=False),
        sa.Column("is_bulk", sa.Boolean(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "done", "failed", "cancelled", name="job_status_enum"),
            nullable=False,
        ),
        sa.Column("total", UINT, nullable=True),
        sa.Column("completed", UINT, nullable=True),
        sa.Column("failed_count", UINT, nullable=True),
        sa.Column("skipped", UINT, nullable=True),
        sa.Column("output_path", sa.String(1000), nullable=True),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("latest_episode_id", sa.String(100), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_uuid"),
    )
    op.create_index("idx_user_status", "download_jobs", ["user_id", "status"])
    op.create_index("idx_uuid", "download_jobs", ["job_uuid"])

    op.create_table(
        "audit_log",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("user_id", UINT, nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("status", sa.Enum("success", "failure", "blocked", name="audit_status_enum"), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_user", "audit_log", ["user_id"])
    op.create_index("idx_action", "audit_log", ["action"])
    op.create_index("idx_created", "audit_log", ["created_at"])

    op.create_table(
        "rate_limit_log",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("identifier", sa.String(200), nullable=False),
        sa.Column("endpoint", sa.String(200), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("request_count", UINT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_identifier_window", "rate_limit_log", ["identifier", "window_start"])
    op.create_index(op.f("ix_rate_limit_log_window_start"), "rate_limit_log", ["window_start"])


def downgrade() -> None:
    op.drop_table("rate_limit_log")
    op.drop_table("audit_log")
    op.drop_table("download_jobs")
    op.drop_table("submissions")
    op.drop_table("competitions")
    op.drop_table("playwright_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")
