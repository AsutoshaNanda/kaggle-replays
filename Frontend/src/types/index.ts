// All shared TypeScript interfaces. No inline interfaces in components.

export interface User {
  id: number
  kaggle_user: string
  display_name: string | null
  thumbnail_url: string | null
  profile_url: string | null
  tier: string | null
}

export interface Competition {
  id: number
  title: string
  slug: string
  team_id: string
  is_simulation: boolean
  kaggle_id: number
  deadline: string | null
  category: string | null
  status: 'active' | 'completed'
}

export interface Submission {
  id: number
  title: string
  score: number | null
  fetched_at: string
  // null = episode count unknown (e.g. Kaggle rate-limited); 0 = confirmed empty.
  episode_count: number | null
  // When this submission's episode list was last cached (null = never synced).
  episodes_synced_at: string | null
}

export interface Episode {
  id: string
  outcome: 'win' | 'lose' | 'draw' | 'unknown'
}

export interface DownloadJob {
  job_id: string
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  total: number
  completed: number
  failed_count: number
  skipped: number
  pct_complete: number
  elapsed_seconds: number
  estimated_remaining_seconds: number | null
}

// A row from GET /downloads (history list).
export interface DownloadHistoryEntry {
  job_id: string
  status: DownloadJob['status']
  filter_mode: EpisodeFilter
  format_mode: FormatMode
  is_bulk: boolean
  total: number
  completed: number
  failed_count: number
  skipped: number
  submission_title: string | null
  submission_score: number | null
  created_at: string | null
  started_at: string | null
  completed_at: string | null
}

export type TabFilter = 'entered' | 'completed' | 'all'
export type EpisodeFilter = 'all' | 'win' | 'lose' | 'draw'
export type FormatMode = 'json' | 'zip' | 'both'

// --- API response envelopes ---
export interface CompetitionListResponse {
  competitions: Competition[]
}
export interface SubmissionListResponse {
  submissions: Submission[]
  last_synced_at?: string | null
}
export interface EpisodeListResponse {
  episodes: Episode[]
  total: number
  filter_applied: EpisodeFilter
  note?: string | null
}
export interface StartDownloadResponse {
  job_id: string
  status: DownloadJob['status']
}
export interface BulkDownloadResponse {
  job_id: string
  total_submissions: number
  total_episodes_estimated: number
}
export interface DownloadHistoryResponse {
  jobs: DownloadHistoryEntry[]
}
export interface TokenResponse {
  access_token: string
  token_type?: string
}
export interface KaggleLoginResponse {
  redirect_url: string
}

// --- WebSocket progress frame ---
export interface WsProgressFrame {
  status: DownloadJob['status']
  completed: number
  total: number
  pct_complete: number
  latest_episode_id: string | null
  failed_count: number
}

// --- Toast notifications ---
export type ToastType = 'success' | 'error' | 'warning' | 'info'
export interface Toast {
  id: number
  type: ToastType
  message: string
}

// --- Leaderboard ---
export interface LeaderboardRow {
  team_id: string
  team_name: string | null
  rank: number
  score: number | null
  medal: string | null
  best_submission_id: string | null
}
export interface LeaderboardCurrentResponse {
  total_teams: number
  top10_cutoff_rank: number
  entries: LeaderboardRow[]
  last_synced_at?: string | null
}
export interface TopPerformer {
  team_id: string
  team_name: string | null
  rank: number
  score: number | null
  best_submission_id: string | null
  episode_ids: string[]
}
export interface LeaderboardDay {
  date: string
  total_teams: number
  top10_cutoff_rank: number
  top_performers: TopPerformer[]
}
export interface LeaderboardHistoryResponse {
  days: LeaderboardDay[]
  last_synced_at?: string | null
}
export interface LeaderboardSyncResponse {
  status: string
  mode: string
  message: string
}
