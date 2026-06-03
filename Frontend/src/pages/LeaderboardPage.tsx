// Competition leaderboard: current public standings (rank / team / score / medal),
// with a competition selector, search box, and a "show all" toggle (3000+ rows).
// Reachable per-competition (/competitions/:id/leaderboard) or top-level
// (/leaderboard, competition chosen via the in-page picker).

import { useEffect, useMemo, useState, type CSSProperties, type JSX } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getLeaderboardCurrent } from '@/api/endpoints'
import { useToast } from '@/components/shared/ToastProvider'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { CompetitionPicker } from '@/components/shared/CompetitionPicker'
import { LastSynced } from '@/components/shared/LastSynced'
import { ArrowLeftIcon, MedalIcon, InboxIcon } from '@/components/shared/icons'
import type { LeaderboardRow } from '@/types'

const GRID = '80px minmax(160px, 1fr) 110px 90px'
const DEFAULT_LIMIT = 200

const TRUNCATE: CSSProperties = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }

function medalColor(medal: string | null): string {
  switch ((medal ?? '').toUpperCase()) {
    case 'GOLD':
      return 'var(--accent-amber)'
    case 'SILVER':
      return 'var(--text-muted)'
    case 'BRONZE':
      return 'var(--accent-red)'
    default:
      return 'var(--text-faint)'
  }
}

export function LeaderboardPage(): JSX.Element {
  const { competitionId: routeId } = useParams()
  const navigate = useNavigate()
  const { notify } = useToast()

  // Active competition (kaggle_id). Seeded from the route, else from the picker.
  const [activeId, setActiveId] = useState<number | null>(routeId ? Number(routeId) : null)
  const [rows, setRows] = useState<LeaderboardRow[]>([])
  const [cutoff, setCutoff] = useState(0)
  const [syncedAt, setSyncedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    if (activeId === null) {
      // Waiting for the picker to choose a competition.
      setLoading(false)
      return
    }
    let active = true
    setLoading(true)
    getLeaderboardCurrent(activeId)
      .then((res) => {
        if (!active) return
        setRows(res.entries)
        setCutoff(res.top10_cutoff_rank)
        setSyncedAt(res.last_synced_at ?? null)
      })
      .catch(() => active && notify('error', 'Could not load the leaderboard.'))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [activeId, notify])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const base = q
      ? rows.filter((r) => (r.team_name ?? '').toLowerCase().includes(q))
      : rows
    return showAll ? base : base.slice(0, DEFAULT_LIMIT)
  }, [rows, query, showAll])

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-2 animate-in">
        <button
          type="button"
          className="btn-icon"
          onClick={() => navigate(routeId ? `/competitions/${routeId}/submissions` : '/competitions')}
          aria-label="Back"
        >
          <ArrowLeftIcon size={18} />
        </button>
        <h1
          className="gradient-text"
          style={{ fontSize: 'clamp(1.6rem, 3.5vw, 2.25rem)', fontWeight: 700, marginRight: 'auto' }}
        >
          Leaderboard
        </h1>
        <CompetitionPicker value={activeId} onChange={setActiveId} />
      </div>
      <div className="flex flex-wrap items-center gap-3" style={{ marginBottom: 20 }}>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          {loading
            ? 'Loading current standings…'
            : `${rows.length.toLocaleString()} teams · top 10% = rank ≤ ${cutoff.toLocaleString()}`}
        </p>
        {!loading && <LastSynced at={syncedAt} />}
      </div>

      <input
        className="form-select"
        type="text"
        placeholder="Search teams…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{ maxWidth: 360, marginBottom: 16 }}
      />

      {loading ? (
        <div className="glass-card" style={{ padding: 16 }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} style={{ marginBottom: 10 }}>
              <LoadingSkeleton shape="row" />
            </div>
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="text-center py-16" style={{ color: 'var(--text-muted)' }}>
          <div className="mb-3 flex justify-center" style={{ color: 'var(--text-faint)' }}>
            <InboxIcon size={44} />
          </div>
          <p>No leaderboard data available.</p>
        </div>
      ) : (
        <div className="glass-card overflow-hidden" style={{ overflowX: 'auto' }}>
          <div className="data-table" style={{ minWidth: 520 }}>
            <div style={{ display: 'grid', gridTemplateColumns: GRID }}>
              <div className="data-table-header">Rank</div>
              <div className="data-table-header">Team</div>
              <div className="data-table-header" style={{ display: 'flex', justifyContent: 'flex-end' }}>
                Score
              </div>
              <div className="data-table-header" style={{ display: 'flex', justifyContent: 'flex-end' }}>
                Medal
              </div>
            </div>
            {filtered.map((r) => {
              const isTop = r.rank <= cutoff
              return (
                <div key={r.team_id} className="data-table-rowwrap" style={{ gridTemplateColumns: GRID }}>
                  <div
                    className="data-table-cell mono"
                    style={{ color: isTop ? 'var(--accent-cyan)' : 'var(--text-muted)', fontWeight: isTop ? 600 : 400 }}
                  >
                    #{r.rank}
                  </div>
                  <div className="data-table-cell" style={TRUNCATE} title={r.team_name ?? r.team_id}>
                    {r.team_name ?? r.team_id}
                  </div>
                  <div className="data-table-cell mono" style={{ justifyContent: 'flex-end' }}>
                    {r.score !== null ? r.score.toFixed(1) : '—'}
                  </div>
                  <div className="data-table-cell" style={{ justifyContent: 'flex-end', color: medalColor(r.medal) }}>
                    {r.medal ? <MedalIcon size={16} /> : <span style={{ color: 'var(--text-faint)' }}>—</span>}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {!loading && !showAll && rows.length > DEFAULT_LIMIT && !query && (
        <div className="flex justify-center mt-4">
          <button type="button" className="btn-ghost" onClick={() => setShowAll(true)}>
            Show all {rows.length.toLocaleString()} teams
          </button>
        </div>
      )}
    </div>
  )
}
