// A single competition card with status badge, clamped title, slug, and actions.

import type { JSX } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Competition } from '@/types'
import { ArrowRightIcon, TrophyIcon } from '@/components/shared/icons'

interface CompetitionCardProps {
  competition: Competition
}

function badge(competition: Competition): { label: string; cls: string } {
  if (competition.status === 'completed') return { label: 'Completed', cls: 'pill pill-neutral' }
  if (competition.is_simulation) return { label: 'Simulation', cls: 'pill pill-info' }
  return { label: 'Active', cls: 'pill pill-success' }
}

export function CompetitionCard({ competition }: CompetitionCardProps): JSX.Element {
  const navigate = useNavigate()
  const { label, cls } = badge(competition)

  return (
    <div className="glass-card glass-card-hover flex flex-col h-full overflow-hidden">
      <div className="gradient-line" />
      <div className="p-5 flex flex-col flex-1">
        <div className="mb-3">
          <span className={cls}>{label}</span>
        </div>
        <h3
          className="clamp-2 mb-1"
          style={{ fontSize: '1.125rem', fontWeight: 600, lineHeight: 1.3 }}
        >
          {competition.title}
        </h3>
        <div
          className="mono mb-4"
          style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}
        >
          {competition.slug}
        </div>
        <div className="mt-auto flex items-center justify-between gap-2">
          <button
            type="button"
            className="btn-ghost"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.82rem', padding: '8px 12px' }}
            onClick={() => navigate(`/competitions/${competition.kaggle_id}/leaderboard`)}
          >
            <TrophyIcon size={15} />
            Leaderboard
          </button>
          <button
            type="button"
            className="btn-primary-glow"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.82rem', padding: '8px 14px' }}
            onClick={() => navigate(`/competitions/${competition.kaggle_id}/submissions`)}
          >
            Submissions
            <ArrowRightIcon size={15} />
          </button>
        </div>
      </div>
    </div>
  )
}
