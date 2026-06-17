// Top 10% Replays — daily snapshots (competition start to today), each day showing
// the top performers (rank 1–50 / top 10%) with their replay episode IDs.
// Reachable per-competition (/competitions/:id/top-replays) or top-level
// (/top-replays, competition chosen via the in-page picker).

import { useEffect, useState, type JSX } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getLeaderboardHistory, startReplayDownload, syncLeaderboard } from '@/api/endpoints'
import { useToast } from '@/components/shared/ToastProvider'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { CompetitionPicker } from '@/components/shared/CompetitionPicker'
import { LastSynced } from '@/components/shared/LastSynced'
import { ArrowLeftIcon, DownloadIcon, InboxIcon, TargetIcon } from '@/components/shared/icons'
import { useDownloadStore } from '@/store/downloadStore'
import type { LeaderboardDay } from '@/types'

export function TopReplaysPage(): JSX.Element {
  const { competitionId: routeId } = useParams()
  const navigate = useNavigate()
  const { notify } = useToast()

  const setActiveJobId = useDownloadStore((s) => s.setActiveJobId)

  const [activeId, setActiveId] = useState<number | null>(routeId ? Number(routeId) : null)
  const [days, setDays] = useState<LeaderboardDay[]>([])
  const [syncedAt, setSyncedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  // Which episode chip is currently kicking off a download (disables it briefly).
  const [downloadingEid, setDownloadingEid] = useState<string | null>(null)
  // True while the "Download all replays (ZIP)" job is being started.
  const [downloadingAll, setDownloadingAll] = useState(false)

  // Every resolved replay episode ID across all captured days (first → current),
  // de-duped — a team's IDs repeat day to day, so a Set both spans the whole
  // range and shrinks the "huge numbers" list into one ZIP request.
  const allEpisodeIds = Array.from(
    new Set(days.flatMap((d) => d.top_performers.flatMap((p) => p.episode_ids))),
  )

  // Active-flag guard: under React.StrictMode the effect runs twice in dev; the
  // flag ensures only the current invocation can toast, so a failure shows at
  // most one error (this was the "Could not load top-replay history" ×2 bug).
  useEffect(() => {
    if (activeId === null) {
      setLoading(false)
      return
    }
    let active = true
    setLoading(true)
    getLeaderboardHistory(activeId)
      .then((res) => {
        if (!active) return
        setDays([...res.days].reverse()) // newest day first
        setSyncedAt(res.last_synced_at ?? null)
      })
      .catch(() => active && notify('error', 'Could not load top-replay history.'))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [activeId, reloadKey, notify])

  const handleSync = async (): Promise<void> => {
    if (activeId === null) return
    setSyncing(true)
    try {
      // backfill=false -> a REAL leaderboard capture: today's standings PLUS the
      // top performers' replay episode IDs (bounded + paced on the backend).
      const res = await syncLeaderboard(activeId, false)
      if (res.status === 'skipped') {
        notify('info', 'Already synced moments ago — hit Refresh to see the latest.')
      } else {
        notify('success', "Capturing today's top performers and their replay IDs — refresh in a few seconds.")
      }
    } catch (err) {
      // 429s are already surfaced (with a Retry-After countdown) by the global
      // axios interceptor — don't stack a second, misleading error toast.
      if ((err as { response?: { status?: number } })?.response?.status !== 429) {
        notify('error', 'Could not start sync.')
      }
    } finally {
      setSyncing(false)
    }
  }

  const handleDownloadAll = async (): Promise<void> => {
    if (allEpisodeIds.length === 0) return
    setDownloadingAll(true)
    try {
      const res = await startReplayDownload(allEpisodeIds, 'zip')
      setActiveJobId(res.job_id)
      notify('success', `Zipping ${allEpisodeIds.length} replays — see Downloads.`)
      navigate('/downloads')
    } catch {
      notify('error', 'Could not start the replays ZIP download.')
    } finally {
      setDownloadingAll(false)
    }
  }

  const handleDownloadReplay = async (eid: string): Promise<void> => {
    setDownloadingEid(eid)
    try {
      const res = await startReplayDownload([eid])
      setActiveJobId(res.job_id)
      notify('success', `Downloading replay ${eid}.`)
      navigate('/downloads')
    } catch {
      notify('error', 'Could not start the replay download.')
    } finally {
      setDownloadingEid(null)
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-2 animate-in">
        <button
          type="button"
          className="btn-icon"
          onClick={() => navigate(routeId ? `/competitions/${routeId}/submissions` : '/competitions')}
          aria-label="Back"
        >
          <ArrowLeftIcon size={18} />
        </button>
        <h1
          className="gradient-text"
          style={{ fontSize: 'clamp(1.6rem, 3.5vw, 2.25rem)', fontWeight: 700, marginRight: 'auto' }}
        >
          Top 10% Replays
        </h1>
        <CompetitionPicker value={activeId} onChange={setActiveId} />
        <button
          type="button"
          className="btn-primary-glow"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          disabled={syncing || activeId === null}
          onClick={() => void handleSync()}
        >
          <TargetIcon size={16} />
          {syncing ? 'Syncing…' : 'Sync now'}
        </button>
        <button
          type="button"
          className="btn-ghost"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          disabled={downloadingAll || allEpisodeIds.length === 0}
          onClick={() => void handleDownloadAll()}
          title="Download every resolved replay (first → current date) as one ZIP"
        >
          <DownloadIcon size={16} />
          {downloadingAll
            ? 'Starting…'
            : `Download all replays (ZIP)${allEpisodeIds.length ? ` · ${allEpisodeIds.length}` : ''}`}
        </button>
        <button
          type="button"
          className="btn-ghost"
          disabled={activeId === null}
          onClick={() => setReloadKey((k) => k + 1)}
        >
          Refresh
        </button>
      </div>
      <div className="flex flex-col gap-2" style={{ marginBottom: 20 }}>
        <div className="flex flex-wrap items-center gap-3">
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', margin: 0 }}>
            The leaderboard's top performers on each captured day, with their replay episode IDs —
            click an ID to download that replay. Click Sync now to capture today.
          </p>
          {!loading && <LastSynced at={syncedAt} />}
        </div>
        <p style={{ color: 'var(--text-faint)', fontSize: '0.8rem', margin: 0 }}>
          These are the top teams' replays (not your own submissions), so you don't need to have
          submitted. A competition shows none if it hasn't been synced yet, the last sync was
          rate-limited by Kaggle before resolving, or it isn't a simulation competition with replays.
        </p>
      </div>

      {loading ? (
        <div className="flex flex-col gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <LoadingSkeleton key={i} height="120px" borderRadius="16px" />
          ))}
        </div>
      ) : days.length === 0 ? (
        <div className="text-center py-16" style={{ color: 'var(--text-muted)' }}>
          <div className="mb-3 flex justify-center" style={{ color: 'var(--text-faint)' }}>
            <InboxIcon size={44} />
          </div>
          <p>No snapshots yet — click Sync now to capture today's top performers and their replays.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          {days.map((day) => (
            <div key={day.date} className="glass-card" style={{ padding: 20 }}>
              <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <h3 style={{ fontSize: '1.05rem' }}>{day.date}</h3>
                <span className="pill pill-info">
                  {day.total_teams.toLocaleString()} teams · top {day.top10_cutoff_rank}
                </span>
              </div>
              {!day.top_performers.some((p) => p.episode_ids.length > 0) && (
                <p
                  style={{
                    color: 'var(--text-faint)',
                    fontSize: '0.82rem',
                    margin: '0 0 12px',
                  }}
                >
                  No replay IDs resolved for this day — Sync now again (Kaggle may have rate-limited
                  the last attempt), or this competition may not expose replays.
                </p>
              )}
              <div className="flex flex-col gap-3">
                {day.top_performers.slice(0, 50).map((p) => (
                  <div
                    key={`${day.date}-${p.team_id}`}
                    style={{
                      borderTop: '1px solid var(--border-subtle)',
                      paddingTop: 10,
                    }}
                  >
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="mono" style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>
                        #{p.rank}
                      </span>
                      <span style={{ fontWeight: 500 }}>{p.team_name ?? p.team_id}</span>
                      {p.score !== null && (
                        <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                          {p.score.toFixed(1)}
                        </span>
                      )}
                    </div>
                    {p.episode_ids.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {p.episode_ids.map((eid) => (
                          <button
                            key={eid}
                            type="button"
                            className="mono"
                            disabled={downloadingEid === eid}
                            onClick={() => void handleDownloadReplay(eid)}
                            title="Download this replay (.json)"
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 5,
                              fontSize: '0.72rem',
                              padding: '3px 9px',
                              borderRadius: 6,
                              border: '1px solid var(--border-default)',
                              background: 'var(--bg-overlay)',
                              color: 'var(--text-muted)',
                              cursor: downloadingEid === eid ? 'progress' : 'pointer',
                              opacity: downloadingEid === eid ? 0.6 : 1,
                            }}
                          >
                            <DownloadIcon size={12} />
                            {eid}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
