// Fixed top navbar — translucent blurred bar, gradient avatar, glass dropdown.

import { useEffect, useRef, useState, type JSX } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/auth/useAuth'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import { BulkDownloadButton } from '@/components/downloads/BulkDownloadButton'
import { ProfileModal } from '@/components/profile/ProfileModal'

export function Navbar(): JSX.Element {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)

  const initial = user?.kaggle_user?.[0]?.toUpperCase() ?? '?'

  useEffect(() => {
    function onDocClick(e: MouseEvent): void {
      if (!menuRef.current) return
      if (!menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  const handleLogout = async (): Promise<void> => {
    setMenuOpen(false)
    await logout()
    navigate('/login')
  }

  return (
    <nav
      className="fixed top-0 left-0 right-0 flex items-center px-4 md:px-6"
      style={{
        height: 56,
        background: 'var(--nav-bg)',
        backdropFilter: 'blur(20px)',
        borderBottom: '1px solid var(--border-subtle)',
        zIndex: 100,
      }}
    >
      <Link
        to="/competitions"
        className="flex items-center gap-2"
        style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '1rem' }}
      >
        <img src="/logo.svg" width={24} height={24} alt="" style={{ display: 'block' }} />
        <span style={{ color: 'var(--text-primary)' }}>Replay Analytics</span>
      </Link>

      <div
        className="hidden md:block mx-6"
        style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}
      >
        <Breadcrumb pathname={location.pathname} />
      </div>

      <div className="flex items-center gap-2 ml-auto">
        <BulkDownloadButton />
        <ThemeToggle />

        <div className="relative" ref={menuRef}>
          <button
            type="button"
            className="avatar-gradient"
            onClick={() => setMenuOpen((o) => !o)}
            aria-haspopup="true"
            aria-expanded={menuOpen}
            aria-label="Account menu"
            style={user?.thumbnail_url ? { padding: 0, overflow: 'hidden' } : undefined}
          >
            {user?.thumbnail_url ? (
              <img src={user.thumbnail_url} alt="" width={32} height={32} style={{ borderRadius: '50%' }} />
            ) : (
              initial
            )}
          </button>
          {menuOpen && (
            <div
              className="glass-card"
              style={{
                position: 'absolute',
                right: 0,
                top: 'calc(100% + 8px)',
                minWidth: 200,
                padding: 6,
                zIndex: 110,
              }}
            >
              <DropdownItem
                onClick={() => {
                  setMenuOpen(false)
                  setProfileOpen(true)
                }}
              >
                Profile
              </DropdownItem>
              <DropdownItem
                onClick={() => {
                  setMenuOpen(false)
                  navigate('/downloads')
                }}
              >
                My Downloads
              </DropdownItem>
              <div
                style={{
                  height: 1,
                  background: 'var(--border-subtle)',
                  margin: '4px 0',
                }}
              />
              <DropdownItem onClick={() => void handleLogout()}>Sign Out</DropdownItem>
            </div>
          )}
        </div>
      </div>

      <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
    </nav>
  )
}

function DropdownItem({
  children,
  onClick,
}: {
  children: React.ReactNode
  onClick: () => void
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'block',
        width: '100%',
        textAlign: 'left',
        padding: '8px 12px',
        background: 'transparent',
        border: 'none',
        color: 'var(--text-primary)',
        fontSize: '0.88rem',
        borderRadius: 8,
        cursor: 'pointer',
        fontFamily: 'var(--font-body)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'var(--bg-raised)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'transparent'
      }}
    >
      {children}
    </button>
  )
}

function Breadcrumb({ pathname }: { pathname: string }): JSX.Element {
  const parts: string[] = []
  if (pathname.startsWith('/competitions')) parts.push('Competitions')
  if (/\/competitions\/\d+\/submissions/.test(pathname)) parts.push('Submissions')
  if (pathname.startsWith('/downloads')) parts.push('Downloads')
  if (parts.length === 0) parts.push('Home')
  return <span>{parts.join(' › ')}</span>
}
