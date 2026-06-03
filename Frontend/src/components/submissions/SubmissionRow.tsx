// A single submission grid row with a color-coded score badge and download CTA.

import type { JSX } from 'react'
import type { Submission } from '@/types'

interface SubmissionRowProps {
  submission: Submission
  onDownload: (submission: Submission) => void
}

function scoreBadgeClass(score: number | null): string {
  if (score === null) return 'score-badge score-badge-none'
  if (score > 1200) return 'score-badge score-badge-high'
  if (score > 800) return 'score-badge score-badge-mid'
  return 'score-badge score-badge-low'
}

export function SubmissionRow({
  submission,
  onDownload,
}: SubmissionRowProps): JSX.Element {
  const score = submission.score
  const dateText = submission.fetched_at
    ? new Date(submission.fetched_at).toLocaleDateString()
    : '—'

  return (
    <div
      className="data-table-rowwrap"
      style={{ gridTemplateColumns: '120px 1fr 110px 140px 180px' /* must match SUBMISSION_GRID_COLS */ }}
    >
      <div className="data-table-cell">
        <span className={scoreBadgeClass(score)}>
          {score !== null ? score.toFixed(1) : '—'}
        </span>
      </div>
      <div
        className="data-table-cell"
        style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {submission.title}
        </span>
      </div>
      <div
        className="data-table-cell mono"
        style={{ justifyContent: 'flex-end', color: 'var(--text-muted)' }}
        title={submission.episode_count === null ? 'Episode count unavailable (rate limited)' : undefined}
      >
        {submission.episode_count === null ? '—' : submission.episode_count}
      </div>
      <div className="data-table-cell" style={{ color: 'var(--text-muted)' }}>
        {dateText}
      </div>
      <div className="data-table-cell" style={{ justifyContent: 'flex-end' }}>
        <button
          type="button"
          className="btn-ghost"
          style={{ padding: '8px 14px', fontSize: '0.82rem' }}
          onClick={() => onDownload(submission)}
        >
          Download Replays
        </button>
      </div>
    </div>
  )
}

export { scoreBadgeClass }
