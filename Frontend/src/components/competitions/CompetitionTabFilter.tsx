// Entered / Completed / All pill filter.

import type { JSX } from 'react'
import type { TabFilter } from '@/types'

interface CompetitionTabFilterProps {
  active: TabFilter
  onChange: (tab: TabFilter) => void
}

const TABS: { value: TabFilter; label: string }[] = [
  { value: 'entered', label: 'Entered' },
  { value: 'completed', label: 'Completed' },
  { value: 'all', label: 'All' },
]

export function CompetitionTabFilter({
  active,
  onChange,
}: CompetitionTabFilterProps): JSX.Element {
  return (
    <div className="flex flex-wrap gap-2 mb-6" role="tablist">
      {TABS.map((tab) => (
        <button
          key={tab.value}
          type="button"
          role="tab"
          aria-selected={active === tab.value}
          className={`pill ${active === tab.value ? 'pill-active' : ''}`}
          onClick={() => onChange(tab.value)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
