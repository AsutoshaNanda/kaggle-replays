// Competitions page: tab filter + responsive card grid with skeletons.

import { useEffect, useState, type JSX } from 'react'
import { getCompetitions } from '@/api/endpoints'
import { useToast } from '@/components/shared/ToastProvider'
import { CompetitionGrid } from '@/components/competitions/CompetitionGrid'
import { CompetitionTabFilter } from '@/components/competitions/CompetitionTabFilter'
import type { Competition, TabFilter } from '@/types'

export function CompetitionsPage(): JSX.Element {
  const { notify } = useToast()
  const [tab, setTab] = useState<TabFilter>('all')
  const [competitions, setCompetitions] = useState<Competition[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    setLoading(true)
    getCompetitions(tab)
      .then((res) => active && setCompetitions(res.competitions))
      .catch(() => active && notify('error', 'Could not load competitions.'))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [tab, notify])

  return (
    <div>
      <div className="mb-6 animate-in">
        <h1
          className="gradient-text mb-2"
          style={{ fontSize: 'clamp(1.8rem, 4vw, 2.5rem)', fontWeight: 700 }}
        >
          Competitions
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>
          Browse competitions you've entered and explore featured ones.
        </p>
      </div>
      <CompetitionTabFilter active={tab} onChange={setTab} />
      <CompetitionGrid competitions={competitions} loading={loading} />
    </div>
  )
}
