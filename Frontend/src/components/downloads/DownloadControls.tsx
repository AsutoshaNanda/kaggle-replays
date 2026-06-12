// New-download controls: filter chips, format toggle, episode-count preview, and
// the Start button. Fetches the episode count for the current filter.

import { useEffect, useState, type JSX } from 'react'
import { getEpisodes } from '@/api/endpoints'
import type { EpisodeFilter, FormatMode, Submission } from '@/types'
import { EpisodeFilterChips } from './EpisodeFilterChips'
import { FormatToggle } from './FormatToggle'
import { DownloadIcon } from '@/components/shared/icons'

interface DownloadControlsProps {
  submission: Submission
  onStart: (filter: EpisodeFilter, format: FormatMode) => void
  starting: boolean
}

export function DownloadControls({
  submission,
  onStart,
  starting,
}: DownloadControlsProps): JSX.Element {
  const [filter, setFilter] = useState<EpisodeFilter>('all')
  const [format, setFormat] = useState<FormatMode>('zip')
  const [count, setCount] = useState<number | null>(null)
  const [counting, setCounting] = useState(false)

  useEffect(() => {
    let active = true
    setCounting(true)
    getEpisodes(submission.id, filter)
      .then((res) => active && setCount(res.total))
      .catch(() => active && setCount(null))
      .finally(() => active && setCounting(false))
    return () => {
      active = false
    }
  }, [submission.id, filter])

  return (
    <div className="glass-card" style={{ padding: 24 }}>
      <div className="flex flex-col gap-6">
        <EpisodeFilterChips value={filter} onChange={setFilter} />
        <FormatToggle value={format} onChange={setFormat} />

        <div
          className="mono"
          style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}
        >
          {counting
            ? 'Counting episodes…'
            : count !== null
              ? `~${count.toLocaleString()} episode${count === 1 ? '' : 's'} will be downloaded`
              : 'Episode count unavailable'}
        </div>

        <button
          type="button"
          className="btn-primary-glow btn-lg"
          style={{ width: '100%', height: 52, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
          disabled={starting}
          onClick={() => onStart(filter, format)}
        >
          {starting ? (
            'Starting…'
          ) : (
            <>
              <DownloadIcon size={18} />
              Start Download
            </>
          )}
        </button>
      </div>
    </div>
  )
}
