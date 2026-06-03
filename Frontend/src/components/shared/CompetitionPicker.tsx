// Competition dropdown for the standalone /leaderboard and /top-replays pages.
// Fetches the user's competitions once and emits the chosen competition's
// kaggle_id. Auto-selects the first competition when nothing is selected yet.

import { useEffect, useState, type JSX } from 'react'
import { getCompetitions } from '@/api/endpoints'
import type { Competition } from '@/types'

interface CompetitionPickerProps {
  value: number | null // selected kaggle_id
  onChange: (kaggleId: number) => void
}

export function CompetitionPicker({ value, onChange }: CompetitionPickerProps): JSX.Element | null {
  const [comps, setComps] = useState<Competition[]>([])

  useEffect(() => {
    let active = true
    getCompetitions('all')
      .then((res) => {
        if (!active) return
        setComps(res.competitions)
        // Default to the first competition when the page opened without one.
        if (value === null && res.competitions.length > 0) {
          onChange(res.competitions[0].kaggle_id)
        }
      })
      .catch(() => {
        /* The page shows its own empty/error state; the selector stays hidden. */
      })
    return () => {
      active = false
    }
  }, [])

  if (comps.length === 0) return null

  return (
    <select
      className="form-select"
      style={{ maxWidth: 320 }}
      value={value ?? ''}
      onChange={(e) => onChange(Number(e.target.value))}
      aria-label="Select competition"
    >
      {comps.map((c) => (
        <option key={c.kaggle_id} value={c.kaggle_id}>
          {c.title}
        </option>
      ))}
    </select>
  )
}
