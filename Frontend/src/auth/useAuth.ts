// Hook wrapping AuthContext with a null-guard.

import { useContext } from 'react'
import { AuthContext, type AuthContextValue } from './AuthContext'

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (ctx === null) {
    throw new Error('useAuth must be used within an <AuthProvider>')
  }
  return ctx
}
