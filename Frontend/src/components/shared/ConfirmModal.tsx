// Generic confirmation modal — glass panel + framer-motion scale+fade entry.

import type { JSX, ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { XIcon } from '@/components/shared/icons'

interface ConfirmModalProps {
  open: boolean
  title: ReactNode
  children: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  confirmDisabled?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmModal({
  open,
  title,
  children,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  confirmDisabled = false,
  onConfirm,
  onCancel,
}: ConfirmModalProps): JSX.Element {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="modal-backdrop"
            onClick={onCancel}
            aria-hidden="true"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          />
          <div className="modal-shell" role="dialog" aria-modal="true">
            <motion.div
              className="modal-panel"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
            >
              <div className="modal-header">
                <h3 style={{ fontSize: '1.05rem' }}>{title}</h3>
                <button
                  type="button"
                  aria-label="Close"
                  onClick={onCancel}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--text-muted)',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    lineHeight: 1,
                  }}
                >
                  <XIcon size={18} />
                </button>
              </div>
              <div className="modal-body">{children}</div>
              <div className="modal-footer">
                <button type="button" className="btn-ghost" onClick={onCancel}>
                  {cancelLabel}
                </button>
                <button
                  type="button"
                  className="btn-primary-glow"
                  onClick={onConfirm}
                  disabled={confirmDisabled}
                >
                  {confirmLabel}
                </button>
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  )
}
