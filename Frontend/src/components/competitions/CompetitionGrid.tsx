// Responsive grid of competition cards, with loading + empty states.

import type { JSX } from 'react'
import type { Competition } from '@/types'
import { CompetitionCard } from './CompetitionCard'
import { SkeletonCard } from '@/components/shared/LoadingSkeleton'
import { InboxIcon } from '@/components/shared/icons'

interface CompetitionGridProps {
  competitions: Competition[]
  loading: boolean
}

export function CompetitionGrid({
  competitions,
  loading,
}: CompetitionGridProps): JSX.Element {
  if (loading) {
    return (
      <div className="grid gap-5 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    )
  }

  if (competitions.length === 0) {
    return (
      <div
        className="text-center py-16"
        style={{ color: 'var(--text-muted)' }}
      >
        <div className="mb-3 flex justify-center" style={{ color: 'var(--text-faint)' }}>
          <InboxIcon size={44} />
        </div>
        <p>No competitions found for this filter.</p>
      </div>
    )
  }

  return (
    <div className="grid gap-5 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
      {competitions.map((c, i) => (
        <div
          key={c.id}
          className={`animate-in stagger-${(i % 4) + 1}`}
        >
          <CompetitionCard competition={c} />
        </div>
      ))}
    </div>
  )
}
