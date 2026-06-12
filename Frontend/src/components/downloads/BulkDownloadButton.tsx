// Top-right "Bulk Download All" trigger. Renders only on Competitions or
// Submissions pages. Opens a ConfirmModal with a per-submission summary table,
// filter + format dropdowns, and a warning, then POSTs /downloads/bulk.

import { useEffect, useState, type JSX } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { getSubmissions, startBulkDownload } from '@/api/endpoints'
import { useToast } from '@/components/shared/ToastProvider'
import { ConfirmModal } from '@/components/shared/ConfirmModal'
import { DownloadIcon, AlertIcon } from '@/components/shared/icons'
import type { EpisodeFilter, FormatMode, Submission } from '@/types'

export function BulkDownloadButton(): JSX.Element | null {
  const location = useLocation()
  const navigate = useNavigate()
  const params = useParams()
  const { notify } = useToast()

  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [filter, setFilter] = useState<EpisodeFilter>('all')
  const [format, setFormat] = useState<FormatMode>('zip')

  const onCompetitions = location.pathname === '/competitions'
  const onSubmissions = /^\/competitions\/\d+\/submissions/.test(location.pathname)
  const visible = onCompetitions || onSubmissions
  const competitionId = params.competitionId ? Number(params.competitionId) : null

  useEffect(() => {
    if (!open || competitionId === null) return
    let active = true
    setLoading(true)
    getSubmissions(competitionId)
      .then((res) => active && setSubmissions(res.submissions))
      .catch(() => active && notify('error', 'Could not load submissions for bulk download.'))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [open, competitionId, notify])

  if (!visible) return null

  const totalEpisodes = submissions.reduce((sum, s) => sum + (s.episode_count || 0), 0)

  const handleOpen = (): void => {
    if (competitionId === null) {
      notify('info', 'Open a competition to bulk-download all its submissions.')
      navigate('/competitions')
      return
    }
    setOpen(true)
  }

  const handleConfirm = async (): Promise<void> => {
    if (competitionId === null) return
    setSubmitting(true)
    try {
      const res = await startBulkDownload(competitionId, filter, format)
      notify('success', `Bulk download started (${res.total_submissions} submissions).`)
      setOpen(false)
      navigate('/downloads')
    } catch {
      notify('error', 'Failed to start bulk download.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <button
        type="button"
        className="btn-gradient-outline"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}
        onClick={handleOpen}
      >
        <DownloadIcon size={16} />
        <span className="hidden md:inline">Bulk Download All</span>
      </button>

      <ConfirmModal
        open={open}
        title={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span style={{ display: 'inline-flex', color: 'var(--accent-amber)' }}>
              <AlertIcon size={18} />
            </span>
            Download All Replays
          </span>
        }
        confirmLabel={submitting ? 'Starting…' : 'Start Bulk Download'}
        confirmDisabled={submitting || loading || submissions.length === 0}
        onConfirm={() => void handleConfirm()}
        onCancel={() => setOpen(false)}
      >
        <div className="warning-box">
          You are about to download <strong>ALL replays for ALL submissions</strong> in
          this competition. This may involve hundreds or thousands of episodes and could
          take several minutes.
        </div>

        {loading ? (
          <p style={{ color: 'var(--text-muted)', marginBottom: 16 }}>
            Loading submission summary…
          </p>
        ) : (
          <div
            className="glass-card overflow-hidden"
            style={{ marginBottom: 16 }}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 100px',
              }}
            >
              <div className="data-table-header">Submission</div>
              <div
                className="data-table-header"
                style={{ justifyContent: 'flex-end', display: 'flex' }}
              >
                Episodes
              </div>
              {submissions.map((s) => (
                <div key={s.id} className="data-table-rowwrap" style={{ gridTemplateColumns: '1fr 100px' }}>
                  <div
                    className="data-table-cell"
                    style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      fontSize: '0.85rem',
                    }}
                  >
                    {s.title}
                  </div>
                  <div
                    className="data-table-cell mono"
                    style={{ justifyContent: 'flex-end', color: 'var(--text-muted)' }}
                  >
                    {s.episode_count === null ? '—' : s.episode_count}
                  </div>
                </div>
              ))}
              <div
                className="data-table-cell"
                style={{ fontWeight: 600, borderTop: '1px solid var(--border-default)' }}
              >
                TOTAL
              </div>
              <div
                className="data-table-cell mono"
                style={{
                  justifyContent: 'flex-end',
                  fontWeight: 600,
                  borderTop: '1px solid var(--border-default)',
                  color: 'var(--accent-cyan)',
                }}
              >
                {totalEpisodes.toLocaleString()}
              </div>
            </div>
          </div>
        )}

        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
          <div>
            <label className="form-label">Episode filter</label>
            <select
              className="form-select"
              value={filter}
              onChange={(e) => setFilter(e.target.value as EpisodeFilter)}
            >
              <option value="all">All</option>
              <option value="win">Win Only</option>
              <option value="lose">Lose Only</option>
            </select>
          </div>
          <div>
            <label className="form-label">Format</label>
            <select
              className="form-select"
              value={format}
              onChange={(e) => setFormat(e.target.value as FormatMode)}
            >
              <option value="zip">ZIP</option>
              <option value="json">JSON</option>
              <option value="both">Both</option>
            </select>
          </div>
        </div>
      </ConfirmModal>
    </>
  )
}
