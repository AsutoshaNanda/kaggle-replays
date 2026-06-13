"""Pydantic v2 request/response schemas.

Request models forbid unknown fields (``extra="forbid"``), enforce string
lengths and patterns, and constrain IDs to positive integers. Enum-typed fields
prevent free-text for ``filter_mode`` / ``format_mode``. Response models are
plain DTOs returned by routers.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FilterMode = Literal["all", "win", "lose", "draw"]
FormatMode = Literal["json", "zip", "both"]
JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]
JobType = Literal["episodes", "collection"]
CollectionItemFilter = Literal["all", "notebooks", "discussions", "datasets", "competitions"]
Medal = Literal["gold", "silver", "bronze"]


class _StrictModel(BaseModel):
    """Base for request bodies: reject unknown fields."""

    model_config = ConfigDict(extra="forbid")


class _ORMModel(BaseModel):
    """Base for response DTOs: allow construction from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


# --- Auth ------------------------------------------------------------------
class KaggleLoginResponse(BaseModel):
    """Response of ``POST /auth/kaggle-login``."""

    redirect_url: str


class TokenResponse(BaseModel):
    """Access-token response (refresh token travels in an httponly cookie)."""

    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    """Generic ``{"message": ...}`` response."""

    message: str


class UserResponse(_ORMModel):
    """Public user info for ``GET /auth/me``."""

    id: int
    kaggle_user: str
    display_name: str | None = None
    thumbnail_url: str | None = None
    profile_url: str | None = None
    tier: str | None = None


class ProfileUpdate(_StrictModel):
    """Body of ``PATCH /auth/me`` — only the local display name is editable."""

    display_name: str = Field(min_length=1, max_length=200)


# --- Competitions / submissions / episodes ---------------------------------
class CompetitionItem(_ORMModel):
    """A single competition in a list response."""

    id: int
    kaggle_id: int
    title: str
    slug: str
    team_id: str | None = None
    is_simulation: bool = False
    deadline: dt.datetime | None = None
    category: str | None = None
    status: Literal["active", "completed"] = "active"

    @classmethod
    def model_validate(cls, obj, **kwargs):  # type: ignore[override]
        item = super().model_validate(obj, **kwargs)
        dl = getattr(obj, "deadline", None)
        if dl is not None:
            now = dt.datetime.now(dt.timezone.utc)
            dl_aware = dl if dl.tzinfo else dl.replace(tzinfo=dt.timezone.utc)
            object.__setattr__(item, "status", "completed" if dl_aware < now else "active")
        return item


class CompetitionListResponse(BaseModel):
    """Response of ``GET /competitions``."""

    competitions: list[CompetitionItem]


class SubmissionItem(_ORMModel):
    """A single submission in a list response."""

    id: int
    title: str
    score: float | None = None
    episode_count: int | None = None  # None = unknown (e.g. rate-limited); 0 = confirmed empty
    fetched_at: dt.datetime | None = None
    episodes_synced_at: dt.datetime | None = None  # when episode IDs were last cached


class SubmissionListResponse(BaseModel):
    """Response of ``GET /competitions/{id}/submissions``."""

    submissions: list[SubmissionItem]
    # Most recent submission-metadata sync time (for a "last synced X ago" label).
    last_synced_at: dt.datetime | None = None


class EpisodeItem(BaseModel):
    """A single episode with its computed outcome."""

    id: str
    outcome: Literal["win", "lose", "draw", "unknown"] = "unknown"


class EpisodeListResponse(BaseModel):
    """Response of ``GET /submissions/{id}/episodes``."""

    episodes: list[EpisodeItem]
    total: int
    filter_applied: FilterMode
    note: str | None = None


# --- Collections ------------------------------------------------------------
class CollectionListItem(_ORMModel):
    """A single collection in ``GET /collections``."""

    id: int
    kaggle_id: int
    name: str
    item_count: int = 0
    items_synced_at: dt.datetime | None = None


class CollectionListResponse(BaseModel):
    """Response of ``GET /collections``."""

    collections: list[CollectionListItem]
    last_synced_at: dt.datetime | None = None


class CollectionItemSchema(_ORMModel):
    """A single document inside a collection (kernel/topic/competition/...)."""

    id: int
    kaggle_doc_id: str
    document_type: str  # "KERNEL" | "TOPIC" | "COMPETITION" | "DATASET" | ...
    title: str
    votes: int = 0
    total_comments: int = 0
    author_username: str | None = None
    author_tier: str | None = None
    medal: str | None = None  # "gold" | "silver" | "bronze" | None
    url: str | None = None
    create_time: dt.datetime | None = None
    update_time: dt.datetime | None = None


class CollectionItemsResponse(BaseModel):
    """Response of ``GET /collections/{id}/items`` (pre-sorted medal→votes)."""

    items: list[CollectionItemSchema]
    total: int
    last_synced_at: dt.datetime | None = None


class CollectionDrillItem(BaseModel):
    """One notebook or discussion enumerated under a COMPETITION/DATASET item."""

    title: str
    url: str | None = None
    votes: int | None = None
    medal: str | None = None  # "gold" | "silver" | "bronze" | None
    author_username: str | None = None


