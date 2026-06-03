// "Last synced X ago" label. Renders nothing when there is no timestamp.
// Used on Submissions, Leaderboard and Top 10% Replays so the user can see how
// fresh the cached data is (it is NOT auto-refetched — sync is manual/daily).

import type { JSX } from 'react'

function ago(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (secs < 60) return 'just now'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export function LastSynced({ at }: { at: string | null | undefined }): JSX.Element | null {
  if (!at) return null
  const label = ago(at)
  if (!label) return null
  return (
    <span style={{ color: 'var(--text-faint)', fontSize: '0.78rem' }}>
      Last synced {label}
    </span>
  )
}
