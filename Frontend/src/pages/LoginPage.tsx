// Split hero (left, mesh gradient) + sign-in card (right). Stacks on mobile.

import { useEffect, useState, type ComponentType, type JSX } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/auth/useAuth'
import { useToast } from '@/components/shared/ToastProvider'
import { BoltIcon, ChartIcon, DownloadIcon, TrophyIcon } from '@/components/shared/icons'

export function LoginPage(): JSX.Element {
  const { login, completeLoginWithToken } = useAuth()
  const { notify } = useToast()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const hash = window.location.hash
    const match = hash.match(/access_token=([^&]+)/)
    if (!match) return
    const token = decodeURIComponent(match[1])
    window.history.replaceState(null, '', window.location.pathname)
    completeLoginWithToken(token)
      .then(() => navigate('/competitions', { replace: true }))
      .catch(() => notify('error', 'Login could not be completed.'))
  }, [completeLoginWithToken, navigate, notify])

  // Surface a friendly error passed back by the backend dev-login redirect
  // (e.g. when no Kaggle session / auth.json exists), then clear it from the URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const err = params.get('error')
    if (!err) return
    notify('error', err)
    window.history.replaceState(null, '', window.location.pathname)
  }, [notify])

  const handleConnect = async (): Promise<void> => {
    setBusy(true)
    try {
      await login()
    } catch {
      notify('error', 'Could not start the Kaggle login flow.')
      setBusy(false)
    }
  }

  return (
    <div
      className="flex flex-col md:flex-row"
      style={{ minHeight: '100vh', background: 'var(--bg-base)' }}
    >
      {/* Hero — width handled by the .login-hero class (see global.css):
          full width while stacked on mobile, 55% side-by-side on md+. */}
      <div className="login-hero mesh-bg-animated relative flex items-center p-8 md:p-16">
        {/* SVG noise overlay at 3% */}
        <svg
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            opacity: 0.03,
            pointerEvents: 'none',
            mixBlendMode: 'overlay',
          }}
        >
          <filter id="noise">
            <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch" />
            <feColorMatrix type="saturate" values="0" />
          </filter>
          <rect width="100%" height="100%" filter="url(#noise)" />
        </svg>

        <div className="relative z-10 animate-in" style={{ maxWidth: 560 }}>
          <h1
            className="gradient-text mb-4"
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'clamp(2.5rem, 6vw, 4.5rem)',
              fontWeight: 700,
              lineHeight: 1.05,
              letterSpacing: '-0.03em',
            }}
          >
            Replay Analytics
          </h1>
          <p
            className="mb-8"
            style={{
              color: 'var(--text-primary)',
              opacity: 0.85,
              fontSize: '1.15rem',
              maxWidth: 480,
            }}
          >
            Download and analyze your Kaggle competition replays — at scale.
          </p>
          <div className="flex flex-wrap gap-2">
            <FeaturePill Icon={ChartIcon} label="Browse competitions" />
            <FeaturePill Icon={DownloadIcon} label="Bulk download" />
            <FeaturePill Icon={TrophyIcon} label="Filter by outcome" />
          </div>
        </div>
      </div>

      {/* Sign-in card */}
      <div
        className="flex items-center justify-center p-6 md:p-12"
        style={{ flex: 1, background: 'var(--bg-base)' }}
      >
        <div
          className="glass-card animate-in stagger-2"
          style={{ width: '100%', maxWidth: 420, padding: '40px 32px' }}
        >
          <div
            className="mb-8 flex items-center gap-2"
            style={{ fontFamily: 'var(--font-mono)', fontSize: '1.05rem' }}
          >
            <span aria-hidden="true" style={{ color: 'var(--accent-cyan)', display: 'inline-flex' }}>
              <BoltIcon size={22} />
            </span>
            <span style={{ color: 'var(--text-primary)', letterSpacing: '0.02em' }}>kaggle</span>
          </div>
          <h2 className="mb-2" style={{ fontSize: '1.5rem' }}>
            Sign in
          </h2>
          <p
            className="mb-6"
            style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}
          >
            Continue with your Kaggle account
          </p>
          <button
            type="button"
            className="btn-primary-glow btn-lg"
            style={{ width: '100%' }}
            disabled={busy}
            onClick={() => void handleConnect()}
          >
            {busy ? 'Connecting…' : 'Connect Kaggle Account'}
          </button>
          <p
            className="mt-6"
            style={{ color: 'var(--text-faint)', fontSize: '0.78rem', lineHeight: 1.5 }}
          >
            Your Kaggle credentials are used only for authentication. We never store
            passwords.
          </p>
        </div>
      </div>
    </div>
  )
}

function FeaturePill({
  Icon,
  label,
}: {
  Icon: ComponentType<{ size?: number }>
  label: string
}): JSX.Element {
  return (
    <div
      className="glass-card"
      style={{
        padding: '8px 14px',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        fontSize: '0.85rem',
        borderRadius: 999,
      }}
    >
      <span aria-hidden="true" style={{ display: 'inline-flex', color: 'var(--accent-cyan)' }}>
        <Icon size={16} />
      </span>
      <span style={{ color: 'var(--text-primary)' }}>{label}</span>
    </div>
  )
}
