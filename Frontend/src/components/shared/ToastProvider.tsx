// Global toast notifications (bottom-right). Stacks up to 3, auto-dismiss after 5s.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type JSX,
  type ReactNode,
} from 'react'
import type { ComponentType } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { registerToast } from '@/api/client'
import type { Toast, ToastType } from '@/types'
import { CheckIcon, XIcon, AlertIcon, BoltIcon } from '@/components/shared/icons'

interface ToastContextValue {
  notify: (type: ToastType, message: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)
const MAX_TOASTS = 3
const AUTO_DISMISS_MS = 5000

const VARIANT: Record<ToastType, string> = {
  success: 'toast-success',
  error: 'toast-error',
  warning: 'toast-warning',
  info: 'toast-info',
}

const ICON: Record<ToastType, ComponentType<{ size?: number }>> = {
  success: CheckIcon,
  error: XIcon,
  warning: AlertIcon,
  info: BoltIcon,
}

export function ToastProvider({ children }: { children: ReactNode }): JSX.Element {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef<number>(1)

  const dismiss = useCallback((id: number): void => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const notify = useCallback(
    (type: ToastType, message: string): void => {
      const id = nextId.current++
      setToasts((prev) => [...prev.slice(-(MAX_TOASTS - 1)), { id, type, message }])
      window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS)
    },
    [dismiss],
  )

  useEffect(() => {
    registerToast((type, message) => notify(type, message))
  }, [notify])

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-atomic="true">
        <AnimatePresence>
          {toasts.map((t) => {
            const Icon = ICON[t.type]
            return (
            <motion.div
              key={t.id}
              role="alert"
              className={`toast-card ${VARIANT[t.type]}`}
              initial={{ opacity: 0, x: 60 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 60 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              layout
            >
              <span
                aria-hidden="true"
                style={{
                  display: 'inline-flex',
                  color:
                    t.type === 'success'
                      ? 'var(--accent-green)'
                      : t.type === 'error'
                        ? 'var(--accent-red)'
                        : t.type === 'warning'
                          ? 'var(--accent-amber)'
                          : 'var(--accent-cyan)',
                }}
              >
                <Icon size={18} />
              </span>
              <div style={{ flex: 1 }}>{t.message}</div>
              <button
                type="button"
                className="toast-close"
                aria-label="Close"
                onClick={() => dismiss(t.id)}
              >
                <XIcon size={15} />
              </button>
            </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (ctx === null) throw new Error('useToast must be used within <ToastProvider>')
  return ctx
}
