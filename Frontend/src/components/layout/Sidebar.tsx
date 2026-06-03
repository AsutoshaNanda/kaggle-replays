// Left navigation sidebar (desktop). Highlights the active section.

import type { JSX, ComponentType } from 'react'
import { NavLink } from 'react-router-dom'
import { ChartIcon, TrophyIcon, TargetIcon, DownloadIcon } from '@/components/shared/icons'

interface SidebarLink {
  to: string
  label: string
  Icon: ComponentType<{ size?: number }>
  end?: boolean
}

const LINKS: SidebarLink[] = [
  { to: '/competitions', label: 'Home', Icon: ChartIcon, end: true },
  { to: '/leaderboard', label: 'Leaderboard', Icon: TrophyIcon },
  { to: '/top-replays', label: 'Top 10% Replays', Icon: TargetIcon },
  { to: '/downloads', label: 'My Downloads', Icon: DownloadIcon },
]

export function Sidebar(): JSX.Element {
  return (
    <aside
      className="hidden lg:block p-4"
      style={{
        width: 220,
        background: 'var(--bg-surface)',
        borderRight: '1px solid var(--border-subtle)',
        minHeight: 'calc(100vh - 56px)',
      }}
    >
      <nav className="flex flex-col gap-1">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className="sidebar-link"
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '10px 12px',
              borderRadius: 8,
              fontSize: '0.88rem',
              fontFamily: 'var(--font-body)',
              fontWeight: isActive ? 600 : 400,
              color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
              background: isActive ? 'var(--bg-raised)' : 'transparent',
              borderLeft: isActive ? '3px solid var(--accent-cyan)' : '3px solid transparent',
              transition: 'background 150ms ease, color 150ms ease',
            })}
          >
            <link.Icon size={18} />
            {link.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