class CollectionItemContentsResponse(BaseModel):
    """Response of ``GET /collections/{id}/items/{item_id}/contents`` (drill-down)."""

    notebooks: list[CollectionDrillItem]
    discussions: list[CollectionDrillItem]


class CollectionDownloadRequest(_StrictModel):
    """Body of ``POST /collections/{id}/download`` — requires confirmation."""

    item_filter: CollectionItemFilter = "all"
    format_mode: FormatMode = "zip"
    # Top-N notebooks AND top-N discussions per COMPETITION/DATASET item (0 = no cap).
    per_competition_cap: int = Field(default=50, ge=0, le=1000)
    # Restrict downloaded notebooks to these medals; empty = all notebooks.
    medals: list[Medal] = Field(default_factory=list)
    confirm: bool = False


class CollectionDownloadResponse(BaseModel):
    """Response of ``POST /collections/{id}/download``."""

    job_id: str
    total_items: int
    status: JobStatus


# --- Downloads -------------------------------------------------------------
class DownloadStartRequest(_StrictModel):
    """Body of ``POST /downloads/start``."""

    submission_id: int = Field(gt=0)
    filter_mode: FilterMode = "all"
    format_mode: FormatMode = "json"


class DownloadStartResponse(BaseModel):
    """Response of ``POST /downloads/start``."""

    job_id: str
    status: JobStatus


class ReplayDownloadRequest(_StrictModel):
    """Body of ``POST /downloads/replays`` — download specific episodes by ID.

    Used by the Top 10% Replays page to grab a performer's replays directly; no
    owned submission is involved. IDs are bounded to keep one job sane.
    """

    episode_ids: list[str] = Field(min_length=1, max_length=200)
    format_mode: FormatMode = "zip"


class BulkDownloadRequest(_StrictModel):
    """Body of ``POST /downloads/bulk`` — requires explicit confirmation."""

    competition_id: int = Field(gt=0)
    filter_mode: FilterMode = "all"
    format_mode: FormatMode = "json"
    confirm: bool = False


class BulkDownloadResponse(BaseModel):
    """Response of ``POST /downloads/bulk``."""

    job_id: str
    total_submissions: int
    total_episodes_estimated: int


class JobStatusResponse(_ORMModel):
    """Response of ``GET /downloads/{uuid}/status``."""

    job_id: str
    status: JobStatus
    total: int
    completed: int
    failed_count: int
    skipped: int
    pct_complete: float
    elapsed_seconds: float
    estimated_remaining_seconds: float | None = None


class JobHistoryItem(_ORMModel):
    """A single job row in the history list."""

    job_id: str
    status: JobStatus
    job_type: JobType = "episodes"
    filter_mode: FilterMode
    format_mode: FormatMode
    is_bulk: bool
    total: int
    completed: int
    failed_count: int
    skipped: int
    submission_title: str | None = None
    submission_score: float | None = None
    collection_name: str | None = None
    created_at: dt.datetime | None = None
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None


class JobHistoryResponse(BaseModel):
    """Response of ``GET /downloads``."""

    jobs: list[JobHistoryItem]


# --- Leaderboard (feature add-on; schemas live here per its spec) -----------
class TopPerformer(BaseModel):
    """A top-10% team within a daily leaderboard snapshot."""

    team_id: str
    team_name: str | None = None
    rank: int
    score: float | None = None
    best_submission_id: str | None = None
    episode_ids: list[str] = Field(default_factory=list)


class LeaderboardRow(BaseModel):
    """A single row of the current public leaderboard."""

    team_id: str
    team_name: str | None = None
    rank: int
    score: float | None = None
    medal: str | None = None
    best_submission_id: str | None = None


class LeaderboardCurrentResponse(BaseModel):
    """Response of ``GET /leaderboard/{id}/current``."""

    total_teams: int
    top10_cutoff_rank: int
    entries: list[LeaderboardRow]
    last_synced_at: dt.datetime | None = None


class LeaderboardDay(BaseModel):
    """One day's leaderboard snapshot summary."""

    date: dt.date
    total_teams: int
    top10_cutoff_rank: int
    top_performers: list[TopPerformer] = Field(default_factory=list)


class LeaderboardHistoryResponse(BaseModel):
    """Response of ``GET /leaderboard/{id}/history``."""

    days: list[LeaderboardDay]
    last_synced_at: dt.datetime | None = None


class LeaderboardReplaysResponse(BaseModel):
    """Response of ``GET /leaderboard/{id}/date/{date}/replays``."""

    date: dt.date
    total_teams: int
    top10_cutoff_rank: int
    top_performers: list[TopPerformer]


class LeaderboardSyncRequest(_StrictModel):
    """Body of ``POST /leaderboard/{id}/sync``."""

    backfill: bool = False
    from_date: dt.date | None = None
    to_date: dt.date | None = None


class LeaderboardSyncResponse(BaseModel):
    """Response of ``POST /leaderboard/{id}/sync``."""

    status: str
    mode: Literal["sync", "backfill"]
    message: str
