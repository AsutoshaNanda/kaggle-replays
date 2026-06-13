"""SQLAlchemy ORM models — the full MySQL schema.

One class per table, declared in FK-dependency order. Column types mirror the
project's SQL spec (``INT UNSIGNED`` PKs, ``CHAR(36)`` UUIDs, native ``ENUM``s,
``JSON`` detail columns). All access elsewhere is through the ORM — no raw SQL.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import INTEGER as MySQLInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# Reusable MySQL ``INT UNSIGNED`` / ``BIGINT UNSIGNED`` column types.
UINT = MySQLInteger(unsigned=True)
UBIGINT = BigInteger().with_variant(
    __import__("sqlalchemy.dialects.mysql", fromlist=["BIGINT"]).BIGINT(unsigned=True),
    "mysql",
)


class User(Base):
    """One row per Kaggle account that has logged in."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(UINT, primary_key=True, autoincrement=True)
    kaggle_user: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    profile_url: Mapped[str | None] = mapped_column(String(300))
    tier: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    last_login: Mapped[dt.datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    playwright_session: Mapped["PlaywrightSession | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    competitions: Mapped[list["Competition"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    download_jobs: Mapped[list["DownloadJob"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    collections: Mapped[list["Collection"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    """JWT refresh-token tracking — one row per active/expired login session."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(UINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(UINT, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    refresh_token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="sessions")


class PlaywrightSession(Base):
    """Per-user Kaggle browser session file location (the ``auth.json`` path)."""

    __tablename__ = "playwright_sessions"

    id: Mapped[int] = mapped_column(UINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        UINT, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    session_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    last_used: Mapped[dt.datetime | None] = mapped_column(DateTime)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship(back_populates="playwright_session")


class Competition(Base):
    """Cached competition metadata, scoped per user."""

    __tablename__ = "competitions"
    __table_args__ = (UniqueConstraint("kaggle_id", "user_id", name="uk_kaggle_user"),)

    id: Mapped[int] = mapped_column(UINT, primary_key=True, autoincrement=True)
    kaggle_id: Mapped[int] = mapped_column(UINT, nullable=False)
    user_id: Mapped[int] = mapped_column(UINT, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), nullable=False)
    team_id: Mapped[str | None] = mapped_column(String(100))
    deadline: Mapped[dt.datetime | None] = mapped_column(DateTime)
    category: Mapped[str | None] = mapped_column(String(50))
    enabled_date: Mapped[dt.datetime | None] = mapped_column(DateTime)
    is_simulation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="competitions")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="competition", cascade="all, delete-orphan")


class Submission(Base):
    """Cached submission metadata, scoped per user + competition."""

    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("kaggle_id", "user_id", name="uk_kaggle_user"),)

    id: Mapped[int] = mapped_column(UINT, primary_key=True, autoincrement=True)
    kaggle_id: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[int] = mapped_column(UINT, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    competition_id: Mapped[int] = mapped_column(
        UINT, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    # Nullable: None = count unknown (e.g. Kaggle rate-limited); a real int
    # (including 0) once confirmed. Column is already nullable in migration 001.
    episode_count: Mapped[int | None] = mapped_column(UINT, nullable=True, default=None)
    # Cached episode list [{"id","outcome"}, ...] + last-sync time, so the UI
    # serves episode IDs from the DB rather than hitting Kaggle on every view
    # (rate-limit-safe). Populated by the daily scheduler / manual "Sync now".
    episodes_json: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    episodes_synced_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="submissions")
    competition: Mapped["Competition"] = relationship(back_populates="submissions")
    download_jobs: Mapped[list["DownloadJob"]] = relationship(back_populates="submission", cascade="all, delete-orphan")


class Collection(Base):
    """Cached Kaggle collection metadata, scoped per user."""

    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("kaggle_id", "user_id", name="uk_kaggle_user_collection"),)

    id: Mapped[int] = mapped_column(UINT, primary_key=True, autoincrement=True)
    kaggle_id: Mapped[int] = mapped_column(UBIGINT, nullable=False)
    user_id: Mapped[int] = mapped_column(UINT, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    item_count: Mapped[int] = mapped_column(UINT, nullable=False, default=0)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    items_synced_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="collections")
    items: Mapped[list["CollectionItem"]] = relationship(back_populates="collection", cascade="all, delete-orphan")


