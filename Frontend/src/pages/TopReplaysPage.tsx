import { useEffect, useState, type JSX } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  getLatestTop100Export,
  getLeaderboardHistory,
  getTop100ExportCapabilities,
  startReplayDownload,
  startTop100Export,
  syncLeaderboard,
} from '@/api/endpoints'
import { useToast } from '@/components/shared/ToastProvider'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { CompetitionPicker } from '@/components/shared/CompetitionPicker'
import { LastSynced } from '@/components/shared/LastSynced'
import {
  ArrowLeftIcon,
  ArrowUpRightIcon,
  DownloadIcon,
  InboxIcon,
  PackageIcon,
  TargetIcon,
} from '@/components/shared/icons'
import { useDownloadStore } from '@/store/downloadStore'
import type {
  LeaderboardDay,
  Top100ExportCapabilities,
  Top100ExportJob,
  Top100ExportTarget,
  TopPerformer,
} from '@/types'

const ACTIVE_EXPORT_STATUSES = new Set([
  'queued',
  'waiting_for_replays',
  'downloading',
  'uploading',
])

interface ExportProgressProps {
  label: string
  job: Top100ExportJob
}

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
  const [downloadingPlayer, setDownloadingPlayer] = useState<string | null>(null)
  const [capabilities, setCapabilities] = useState<Top100ExportCapabilities | null>(null)
  const [kaggleExport, setKaggleExport] = useState<Top100ExportJob | null>(null)
  const [driveExport, setDriveExport] = useState<Top100ExportJob | null>(null)
  const [startingExport, setStartingExport] = useState<Top100ExportTarget | null>(null)

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
        setDays([...res.days].reverse())
        setSyncedAt(res.last_synced_at ?? null)
      })
      .catch(() => active && notify('error', 'Could not load top-replay history.'))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [activeId, reloadKey, notify])

  useEffect(() => {
    if (activeId === null) return
    let active = true
    Promise.all([
      getTop100ExportCapabilities(activeId),
      getLatestTop100Export(activeId, 'kaggle_dataset'),
      getLatestTop100Export(activeId, 'google_drive'),
    ])
      .then(([caps, kaggle, drive]) => {
        if (!active) return
        setCapabilities(caps)
        setKaggleExport(kaggle.job)
        setDriveExport(drive.job)
      })
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [activeId, reloadKey])

  useEffect(() => {
    if (activeId === null) return
    const hasActiveExport = [kaggleExport, driveExport].some(
      (job) => job && ACTIVE_EXPORT_STATUSES.has(job.status),
    )
    if (!hasActiveExport) return
    const timer = window.setInterval(() => {
      void Promise.all([
        getLatestTop100Export(activeId, 'kaggle_dataset'),
        getLatestTop100Export(activeId, 'google_drive'),
      ]).then(([kaggle, drive]) => {
        setKaggleExport(kaggle.job)
        setDriveExport(drive.job)
      })
    }, 5000)
    return () => window.clearInterval(timer)
  }, [activeId, kaggleExport, driveExport])

  const handleSync = async (): Promise<void> => {
    if (activeId === null) return
    setSyncing(true)
    try {
      const res = await syncLeaderboard(activeId, false)
      if (res.status === 'skipped') {
        notify('info', res.message)
      } else {
        notify('success', 'Resolving the top 100 players. You can refresh while it continues.')
      }
    } catch (err) {
      if ((err as { response?: { status?: number } })?.response?.status !== 429) {
        notify('error', 'Could not start sync.')
      }
    } finally {
      setSyncing(false)
    }
  }

  const handlePlayerDownload = async (day: string, player: TopPerformer): Promise<void> => {
    if (player.episode_ids.length === 0) return
    const key = `${day}:${player.team_id}`
    const playerName = player.team_name ?? player.team_id
    const safePlayerName = playerName.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 70)
    const archiveName = `${day}_rank-${String(player.rank).padStart(3, '0')}_${safePlayerName}_${player.episode_count}-episodes`
    setDownloadingPlayer(key)
    try {
      const res = await startReplayDownload(player.episode_ids, 'zip', archiveName)
      setActiveJobId(res.job_id)
      notify('success', `Creating one ZIP with ${player.episode_count} episodes for ${playerName}.`)
      navigate('/downloads')
    } catch {
      notify('error', `Could not start the ZIP for ${playerName}.`)
    } finally {
      setDownloadingPlayer(null)
    }
  }

  const handleExport = async (target: Top100ExportTarget): Promise<void> => {
    if (activeId === null) return
    if (
      target === 'kaggle_dataset' &&
      !window.confirm(
        'Create a public Kaggle Dataset containing 100 player ZIPs for the final competition day?',
      )
    ) {
      return
    }
    setStartingExport(target)
    try {
      const job = await startTop100Export(activeId, target, target === 'kaggle_dataset')
      if (target === 'kaggle_dataset') setKaggleExport(job)
      else setDriveExport(job)
      notify(
        'success',
        target === 'kaggle_dataset'
          ? 'Dataset export queued. The Kaggle link will appear here when publishing finishes.'
          : 'Google Drive export queued.',
      )
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
      notify('error', detail ?? 'Could not start the Top 100 export.')
    } finally {
      setStartingExport(null)
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
          Top 100 Replays
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
          {syncing ? 'Starting…' : 'Sync top 100'}
        </button>
        <button
          type="button"
          className="btn-ghost"
          disabled={activeId === null}
          onClick={() => setReloadKey((key) => key + 1)}
        >
          Refresh
        </button>
      </div>

      <div className="flex flex-col gap-2" style={{ marginBottom: 20 }}>
        <div className="flex flex-wrap items-center gap-3">
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', margin: 0 }}>
            One ZIP per player per day. Each ZIP contains all resolved episode replay JSON files.
          </p>
          {!loading && <LastSynced at={syncedAt} />}
        </div>
        <p style={{ color: 'var(--text-faint)', fontSize: '0.8rem', margin: 0 }}>
          The sync stops at the competition end date. Rate limits pause the resolver and it resumes
          from saved progress.
        </p>
      </div>

      <div
        className="glass-card"
        style={{
          padding: 18,
          marginBottom: 20,
          borderColor: 'color-mix(in srgb, var(--accent-coral) 35%, var(--border-subtle))',
        }}
      >
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <p
              className="mono"
              style={{ color: 'var(--accent-coral)', fontSize: '0.72rem', margin: '0 0 5px' }}
            >
              DATASET DELIVERY
            </p>
            <h2 style={{ fontSize: '1.05rem', margin: 0 }}>Package the final Top 100</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', margin: '5px 0 0' }}>
              Prepares one validated ZIP per player, writes a count manifest, and resumes after
              interruptions.
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              className="btn-primary-glow"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}
              disabled={
                activeId === null ||
                startingExport !== null ||
                !capabilities?.kaggle_dataset_ready ||
                Boolean(kaggleExport && ACTIVE_EXPORT_STATUSES.has(kaggleExport.status))
              }
              onClick={() => void handleExport('kaggle_dataset')}
            >
              <PackageIcon size={16} />
              {startingExport === 'kaggle_dataset' ? 'Starting…' : 'Publish 100 ZIPs to Kaggle'}
            </button>
            <button
              type="button"
              className="btn-ghost"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}
              disabled={
                activeId === null ||
                startingExport !== null ||
                !capabilities?.google_drive_ready ||
                Boolean(driveExport && ACTIVE_EXPORT_STATUSES.has(driveExport.status))
              }
              title={capabilities?.google_drive_message}
              onClick={() => void handleExport('google_drive')}
            >
              <DownloadIcon size={16} />
              {startingExport === 'google_drive' ? 'Starting…' : 'Upload 100 ZIPs to Drive'}
            </button>
          </div>
        </div>
        {!capabilities?.google_drive_ready && capabilities && (
          <p style={{ color: 'var(--text-faint)', fontSize: '0.76rem', margin: '10px 0 0' }}>
            Google Drive setup: {capabilities.google_drive_message}.
          </p>
        )}
        {(kaggleExport || driveExport) && (
          <div className="flex flex-col gap-2" style={{ marginTop: 12 }}>
            {kaggleExport && <ExportProgress label="Kaggle Dataset" job={kaggleExport} />}
            {driveExport && <ExportProgress label="Google Drive" job={driveExport} />}
          </div>
        )}
      </div>

      {loading ? (
        <div className="flex flex-col gap-4">
          {Array.from({ length: 3 }).map((_, index) => (
            <LoadingSkeleton key={index} height="120px" borderRadius="16px" />
          ))}
        </div>
      ) : days.length === 0 ? (
        <div className="text-center py-16" style={{ color: 'var(--text-muted)' }}>
          <div className="mb-3 flex justify-center" style={{ color: 'var(--text-faint)' }}>
            <InboxIcon size={44} />
          </div>
          <p>No snapshots yet. Click Sync top 100 to start.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          {days.map((day) => {
            const players = day.top_performers.slice(0, 100)
            const resolvedCount = players.filter((player) => player.episodes_resolved).length
            return (
              <div key={day.date} className="glass-card" style={{ padding: 20 }}>
                <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                  <h3 style={{ fontSize: '1.05rem' }}>{day.date}</h3>
                  <span className="pill pill-info">
                    {players.length} players shown · {resolvedCount} resolved ·{' '}
                    {day.total_teams.toLocaleString()} total teams
                  </span>
                </div>
                <div className="flex flex-col">
                  {players.map((player) => {
                    const key = `${day.date}:${player.team_id}`
                    const isStarting = downloadingPlayer === key
                    return (
                      <div
                        key={key}
                        className="flex items-center justify-between gap-4 flex-wrap"
                        style={{ borderTop: '1px solid var(--border-subtle)', padding: '12px 0' }}
                      >
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className="mono" style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>
                            #{player.rank}
                          </span>
                          <span style={{ fontWeight: 500 }}>{player.team_name ?? player.team_id}</span>
                          {player.score !== null && (
                            <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                              {player.score.toFixed(1)}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3">
                          <span
                            className={`pill ${player.episodes_resolved ? 'pill-success' : 'pill-neutral'}`}
                          >
                            {player.episodes_resolved
                              ? `${player.episode_count} episodes`
                              : 'Pending sync'}
                          </span>
                          <button
                            type="button"
                            className="btn-ghost"
                            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                            disabled={isStarting || !player.episodes_resolved || player.episode_count === 0}
                            onClick={() => void handlePlayerDownload(day.date, player)}
                          >
                            <DownloadIcon size={15} />
                            {isStarting ? 'Starting…' : 'Download ZIP'}
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function ExportProgress({ label, job }: ExportProgressProps): JSX.Element {
  const status = exportStatus(job)
  return (
    <div
      className="flex items-center justify-between gap-3 flex-wrap"
      style={{
        padding: '9px 11px',
        borderRadius: 10,
        background: 'var(--bg-overlay)',
        border: '1px solid var(--border-subtle)',
        fontSize: '0.8rem',
      }}
    >
      <span>
        <strong>{label}</strong>
        <span style={{ color: 'var(--text-muted)' }}> · {status}</span>
      </span>
      {job.result_url && (
        <a
          href={job.result_url}
          target="_blank"
          rel="noreferrer"
          className="btn-ghost"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '5px 9px' }}
        >
          Open dataset <ArrowUpRightIcon size={13} />
        </a>
      )}
    </div>
  )
}

function exportStatus(job: Top100ExportJob): string {
  if (job.status === 'waiting_for_replays') {
    return `resolving players ${job.resolved_players}/${job.total_players}`
  }
  if (job.status === 'downloading') {
    const rank = job.current_rank ? `, rank ${job.current_rank}` : ''
    return `preparing ZIPs ${job.completed_players}/${job.total_players}${rank}`
  }
  if (job.status === 'uploading') return 'uploading and verifying'
  if (job.status === 'done') return `${job.completed_players} ZIPs published`
  if (job.status === 'failed') return job.error ?? 'failed'
  return 'queued'
}
