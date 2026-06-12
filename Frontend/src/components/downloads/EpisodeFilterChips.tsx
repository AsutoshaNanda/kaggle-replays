// Pill-style radio group: All / Win Only / Lose Only.

import type { JSX } from 'react'
import type { EpisodeFilter } from '@/types'

interface EpisodeFilterChipsProps {
  value: EpisodeFilter
  onChange: (value: EpisodeFilter) => void
}

const OPTIONS: { value: EpisodeFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'win', label: 'Win Only' },
  { value: 'lose', label: 'Lose Only' },
]

export function EpisodeFilterChips({
  value,
  onChange,
}: EpisodeFilterChipsProps): JSX.Element {
  return (
    <div>
      <label
        className="form-label"
        title="Outcome filtering may take longer as episodes need to be analyzed"
      >
        Episode filter
      </label>
      <div className="flex gap-2 flex-wrap" role="group" aria-label="Episode outcome filter">
        {OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            className={`pill ${value === opt.value ? 'pill-active' : ''}`}
            aria-pressed={value === opt.value}
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}