class CollectionItem(Base):
    """One cached document inside a collection (kernel/topic/competition/...)."""

    __tablename__ = "collection_items"
    __table_args__ = (UniqueConstraint("collection_id", "kaggle_doc_id", name="uk_collection_doc"),)

    id: Mapped[int] = mapped_column(UINT, primary_key=True, autoincrement=True)
    collection_id: Mapped[int] = mapped_column(
        UINT, ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kaggle_doc_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # Plain VARCHAR (not a native ENUM): Kaggle may add document types and an
    # unknown value must not break the sync upsert.
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_comments: Mapped[int] = mapped_column(UINT, nullable=False, default=0)
    author_username: Mapped[str | None] = mapped_column(String(100))
    author_tier: Mapped[str | None] = mapped_column(String(50))
    medal: Mapped[str | None] = mapped_column(String(20))
    url: Mapped[str | None] = mapped_column(String(600))
    create_time: Mapped[dt.datetime | None] = mapped_column(DateTime)
    update_time: Mapped[dt.datetime | None] = mapped_column(DateTime)
    raw_json: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    collection: Mapped["Collection"] = relationship(back_populates="items")


class DownloadJob(Base):
    """One row per initiated download (episode replays or a collection export)."""

    __tablename__ = "download_jobs"

    id: Mapped[int] = mapped_column(UINT, primary_key=True, autoincrement=True)
    job_uuid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(UINT, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Nullable since migration 005: collection jobs have no submission.
    submission_id: Mapped[int | None] = mapped_column(
        UINT, ForeignKey("submissions.id", ondelete="CASCADE"), nullable=True
    )
    job_type: Mapped[str] = mapped_column(
        Enum("episodes", "collection", name="job_type_enum"), nullable=False, default="episodes"
    )
    collection_id: Mapped[int | None] = mapped_column(
        UINT, ForeignKey("collections.id", ondelete="CASCADE"), nullable=True
    )
    # Collection jobs only: which item types to download (episode jobs leave NULL).
    item_filter: Mapped[str | None] = mapped_column(
        Enum("all", "notebooks", "discussions", "datasets", "competitions", name="item_filter_enum"),
        nullable=True,
    )
    # Collection jobs only: top-N notebooks/discussions per COMPETITION item
    # (NULL = server default, 0 = no cap).
    per_competition_cap: Mapped[int | None] = mapped_column(UINT, nullable=True)
    # Collection jobs only: comma-joined medals ("gold,silver") to restrict
    # downloaded notebooks; NULL = no medal filter (all notebooks).
    medal_filter: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Replay-by-id jobs only: explicit episode IDs to download (no owned
    # submission). NULL for submission-based and collection jobs.
    episode_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    filter_mode: Mapped[str] = mapped_column(
        Enum("all", "win", "lose", "draw", name="filter_mode_enum"), nullable=False, default="all"
    )
    format_mode: Mapped[str] = mapped_column(
        Enum("json", "zip", "both", name="format_mode_enum"), nullable=False, default="json"
    )
    is_bulk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        Enum("queued", "running", "done", "failed", "cancelled", name="job_status_enum"),
        nullable=False,
        default="queued",
    )
    total: Mapped[int] = mapped_column(UINT, default=0)
    completed: Mapped[int] = mapped_column(UINT, default=0)
    failed_count: Mapped[int] = mapped_column(UINT, default=0)
    skipped: Mapped[int] = mapped_column(UINT, default=0)
    output_path: Mapped[str | None] = mapped_column(String(1000))
    error_msg: Mapped[str | None] = mapped_column(Text)
    latest_episode_id: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="download_jobs")
    submission: Mapped["Submission | None"] = relationship(back_populates="download_jobs")
    collection: Mapped["Collection | None"] = relationship()


class AuditLog(Base):
    """Immutable security/event log (INSERT only)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(UBIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(UINT, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        Enum("success", "failure", "blocked", name="audit_status_enum"), nullable=False, default="success"
    )
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)


class RateLimitLog(Base):
    """Per-identifier sliding-window counters for rate limiting."""

    __tablename__ = "rate_limit_log"

    id: Mapped[int] = mapped_column(UBIGINT, primary_key=True, autoincrement=True)
    identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    window_start: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, index=True)
    request_count: Mapped[int] = mapped_column(UINT, nullable=False, default=1)


# ---------------------------------------------------------------------------
# Leaderboard feature tables (migration 002)
# ---------------------------------------------------------------------------
class LeaderboardSnapshot(Base):
    """One leaderboard capture per competition per day."""

    __tablename__ = "leaderboard_snapshots"
    __table_args__ = (
        UniqueConstraint("competition_id", "snapshot_date", name="uk_competition_date"),
    )

    id: Mapped[int] = mapped_column(UINT, primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(
        UINT, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    total_teams: Mapped[int] = mapped_column(UINT, default=0)
    top10_cutoff_rank: Mapped[int] = mapped_column(UINT, default=0)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    entries: Mapped[list["LeaderboardEntry"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class LeaderboardEntry(Base):
    """One team's standing within a leaderboard snapshot."""

    __tablename__ = "leaderboard_entries"

    id: Mapped[int] = mapped_column(UINT, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        UINT, ForeignKey("leaderboard_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[str] = mapped_column(String(100), nullable=False)
    team_name: Mapped[str | None] = mapped_column(String(300))
    rank: Mapped[int] = mapped_column(UINT, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    is_top_10_percent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    best_submission_id: Mapped[str | None] = mapped_column(String(100))

    snapshot: Mapped["LeaderboardSnapshot"] = relationship(back_populates="entries")
    episodes: Mapped[list["TopPerformerEpisode"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )


class TopPerformerEpisode(Base):
    """An episode ID linked to a top-10% leaderboard entry."""

    __tablename__ = "top_performer_episodes"
    __table_args__ = (UniqueConstraint("entry_id", "episode_id", name="uk_entry_episode"),)

    id: Mapped[int] = mapped_column(UINT, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
        UINT, ForeignKey("leaderboard_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    episode_id: Mapped[str] = mapped_column(String(100), nullable=False)

    entry: Mapped["LeaderboardEntry"] = relationship(back_populates="episodes")
