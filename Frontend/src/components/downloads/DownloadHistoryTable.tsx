// Download history table (last 50 jobs).

import type { CSSProperties, JSX } from 'react'
import type { DownloadHistoryEntry } from '@/types'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'

interface DownloadHistoryTableProps {
  jobs: DownloadHistoryEntry[]
  loading: boolean
  onSelect: (jobId: string) => void
}

const STATUS_CLASS: Record<DownloadHistoryEntry['status'], string> = {
  queued: 'pill pill-neutral',
  running: 'pill pill-info',
  done: 'pill pill-success',
  failed: 'pill pill-danger',
  cancelled: 'pill pill-neutral',
}

// 9 columns: Job | Submission | Score | Filter | Format | Started | Progress | Status | Actions
const GRID =
  '110px minmax(150px, 1.4fr) 70px 70px 70px minmax(140px, 1fr) 80px 95px 90px'

// Single-line cells whose overflow must clip with an ellipsis (not bleed).
const TRUNCATE: CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

export function DownloadHistoryTable({
  jobs,
  loading,
  onSelect,
}: DownloadHistoryTableProps): JSX.Element {
  if (loading) {
    return (
      <div className="glass-card" style={{ padding: 16 }}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} style={{ marginBottom: 10 }}>
            <LoadingSkeleton shape="row" />
          </div>
        ))}
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <div className="text-center py-10" style={{ color: 'var(--text-muted)' }}>
        <p>No downloads yet.</p>
      </div>
    )
  }

  return (
    <div className="glass-card overflow-hidden" style={{ overflowX: 'auto' }}>
      <div className="data-table" style={{ minWidth: 920 }}>
        {/* Header is its OWN grid with the SAME tracks as each row, so header and
            body align even though each row is an independent grid (which lets
            rows keep their hover background). Mirrors SubmissionTable. */}
        <div style={{ display: 'grid', gridTemplateColumns: GRID }}>
          <div className="data-table-header">Job</div>
          <div className="data-table-header">Submission</div>
          <div className="data-table-header" style={{ display: 'flex', justifyContent: 'flex-end' }}>
            Score
          </div>
          <div className="data-table-header">Filter</div>
          <div className="data-table-header">Format</div>
          <div className="data-table-header">Started</div>
          <div className="data-table-header">Progress</div>
          <div className="data-table-header">Status</div>
          <div
            className="data-table-header"
            style={{ display: 'flex', justifyContent: 'flex-end' }}
          >
            Actions
          </div>
        </div>

        {jobs.map((job) => {
          const isCollection = job.job_type === 'collection'
          const jobLabel = `${job.job_id.slice(0, 8)}…${job.is_bulk ? ' (bulk)' : ''}${isCollection ? ' (coll.)' : ''}`
          const startedFull = job.started_at ? new Date(job.started_at).toLocaleString() : '—'
          const subTitle = isCollection
            ? (job.collection_name ?? 'Collection')
            : (job.submission_title ?? '—')
          const scoreText =
            job.submission_score !== null && job.submission_score !== undefined
              ? job.submission_score.toFixed(1)
              : '—'
          return (
            <div
              key={job.job_id}
              className="data-table-rowwrap"
              style={{ gridTemplateColumns: GRID }}
            >
              <div
                className="data-table-cell mono"
                style={{ ...TRUNCATE, color: 'var(--text-muted)' }}
                title={job.job_id}
              >
                {jobLabel}
              </div>
              <div className="data-table-cell" style={TRUNCATE} title={subTitle}>
                {subTitle}
              </div>
              <div
                className="data-table-cell mono"
                style={{ ...TRUNCATE, justifyContent: 'flex-end', color: 'var(--text-muted)' }}
              >
                {scoreText}
              </div>
              <div className="data-table-cell" style={{ ...TRUNCATE, color: 'var(--text-muted)' }}>
                {job.filter_mode}
              </div>
              <div className="data-table-cell" style={{ ...TRUNCATE, color: 'var(--text-muted)' }}>
                {job.format_mode}
              </div>
              <div
                className="data-table-cell"
                style={{ ...TRUNCATE, color: 'var(--text-muted)', fontSize: '0.82rem' }}
                title={startedFull}
              >
                {startedFull}
              </div>
              <div className="data-table-cell mono" style={TRUNCATE}>
                {job.total > 0 ? `${job.completed}/${job.total}` : '—'}
              </div>
              <div className="data-table-cell" style={{ overflow: 'hidden' }}>
                <span className={STATUS_CLASS[job.status]}>{job.status}</span>
              </div>
              <div className="data-table-cell" style={{ justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  className="btn-ghost"
                  style={{ padding: '6px 14px', fontSize: '0.8rem' }}
                  onClick={() => onSelect(job.job_id)}
                >
                  View
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
