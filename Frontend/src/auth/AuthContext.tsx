// Auth state + actions. The access token lives in api/client.ts (module memory);
// this context tracks the derived user/loading state for the UI.

import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  getAccessToken,
  registerAuthFailureHandler,
  setAccessToken,
} from '@/api/client'
import { getMe, kaggleLogin, logout as apiLogout, refreshToken } from '@/api/endpoints'
import type { User } from '@/types'

export interface AuthContextValue {
  user: User | null
  loading: boolean
  isAuthenticated: boolean
  login: () => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  completeLoginWithToken: (token: string) => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

// Coalesce the session bootstrap into ONE shared promise. React.StrictMode
// double-invokes effects in dev, which previously fired two concurrent
// /auth/refresh calls on every load; sharing one promise collapses them into a
// single refresh + getMe (and stops the "Too many requests" double-popup at the
// source — the client interceptor also suppresses auth-endpoint 429 toasts).
let bootstrapPromise: Promise<User | null> | null = null
function bootstrapSession(): Promise<User | null> {
  if (!bootstrapPromise) {
    bootstrapPromise = (async (): Promise<User | null> => {
      try {
        if (!getAccessToken()) {
          const { access_token } = await refreshToken()
          setAccessToken(access_token)
        }
        return await getMe()
      } catch {
        return null
      }
    })()
  }
  return bootstrapPromise
}

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState<boolean>(true)

  const refreshUser = useCallback(async (): Promise<void> => {
    try {
      const me = await getMe()
      setUser(me)
    } catch {
      setUser(null)
    }
  }, [])

  // On mount: try to bootstrap a session via the httponly refresh cookie.
  // Uses the shared, coalesced bootstrap so StrictMode's double-invoke makes at
  // most one /auth/refresh + /auth/me round-trip.
  useEffect(() => {
    let active = true
    bootstrapSession()
      .then((me) => {
        if (active) setUser(me)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  // When a refresh ultimately fails, clear the user.
  useEffect(() => {
    registerAuthFailureHandler(() => setUser(null))
  }, [])

  const login = useCallback(async (): Promise<void> => {
    const { redirect_url } = await kaggleLogin()
    window.location.href = redirect_url
  }, [])

  const logout = useCallback(async (): Promise<void> => {
    try {
      await apiLogout()
    } finally {
      setAccessToken(null)
      setUser(null)
    }
  }, [])

  // Adopt an access token handed back by the dev-login redirect (hash fragment).
  const completeLoginWithToken = useCallback(async (token: string): Promise<void> => {
    setAccessToken(token)
    const me = await getMe()
    setUser(me)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAuthenticated: user !== null,
      login,
      logout,
      refreshUser,
      completeLoginWithToken,
    }),
    [user, loading, login, logout, refreshUser, completeLoginWithToken],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
