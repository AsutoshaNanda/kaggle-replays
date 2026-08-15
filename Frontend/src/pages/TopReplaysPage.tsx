// Top 10% Replays — daily snapshots (competition start to today), each day showing
// the top performers (rank 1–50 / top 10%) with their replay episode IDs.
// Reachable per-competition (/competitions/:id/top-replays) or top-level
// (/top-replays, competition chosen via the in-page picker).

import { useEffect, useMemo, useState, useTransition, type JSX } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getLeaderboardHistory, startReplayDownload, syncLeaderboard } from '@/api/endpoints'
import { useToast } from '@/components/shared/ToastProvider'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { CompetitionPicker } from '@/components/shared/CompetitionPicker'
import { LastSynced } from '@/components/shared/LastSynced'
import { ArrowLeftIcon, CheckSquareIcon, DownloadIcon, InboxIcon, MinusSquareIcon, SquareIcon, TargetIcon } from '@/components/shared/icons'
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
  const [selectedEpisodeIds, setSelectedEpisodeIds] = useState<Set<string>>(new Set())
  const [downloadingSelected, setDownloadingSelected] = useState(false)
  const [isPending, startTransition] = useTransition()

  // Every resolved replay episode ID across all captured days (first → current), de-duped.
  // Memoized so flatMap/Set construction only runs when `days` data actually changes.
  const allEpisodeIds = useMemo(
    () => Array.from(new Set(days.flatMap((d) => d.top_performers.flatMap((p) => p.episode_ids)))),
    [days],
  )

  const allSelected = allEpisodeIds.length > 0 && selectedEpisodeIds.size === allEpisodeIds.length
  const someSelected = selectedEpisodeIds.size > 0 && !allSelected

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
        const reversedDays = [...res.days].reverse() // newest day first
        setDays(reversedDays)
        setSyncedAt(res.last_synced_at ?? null)

        // Select all unique resolved episodes by default on load
        const resolvedEpisodeIds = Array.from(
          new Set(reversedDays.flatMap((d) => d.top_performers.flatMap((p) => p.episode_ids))),
        )
        setSelectedEpisodeIds(new Set(resolvedEpisodeIds))
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
      const res = await syncLeaderboard(activeId, false)
      if (res.status === 'skipped') {
        notify('info', 'Already synced moments ago — hit Refresh to see the latest.')
      } else {
        notify('success', "Capturing today's top performers and their replay IDs — refresh in a few seconds.")
      }
    } catch (err) {
      if ((err as { response?: { status?: number } })?.response?.status !== 429) {
        notify('error', 'Could not start sync.')
      }
    } finally {
      setSyncing(false)
    }
  }

  const handleDownloadSelected = async (): Promise<void> => {
    const idsToDownload = Array.from(selectedEpisodeIds)
    if (idsToDownload.length === 0) return
    setDownloadingSelected(true)
    try {
      const res = await startReplayDownload(idsToDownload, 'zip')
      setActiveJobId(res.job_id)
      notify('success', `Zipping ${idsToDownload.length} replays — see Downloads.`)
      navigate('/downloads')
    } catch {
      notify('error', 'Could not start the replays ZIP download.')
    } finally {
      setDownloadingSelected(false)
    }
  }

  const toggleAllSelection = (): void => {
    if (isPending || allEpisodeIds.length === 0) return
    startTransition(() => {
      if (allSelected) {
        setSelectedEpisodeIds(new Set())
      } else {
        setSelectedEpisodeIds(new Set(allEpisodeIds))
      }
    })
  }

  const toggleUserEpisodes = (userEids: string[]): void => {
    if (isPending || userEids.length === 0) return
    startTransition(() => {
      const isUserFullySelected = userEids.every((id) => selectedEpisodeIds.has(id))
      setSelectedEpisodeIds((prev) => {
        const next = new Set(prev)
        if (isUserFullySelected) {
          userEids.forEach((id) => next.delete(id))
        } else {
          userEids.forEach((id) => next.add(id))
        }
        return next
      })
    })
  }

  const toggleEpisode = (eid: string): void => {
    if (isPending) return
    setSelectedEpisodeIds((prev) => {
      const next = new Set(prev)
      if (next.has(eid)) {
        next.delete(eid)
      } else {
        next.add(eid)
      }
      return next
    })
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
          className="btn-icon"
          disabled={allEpisodeIds.length === 0 || isPending}
          onClick={toggleAllSelection}
          title={allSelected ? 'Deselect all episodes' : 'Select all episodes'}
          aria-label={allSelected ? 'Deselect all episodes' : 'Select all episodes'}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            minWidth: 34,
            minHeight: 34,
          }}
        >
          {isPending ? (
            <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
          ) : allSelected ? (
            <CheckSquareIcon size={18} style={{ color: 'var(--accent-cyan)' }} />
          ) : someSelected ? (
            <MinusSquareIcon size={18} style={{ color: 'var(--accent-cyan)' }} />
          ) : (
            <SquareIcon size={18} style={{ color: 'var(--text-faint)' }} />
          )}
        </button>
        <button
          type="button"
          className="btn-ghost"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          disabled={downloadingSelected || selectedEpisodeIds.size === 0 || isPending}
          onClick={() => void handleDownloadSelected()}
          title="Download all selected replays as one ZIP"
        >
          <DownloadIcon size={16} />
          {downloadingSelected
            ? 'Starting…'
            : `Download selected (ZIP)${selectedEpisodeIds.size ? ` · ${selectedEpisodeIds.size}` : ''}`}
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
            The leaderboard's top performers on each captured day — click episode chips to toggle selection,
            or use the user toggle to select/deselect a team. Click Sync now to capture today.
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
                {day.top_performers.slice(0, 50).map((p) => {
                  const userEids = p.episode_ids
                  const userSelectedCount = userEids.filter((id) => selectedEpisodeIds.has(id)).length
                  const isUserFullySelected = userEids.length > 0 && userSelectedCount === userEids.length
                  const isUserPartiallySelected = userSelectedCount > 0 && !isUserFullySelected

                  return (
                    <div
                      key={`${day.date}-${p.team_id}`}
                      style={{
                        borderTop: '1px solid var(--border-subtle)',
                        paddingTop: 10,
                      }}
                    >
                      <div className="flex items-center gap-2.5 flex-wrap">
                        {userEids.length > 0 && (
                          <button
                            type="button"
                            className="btn-icon"
                            disabled={isPending}
                            style={{
                              padding: '2px 5px',
                              borderRadius: 6,
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              minWidth: 24,
                              minHeight: 24,
                            }}
                            onClick={() => toggleUserEpisodes(userEids)}
                            title={
                              isUserFullySelected
                                ? `Deselect all ${userEids.length} replays for ${p.team_name ?? p.team_id}`
                                : `Select all ${userEids.length} replays for ${p.team_name ?? p.team_id}`
                            }
                            aria-label={`Toggle selection for ${p.team_name ?? p.team_id}`}
                          >
                            {isPending ? (
                              <div className="spinner" style={{ width: 12, height: 12, borderWidth: 1.75 }} />
                            ) : isUserFullySelected ? (
                              <CheckSquareIcon size={15} style={{ color: 'var(--accent-cyan)' }} />
                            ) : isUserPartiallySelected ? (
                              <MinusSquareIcon size={15} style={{ color: 'var(--accent-cyan)' }} />
                            ) : (
                              <SquareIcon size={15} style={{ color: 'var(--text-faint)' }} />
                            )}
                          </button>
                        )}
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
                      {userEids.length > 0 && (
                        <div className="flex flex-wrap gap-2 mt-2">
                          {userEids.map((eid) => {
                            const isSelected = selectedEpisodeIds.has(eid)
                            return (
                              <button
                                key={eid}
                                type="button"
                                className="mono"
                                disabled={isPending}
                                onClick={() => toggleEpisode(eid)}
                                title={isSelected ? 'Click to deselect replay' : 'Click to select replay'}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  fontSize: '0.72rem',
                                  padding: '4px 10px',
                                  borderRadius: 6,
                                  border: isSelected
                                    ? '1px solid var(--accent-cyan)'
                                    : '1px solid var(--border-subtle)',
                                  background: isSelected ? 'var(--bg-raised)' : 'transparent',
                                  color: isSelected ? 'var(--text-primary)' : 'var(--text-faint)',
                                  fontWeight: isSelected ? 600 : 400,
                                  cursor: 'pointer',
                                  boxShadow: isSelected ? 'var(--shadow-sm)' : 'none',
                                  transition: 'all 150ms ease',
                                }}
                              >
                                {eid}
                              </button>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
