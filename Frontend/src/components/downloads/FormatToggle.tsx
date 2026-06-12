// Segmented control: JSON / ZIP / Both.

import type { JSX } from 'react'
import type { FormatMode } from '@/types'

interface FormatToggleProps {
  value: FormatMode
  onChange: (value: FormatMode) => void
}

const OPTIONS: { value: FormatMode; label: string }[] = [
  { value: 'json', label: 'JSON' },
  { value: 'zip', label: 'ZIP' },
  { value: 'both', label: 'Both' },
]

export function FormatToggle({ value, onChange }: FormatToggleProps): JSX.Element {
  return (
    <div>
      <label className="form-label">Format</label>
      <div className="flex gap-2" role="group" aria-label="Download format">
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
