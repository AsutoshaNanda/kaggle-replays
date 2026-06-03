// Downloads page: Section 1 = new download (if a submission was selected),
// Section 2 = history table + live progress card for the active job.

import { useCallback, useEffect, useRef, useState, type JSX } from 'react'
import { cancelJob, getDownloadHistory, startDownload } from '@/api/endpoints'
import { useToast } from '@/components/shared/ToastProvider'
import { DownloadControls } from '@/components/downloads/DownloadControls'
import { DownloadHistoryTable } from '@/components/downloads/DownloadHistoryTable'
import { DownloadProgressCard } from '@/components/downloads/DownloadProgressCard'
import { useDownloadJob } from '@/hooks/useDownloadJob'
import { useDownloadStore } from '@/store/downloadStore'
import type { DownloadHistoryEntry, EpisodeFilter, FormatMode } from '@/types'

const TERMINAL = ['done', 'failed', 'cancelled']

export function DownloadsPage(): JSX.Element {
  const { notify } = useToast()
  const selectedSubmission = useDownloadStore((s) => s.selectedSubmission)
  const activeJobId = useDownloadStore((s) => s.activeJobId)
  const setActiveJobId = useDownloadStore((s) => s.setActiveJobId)

  const [history, setHistory] = useState<DownloadHistoryEntry[]>([])
  const [loadingHistory, setLoadingHistory] = useState(true)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  // Guards against re-fetch loops: only one fetch in flight, and the mount
  // fetch fires exactly once (it does NOT auto-retry on failure — the user
  // retries via the button).
  const inFlight = useRef(false)
  const prevJobStatus = useRef<string | null>(null)

  const liveJob = useDownloadJob(activeJobId)

  const loadHistory = useCallback(async (): Promise<void> => {
    if (inFlight.current) return
    inFlight.current = true
    setLoadingHistory(true)
    setHistoryError(null)
    try {
      const res = await getDownloadHistory()
      setHistory(res.jobs)
    } catch {
      // Single inline error state — no toast, no stacking, no auto-retry.
      setHistoryError('Could not load download history.')
    } finally {
      setLoadingHistory(false)
      inFlight.current = false
    }
  }, [])

  // Fetch once on mount.
  useEffect(() => {
    void loadHistory()
  }, [loadHistory])

  // Refresh history only when a watched job TRANSITIONS into a terminal state
  // (not on every poll/WS tick, which would loop since liveJob is a new object
  // each tick).
  useEffect(() => {
    const status = liveJob?.status ?? null
    if (
      status &&
      status !== prevJobStatus.current &&
      TERMINAL.includes(status)
    ) {
      void loadHistory()
    }
    prevJobStatus.current = status
  }, [liveJob, loadHistory])

  const handleStart = async (filter: EpisodeFilter, format: FormatMode): Promise<void> => {
    if (!selectedSubmission) return
    setStarting(true)
    try {
      const res = await startDownload(selectedSubmission.id, filter, format)
      setActiveJobId(res.job_id)
      notify('success', 'Download started.')
      await loadHistory()
    } catch {
      notify('error', 'Failed to start download.')
    } finally {
      setStarting(false)
    }
  }

  const handleCancel = async (jobId: string): Promise<void> => {
    try {
      await cancelJob(jobId)
      notify('info', 'Download cancelled.')
      if (activeJobId === jobId) setActiveJobId(null)
      await loadHistory()
    } catch {
      notify('error', 'Could not cancel the job.')
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="animate-in">
        <h1
          className="gradient-text mb-2"
          style={{ fontSize: 'clamp(1.8rem, 4vw, 2.5rem)', fontWeight: 700 }}
        >
          Downloads
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>
          Manage active jobs and review download history.
        </p>
      </div>

      {selectedSubmission && (
        <section className="animate-in stagger-1">
          <h2 className="mb-1" style={{ fontSize: '1.25rem' }}>
            New Download
          </h2>
          <p
            className="mb-4"
            style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}
          >
            {selectedSubmission.title}
            {selectedSubmission.score !== null && (
              <>
                {' · score '}
                <span className="mono" style={{ color: 'var(--text-primary)' }}>
                  {selectedSubmission.score.toFixed(1)}
                </span>
              </>
            )}
          </p>
          <DownloadControls
            submission={selectedSubmission}
            onStart={(f, fmt) => void handleStart(f, fmt)}
            starting={starting}
          />
        </section>
      )}

      {liveJob && (
        <section className="animate-in stagger-2">
          <h2 className="mb-4" style={{ fontSize: '1.15rem' }}>
            Active Job
          </h2>
          <DownloadProgressCard job={liveJob} onCancel={(id) => void handleCancel(id)} />
        </section>
      )}

      <section className="animate-in stagger-3">
        <h2 className="mb-4" style={{ fontSize: '1.25rem' }}>
          Download History
        </h2>
        {historyError ? (
          <div
            className="glass-card flex flex-col items-center gap-3 text-center"
            style={{ padding: 32, color: 'var(--text-muted)' }}
          >
            <p style={{ margin: 0 }}>{historyError}</p>
            <button type="button" className="btn-ghost" onClick={() => void loadHistory()}>
              Retry
            </button>
          </div>
        ) : (
          <DownloadHistoryTable
            jobs={history}
            loading={loadingHistory}
            onSelect={(id) => setActiveJobId(id)}
          />
        )}
      </section>
    </div>
  )
}
