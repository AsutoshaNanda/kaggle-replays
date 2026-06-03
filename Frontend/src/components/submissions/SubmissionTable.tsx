// Sortable submissions table (Score / Name / Episodes / Date) with row CTAs.

import { useMemo, useState, type JSX } from 'react'
import type { Submission } from '@/types'
import { SubmissionRow } from './SubmissionRow'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'

interface SubmissionTableProps {
  submissions: Submission[]
  loading: boolean
  onDownload: (submission: Submission) => void
}

type SortKey = 'score' | 'title' | 'episode_count' | 'fetched_at'
type SortDir = 'asc' | 'desc'

// 5 columns: Score | Name | Episodes | Date | Action
const GRID_COLS = '120px 1fr 110px 140px 180px'

export function SubmissionTable({
  submissions,
  loading,
  onDownload,
}: SubmissionTableProps): JSX.Element {
  const [sortKey, setSortKey] = useState<SortKey>('score')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const sorted = useMemo(() => {
    const copy = [...submissions]
    copy.sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      let cmp: number
      if (av === null) cmp = -1
      else if (bv === null) cmp = 1
      else if (typeof av === 'number' && typeof bv === 'number') cmp = av - bv
      else cmp = String(av).localeCompare(String(bv))
      return sortDir === 'asc' ? cmp : -cmp
    })
    return copy
  }, [submissions, sortKey, sortDir])

  const toggleSort = (key: SortKey): void => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const arrow = (key: SortKey): string =>
    key === sortKey ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''

  if (loading) {
    return (
      <div className="glass-card" style={{ padding: 16 }}>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} style={{ marginBottom: 10 }}>
            <LoadingSkeleton shape="row" />
          </div>
        ))}
      </div>
    )
  }

  if (submissions.length === 0) {
    return (
      <div className="text-center py-16" style={{ color: 'var(--text-muted)' }}>
        <p>No submissions found for this competition.</p>
      </div>
    )
  }

  const headers: { key: SortKey; label: string; align?: 'right' }[] = [
    { key: 'score', label: 'Score' },
    { key: 'title', label: 'Name' },
    { key: 'episode_count', label: 'Episodes', align: 'right' },
    { key: 'fetched_at', label: 'Date' },
  ]

  return (
    <div className="glass-card overflow-hidden">
      <div className="data-table">
        {/* Header is its own grid with the SAME columns as each row, so the
            header and body align even though each row is an independent grid
            (which lets rows keep their hover background). */}
        <div style={{ display: 'grid', gridTemplateColumns: GRID_COLS }}>
          {headers.map((h) => (
            <div
              key={h.key}
              role="button"
              tabIndex={0}
              className="data-table-header sortable"
              style={{ justifyContent: h.align === 'right' ? 'flex-end' : 'flex-start' }}
              onClick={() => toggleSort(h.key)}
              onKeyDown={(e) => (e.key === 'Enter' ? toggleSort(h.key) : null)}
            >
              {h.label}
              {arrow(h.key)}
            </div>
          ))}
          <div
            className="data-table-header"
            style={{ display: 'flex', justifyContent: 'flex-end' }}
          >
            Action
          </div>
        </div>

        {sorted.map((s) => (
          <SubmissionRow key={s.id} submission={s} onDownload={onDownload} />
        ))}
      </div>
    </div>
  )
}

export { GRID_COLS as SUBMISSION_GRID_COLS }
