// Typed API call functions — one per backend endpoint.
// Components import from here; they never call axios/fetch directly.

import { apiClient, BASE_URL, getAccessToken } from './client'
import type {
  BulkDownloadResponse,
  CollectionDownloadResponse,
  CollectionItemContentsResponse,
  CollectionItemFilter,
  CollectionItemsResponse,
  CollectionListResponse,
  Medal,
  CompetitionListResponse,
  DownloadHistoryResponse,
  DownloadJob,
  EpisodeFilter,
  EpisodeListResponse,
  FormatMode,
  KaggleLoginResponse,
  LeaderboardCurrentResponse,
  LeaderboardHistoryResponse,
  LeaderboardSyncResponse,
  StartDownloadResponse,
  SubmissionListResponse,
  TabFilter,
  TokenResponse,
  User,
} from '@/types'

// --- Auth ---
export async function kaggleLogin(): Promise<KaggleLoginResponse> {
  const { data } = await apiClient.post<KaggleLoginResponse>('/auth/kaggle-login', {})
  return data
}

export async function refreshToken(): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/auth/refresh', {})
  return data
}

export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout', {})
}

export async function getMe(): Promise<User> {
  const { data } = await apiClient.get<User>('/auth/me')
  return data
}

export async function updateProfile(displayName: string): Promise<User> {
  const { data } = await apiClient.patch<User>('/auth/me', { display_name: displayName })
  return data
}

// --- Leaderboard ---
export async function getLeaderboardCurrent(
  competitionId: number,
): Promise<LeaderboardCurrentResponse> {
  const { data } = await apiClient.get<LeaderboardCurrentResponse>(
    `/leaderboard/${competitionId}/current`,
  )
  return data
}

export async function getLeaderboardHistory(
  competitionId: number,
  fromDate?: string,
  toDate?: string,
): Promise<LeaderboardHistoryResponse> {
  const { data } = await apiClient.get<LeaderboardHistoryResponse>(
    `/leaderboard/${competitionId}/history`,
    { params: { from_date: fromDate, to_date: toDate } },
  )
  return data
}

export async function syncLeaderboard(
  competitionId: number,
  backfill: boolean,
  fromDate?: string,
  toDate?: string,
): Promise<LeaderboardSyncResponse> {
  const { data } = await apiClient.post<LeaderboardSyncResponse>(
    `/leaderboard/${competitionId}/sync`,
    { backfill, from_date: fromDate ?? null, to_date: toDate ?? null },
  )
  return data
}

// --- Competitions ---
export async function getCompetitions(tab: TabFilter): Promise<CompetitionListResponse> {
  const { data } = await apiClient.get<CompetitionListResponse>('/competitions', {
    params: { tab },
  })
  return data
}

export async function getSubmissions(
  kaggleCompetitionId: number,
): Promise<SubmissionListResponse> {
  const { data } = await apiClient.get<SubmissionListResponse>(
    `/competitions/${kaggleCompetitionId}/submissions`,
  )
  return data
}

// Owner-only manual "Sync now": force a fresh pull for a competition (submissions
// immediately, then episodes/scores + leaderboard snapshot in the background).
export async function syncCompetitionData(
  kaggleCompetitionId: number,
): Promise<SubmissionListResponse> {
  const { data } = await apiClient.post<SubmissionListResponse>(
    `/competitions/${kaggleCompetitionId}/sync`,
    {},
  )
  return data
}

// --- Submissions / episodes ---
export async function getEpisodes(
  submissionId: number,
  filter: EpisodeFilter,
): Promise<EpisodeListResponse> {
  const { data } = await apiClient.get<EpisodeListResponse>(
    `/submissions/${submissionId}/episodes`,
    { params: { filter } },
  )
  return data
}

// --- Downloads ---
export async function startDownload(
  submissionId: number,
  filterMode: EpisodeFilter,
  formatMode: FormatMode,
): Promise<StartDownloadResponse> {
  const { data } = await apiClient.post<StartDownloadResponse>('/downloads/start', {
    submission_id: submissionId,
    filter_mode: filterMode,
    format_mode: formatMode,
  })
  return data
}

export async function startBulkDownload(
  competitionId: number,
  filterMode: EpisodeFilter,
  formatMode: FormatMode,
): Promise<BulkDownloadResponse> {
  const { data } = await apiClient.post<BulkDownloadResponse>('/downloads/bulk', {
    competition_id: competitionId,
    filter_mode: filterMode,
    format_mode: formatMode,
    confirm: true,
  })
  return data
}

