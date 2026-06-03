// Axios instance with auth + error interceptors.
//
// SECURITY: the access token is held ONLY in this module-level variable — never
// in localStorage/sessionStorage. This means a new browser tab starts without a
// token and must re-authenticate (the refresh cookie is httponly, so JS can't
// read it to bootstrap a new tab). That trade-off is intentional per policy.

import axios, {
  AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios'
import type { ToastType } from '@/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// In-memory token store (module scope).
let accessToken: string | null = null
export function setAccessToken(token: string | null): void {
  accessToken = token
}
export function getAccessToken(): string | null {
  return accessToken
}

// Toast + logout hooks are injected by the app so this module stays UI-agnostic.
type ToastFn = (type: ToastType, message: string) => void
let emitToast: ToastFn = () => {}
export function registerToast(fn: ToastFn): void {
  emitToast = fn
}
let onAuthFailure: () => void = () => {}
export function registerAuthFailureHandler(fn: () => void): void {
  onAuthFailure = fn
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  withCredentials: true, // send the httponly refresh cookie on /auth/refresh
  headers: { 'Content-Type': 'application/json' },
})

// Attach bearer token to every request.
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) {
    config.headers.set('Authorization', `Bearer ${accessToken}`)
  }
  return config
})

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

// Response interceptor: refresh-on-401 (once), toast on 429/5xx.
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined
    const status = error.response?.status

    // 401 -> try a single refresh, then replay the original request.
    if (status === 401 && original && !original._retried && !isAuthEndpoint(original.url)) {
      original._retried = true
      try {
        const refreshed = await axios.post<{ access_token: string }>(
          `${BASE_URL}/auth/refresh`,
          {},
          { withCredentials: true },
        )
        setAccessToken(refreshed.data.access_token)
        original.headers.set('Authorization', `Bearer ${refreshed.data.access_token}`)
        return apiClient(original)
      } catch {
        setAccessToken(null)
        onAuthFailure()
        return Promise.reject(error)
      }
    }

    if (status === 429) {
      // Prefer the backend's friendly detail (e.g. the Kaggle rate-limit text);
      // fall back to a generic message. Surface the Retry-After countdown.
      // Auth endpoints (/auth/refresh, /auth/kaggle-login) are background/bootstrap
      // calls — a throttled refresh must fail SILENTLY to logged-out, never toast.
      // (Suppressing this is what removes the "Too many requests" popups on login.)
      if (!isAuthEndpoint(original?.url)) {
        const retryAfter = Number(error.response?.headers['retry-after']) || 0
        const detail =
          (error.response?.data as { detail?: string } | undefined)?.detail ??
          'Too many requests — please wait a moment.'
        const wait = retryAfter > 0 ? ` Try again in ${retryAfter}s.` : ''
        emitToast('warning', `${detail}${wait}`)
      }
    } else if (status && status >= 500) {
      emitToast('error', `Server error (${status}). Please try again.`)
    }

    return Promise.reject(error)
  },
)

function isAuthEndpoint(url?: string): boolean {
  return !!url && (url.includes('/auth/refresh') || url.includes('/auth/kaggle-login'))
}

export { BASE_URL }
