// Router + auth guard + providers. ErrorBoundary wraps the Router; ToastProvider
// + AuthProvider supply global context. Protected routes render inside PageWrapper.

import {
  Navigate,
  Route,
  BrowserRouter as Router,
  Routes,
  useLocation,
} from 'react-router-dom'
import type { JSX, ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AuthProvider } from '@/auth/AuthContext'
import { useAuth } from '@/auth/useAuth'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { ToastProvider } from '@/components/shared/ToastProvider'
import { PageWrapper } from '@/components/layout/PageWrapper'
import { LoginPage } from '@/pages/LoginPage'
import { LandingPage } from '@/pages/LandingPage'
import { CompetitionsPage } from '@/pages/CompetitionsPage'
import { SubmissionsPage } from '@/pages/SubmissionsPage'
import { DownloadsPage } from '@/pages/DownloadsPage'
import { LeaderboardPage } from '@/pages/LeaderboardPage'
import { TopReplaysPage } from '@/pages/TopReplaysPage'

function FullScreenSpinner(): JSX.Element {
  return (
    <div
      className="flex items-center justify-center"
      style={{ minHeight: '100vh', background: 'var(--bg-base)' }}
    >
      <div className="spinner" role="status" aria-label="Loading" />
    </div>
  )
}

function RequireAuth({ children }: { children: ReactNode }): JSX.Element {
  const { isAuthenticated, loading } = useAuth()
  if (loading) return <FullScreenSpinner />
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <PageWrapper>{children}</PageWrapper>
}

function PublicOnly({ children }: { children: ReactNode }): JSX.Element {
  const { isAuthenticated, loading } = useAuth()
  if (loading) return <FullScreenSpinner />
  if (isAuthenticated) return <Navigate to="/competitions" replace />
  return <>{children}</>
}

function PublicEntry({ children }: { children: ReactNode }): JSX.Element {
  const { isAuthenticated, loading } = useAuth()
  if (loading) return <FullScreenSpinner />
  if (isAuthenticated) return <Navigate to="/competitions" replace />
  return <>{children}</>
}

function AnimatedRoutes(): JSX.Element {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
      >
        <Routes location={location}>
          <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
          <Route
            path="/competitions"
            element={<RequireAuth><CompetitionsPage /></RequireAuth>}
          />
          <Route
            path="/competitions/:competitionId/submissions"
            element={<RequireAuth><SubmissionsPage /></RequireAuth>}
          />
          <Route
            path="/competitions/:competitionId/leaderboard"
            element={<RequireAuth><LeaderboardPage /></RequireAuth>}
          />
          <Route
            path="/competitions/:competitionId/top-replays"
            element={<RequireAuth><TopReplaysPage /></RequireAuth>}
          />
          {/* Top-level (sidebar) entries — competition chosen via an in-page picker. */}
          <Route
            path="/leaderboard"
            element={<RequireAuth><LeaderboardPage /></RequireAuth>}
          />
          <Route
            path="/top-replays"
            element={<RequireAuth><TopReplaysPage /></RequireAuth>}
          />
          <Route
            path="/downloads"
            element={<RequireAuth><DownloadsPage /></RequireAuth>}
          />
          <Route path="/" element={<PublicEntry><LandingPage /></PublicEntry>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  )
}

export function App(): JSX.Element {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <AuthProvider>
          <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <AnimatedRoutes />
          </Router>
        </AuthProvider>
      </ToastProvider>
    </ErrorBoundary>
  )
}
