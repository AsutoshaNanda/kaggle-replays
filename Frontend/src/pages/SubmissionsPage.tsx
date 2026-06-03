// Submissions page: heading + back button + leaderboard/top-replays links +
// "Sync now" + sortable submission table. Reads are served from the DB cache;
// polling (DB-only, no Kaggle calls) fills in counts/scores as the background
// resolver completes.

import { useEffect, useRef, useState, type JSX } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getSubmissions, syncCompetitionData } from '@/api/endpoints'
import { useToast } from '@/components/shared/ToastProvider'
import { SubmissionTable } from '@/components/submissions/SubmissionTable'
import { LastSynced } from '@/components/shared/LastSynced'
import { useDownloadStore } from '@/store/downloadStore'
import { ArrowLeftIcon, TrophyIcon, TargetIcon } from '@/components/shared/icons'
import type { Submission } from '@/types'

const POLL_MS = 4000
const MAX_POLLS = 8

export function SubmissionsPage(): JSX.Element {
  const { competitionId } = useParams()
  const navigate = useNavigate()
  const { notify } = useToast()
  const setSelectedSubmission = useDownloadStore((s) => s.setSelectedSubmission)

  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [syncedAt, setSyncedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const pollsRef = useRef(0)

  useEffect(() => {
    if (!competitionId) return
    let active = true
    let timer: number | undefined
    pollsRef.current = 0

    const load = async (isPoll: boolean): Promise<void> => {
      try {
        const res = await getSubmissions(Number(competitionId))
        if (!active) return
        setSubmissions(res.submissions)
        setSyncedAt(res.last_synced_at ?? null)
        // Keep polling (DB reads only — never re-hits Kaggle) while any count or
        // score is still unknown, since the background resolver fills them in.
        const pending = res.submissions.some((s) => s.episode_count === null || s.score === null)
        if (pending && pollsRef.current < MAX_POLLS) {
          pollsRef.current += 1
          timer = window.setTimeout(() => void load(true), POLL_MS)
        }
      } catch {
        if (active && !isPoll) notify('error', 'Could not load submissions.')
      } finally {
        if (active && !isPoll) setLoading(false)
      }
    }
    void load(false)
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [competitionId, reloadKey, notify])

  const handleSync = async (): Promise<void> => {
    if (!competitionId) return
    setSyncing(true)
    try {
      const res = await syncCompetitionData(Number(competitionId))
      setSubmissions(res.submissions)
      setSyncedAt(res.last_synced_at ?? null)
      notify('success', 'Sync started — scores and episode counts will fill in shortly.')
      setReloadKey((k) => k + 1) // restart polling so resolved values appear
    } catch {
      notify('error', 'Could not start sync.')
    } finally {
      setSyncing(false)
    }
  }

  const handleDownload = (submission: Submission): void => {
    setSelectedSubmission(submission)
    navigate('/downloads')
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-2 animate-in">
        <button
          type="button"
          className="btn-icon"
          onClick={() => navigate('/competitions')}
          aria-label="Back to competitions"
        >
          <ArrowLeftIcon size={18} />
        </button>
        <h1
          className="gradient-text"
          style={{ fontSize: 'clamp(1.6rem, 3.5vw, 2.25rem)', fontWeight: 700, marginRight: 'auto' }}
        >
          Submissions
        </h1>
        <button
          type="button"
          className="btn-ghost"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.85rem' }}
          onClick={() => navigate(`/competitions/${competitionId}/leaderboard`)}
        >
          <TrophyIcon size={16} />
          Leaderboard
        </button>
        <button
          type="button"
          className="btn-ghost"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.85rem' }}
          onClick={() => navigate(`/competitions/${competitionId}/top-replays`)}
        >
          <TargetIcon size={16} />
          Top 10% Replays
        </button>
        <button
          type="button"
          className="btn-primary-glow"
          style={{ fontSize: '0.85rem' }}
          disabled={syncing}
          onClick={() => void handleSync()}
        >
          {syncing ? 'Syncing…' : 'Sync now'}
        </button>
      </div>
      <div style={{ marginBottom: 16 }}>
        <LastSynced at={syncedAt} />
      </div>
      <SubmissionTable
        submissions={submissions}
        loading={loading}
        onDownload={handleDownload}
      />
    </div>
  )
}
