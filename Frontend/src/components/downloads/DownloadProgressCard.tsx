// Live progress card for a running/finished job. Animated gradient top bar +
// stat pills + elapsed/ETA. Download (when done) / Cancel.

import type { JSX } from 'react'
import { DownloadIcon, XIcon } from '@/components/shared/icons'
import { downloadJobFile } from '@/api/endpoints'
import { useToast } from '@/components/shared/ToastProvider'
import type { DownloadJob } from '@/types'

interface DownloadProgressCardProps {
  job: DownloadJob
  onCancel: (jobId: string) => void
}

function fmtDuration(seconds: number | null): string {
  if (seconds === null) return '—'
  const s = Math.max(0, Math.round(seconds))
  const m = Math.floor(s / 60)
  const r = s % 60
  return m > 0 ? `${m}m ${r}s` : `${r}s`
}

interface StatPillProps {
  label: string
  value: number | string
  tone?: 'default' | 'success' | 'danger' | 'warning'
}

function StatPill({ label, value, tone = 'default' }: StatPillProps): JSX.Element {
  const color =
    tone === 'success'
      ? 'var(--accent-green)'
      : tone === 'danger'
        ? 'var(--accent-red)'
        : tone === 'warning'
          ? 'var(--accent-amber)'
          : 'var(--text-primary)'
  return (
    <div
      style={{
        flex: 1,
        background: 'var(--bg-raised)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 10,
        padding: '10px 14px',
      }}
    >
      <div
        style={{
          fontSize: '0.65rem',
          color: 'var(--text-faint)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div className="mono" style={{ fontSize: '1.1rem', color, fontWeight: 500 }}>
        {value}
      </div>
    </div>
  )
}

export function DownloadProgressCard({
  job,
  onCancel,
}: DownloadProgressCardProps): JSX.Element {
  const { notify } = useToast()
  const isActive = job.status === 'queued' || job.status === 'running'
  const isDone = job.status === 'done'

  const handleDownload = async (): Promise<void> => {
    try {
      const blob = await downloadJobFile(job.job_id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${job.job_id}.zip`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch {
      notify('error', 'Could not download the ZIP file.')
    }
  }

  return (
    <div className="glass-card overflow-hidden">
      <div className="progress-track" role="progressbar"
           aria-valuenow={job.pct_complete} aria-valuemin={0} aria-valuemax={100}>
        <div
          className="progress-fill"
          style={{
            width: `${Math.max(0, Math.min(100, job.pct_complete))}%`,
            animationPlayState: isActive ? 'running' : 'paused',
          }}
        />
      </div>

      <div style={{ padding: 24 }}>
        <div className="flex justify-between items-center mb-4">
          <h4 className="mono" style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            {job.job_id.slice(0, 8)}…
          </h4>
          <span className="gradient-text" style={{ fontSize: '1.5rem', fontWeight: 600 }}>
            {job.pct_complete.toFixed(1)}%
          </span>
        </div>

        <div className="flex gap-2 mb-4 flex-wrap">
          <StatPill label="Completed" value={`${job.completed}/${job.total}`} tone="success" />
          <StatPill label="Failed" value={job.failed_count} tone="danger" />
          <StatPill label="Skipped" value={job.skipped} tone="warning" />
        </div>

        <div
          className="mono"
          style={{ color: 'var(--text-faint)', fontSize: '0.75rem', marginBottom: 6 }}
        >
          Elapsed: {fmtDuration(job.elapsed_seconds)} · Est. remaining:{' '}
          {fmtDuration(job.estimated_remaining_seconds)}
        </div>

        <div className="flex gap-2 mt-4">
          <button
            type="button"
            className="btn-primary-glow"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            disabled={!isDone}
            onClick={() => void handleDownload()}
          >
            <DownloadIcon size={16} />
            Download ZIP
          </button>
          {isActive && (
            <button
              type="button"
              className="btn-ghost"
              style={{ color: 'var(--accent-red)', borderColor: 'rgba(191,77,58,0.40)', display: 'inline-flex', alignItems: 'center', gap: 6 }}
              onClick={() => onCancel(job.job_id)}
            >
              <XIcon size={15} />
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