// Download specific replay episodes by ID (e.g. a top performer's replays on the
// Top 10% Replays page) — no submission ownership required.
export async function startReplayDownload(
  episodeIds: string[],
  formatMode: FormatMode = 'zip',
): Promise<StartDownloadResponse> {
  const { data } = await apiClient.post<StartDownloadResponse>('/downloads/replays', {
    episode_ids: episodeIds,
    format_mode: formatMode,
  })
  return data
}

export async function getJobStatus(jobUuid: string): Promise<DownloadJob> {
  const { data } = await apiClient.get<DownloadJob>(`/downloads/${jobUuid}/status`)
  return data
}

export async function cancelJob(jobUuid: string): Promise<void> {
  await apiClient.delete(`/downloads/${jobUuid}`)
}

export async function getDownloadHistory(): Promise<DownloadHistoryResponse> {
  const { data } = await apiClient.get<DownloadHistoryResponse>('/downloads')
  return data
}

// Build a direct, authless URL is not possible (file route is protected); the
// browser download is triggered via fetch with the bearer token, then a blob.
export async function downloadJobFile(jobUuid: string): Promise<Blob> {
  const { data } = await apiClient.get(`/downloads/${jobUuid}/file`, {
    responseType: 'blob',
  })
  return data as Blob
}

// --- Collections ---
export async function getCollections(): Promise<CollectionListResponse> {
  const { data } = await apiClient.get<CollectionListResponse>('/collections')
  return data
}

export async function syncCollections(): Promise<CollectionListResponse> {
  const { data } = await apiClient.post<CollectionListResponse>('/collections/sync', {})
  return data
}

export async function getCollectionItems(
  collectionId: number,
  itemFilter: CollectionItemFilter,
  medals: Medal[] = [],
): Promise<CollectionItemsResponse> {
  const { data } = await apiClient.get<CollectionItemsResponse>(
    `/collections/${collectionId}/items`,
    { params: { item_filter: itemFilter, medals: medals.join(',') } },
  )
  return data
}

// Drill into a COMPETITION/DATASET collection item: its top notebooks +
// discussions (live, paced, cached server-side).
export async function getCollectionItemContents(
  collectionId: number,
  itemId: number,
): Promise<CollectionItemContentsResponse> {
  const { data } = await apiClient.get<CollectionItemContentsResponse>(
    `/collections/${collectionId}/items/${itemId}/contents`,
  )
  return data
}

export async function syncCollectionItems(
  collectionId: number,
): Promise<CollectionItemsResponse> {
  const { data } = await apiClient.post<CollectionItemsResponse>(
    `/collections/${collectionId}/sync`,
    {},
  )
  return data
}

export async function startCollectionDownload(
  collectionId: number,
  itemFilter: CollectionItemFilter,
  perCompetitionCap: number,
  medals: Medal[] = [],
): Promise<CollectionDownloadResponse> {
  const { data } = await apiClient.post<CollectionDownloadResponse>(
    `/collections/${collectionId}/download`,
    {
      item_filter: itemFilter,
      format_mode: 'zip',
      per_competition_cap: perCompetitionCap,
      medals,
      confirm: true,
    },
  )
  return data
}

// Download a SINGLE collection item (its notebook+output+log, topic Markdown,
// or a competition/dataset drill-down) instead of the whole collection.
export async function startCollectionItemDownload(
  collectionId: number,
  itemId: number,
  perCompetitionCap = 50,
  medals: Medal[] = [],
): Promise<CollectionDownloadResponse> {
  const { data } = await apiClient.post<CollectionDownloadResponse>(
    `/collections/${collectionId}/items/${itemId}/download`,
    {
      item_filter: 'all',
      format_mode: 'zip',
      per_competition_cap: perCompetitionCap,
      medals,
      confirm: true,
    },
  )
  return data
}

// --- WebSocket URL helper (token in query param; WS can't set headers) ---
export function buildWsUrl(jobUuid: string): string | null {
  const token = getAccessToken()
  if (!token) return null
  const wsBase = BASE_URL.replace(/^http/, 'ws')
  return `${wsBase}/ws/downloads/${jobUuid}?token=${encodeURIComponent(token)}`
}
