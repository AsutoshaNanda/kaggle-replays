// Profile panel: READ-ONLY view of the user's Kaggle-imported details.
// There are intentionally NO editable inputs or save actions — Kaggle is the
// source of truth, so the panel links out to Kaggle for any edits.

import type { JSX } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useAuth } from '@/auth/useAuth'
import { XIcon, UserIcon, ArrowUpRightIcon, LockIcon } from '@/components/shared/icons'

interface ProfileModalProps {
  open: boolean
  onClose: () => void
}

function ReadOnlyField({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <div className="form-label" style={{ marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ color: 'var(--text-primary)', fontSize: '0.95rem' }}>{value}</div>
    </div>
  )
}

export function ProfileModal({ open, onClose }: ProfileModalProps): JSX.Element {
  const { user } = useAuth()
  const accountUrl = user?.kaggle_user
    ? `https://www.kaggle.com/${user.kaggle_user}/account`
    : 'https://www.kaggle.com/account'

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="modal-backdrop"
            onClick={onClose}
            aria-hidden="true"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          />
          <div className="modal-shell" role="dialog" aria-modal="true">
            <motion.div
              className="modal-panel"
              style={{ maxWidth: 440 }}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
            >
              <div className="modal-header">
                <h3 style={{ fontSize: '1.05rem' }}>Profile</h3>
                <button
                  type="button"
                  aria-label="Close"
                  onClick={onClose}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--text-muted)',
                    cursor: 'pointer',
                    display: 'inline-flex',
                  }}
                >
                  <XIcon size={18} />
                </button>
              </div>

              <div className="modal-body">
                <div className="flex items-center gap-4 mb-6">
                  {user?.thumbnail_url ? (
                    <img
                      src={user.thumbnail_url}
                      alt=""
                      width={64}
                      height={64}
                      style={{ borderRadius: '50%', border: '1px solid var(--border-default)' }}
                    />
                  ) : (
                    <div
                      className="flex items-center justify-center"
                      style={{
                        width: 64,
                        height: 64,
                        borderRadius: '50%',
                        background: 'var(--bg-raised)',
                        border: '1px solid var(--border-default)',
                        color: 'var(--text-muted)',
                      }}
                    >
                      <UserIcon size={30} />
                    </div>
                  )}
                  <div style={{ minWidth: 0 }}>
                    <div className="mono" style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                      @{user?.kaggle_user}
                    </div>
                    {user?.tier && (
                      <span className="pill pill-info" style={{ marginTop: 6, textTransform: 'capitalize' }}>
                        {user.tier}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex flex-col gap-4">
                  <ReadOnlyField label="Username" value={user?.kaggle_user ?? '—'} />
                  <ReadOnlyField label="Display name" value={user?.display_name || '—'} />
                  <ReadOnlyField label="Tier" value={user?.tier ?? '—'} />
                  {user?.profile_url && (
                    <a
                      href={`https://www.kaggle.com${user.profile_url}`}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="flex items-center gap-1"
                      style={{ fontSize: '0.85rem', width: 'fit-content' }}
                    >
                      View Kaggle profile
                      <ArrowUpRightIcon size={13} />
                    </a>
                  )}
                </div>

                {/* Non-intrusive read-only notice — Kaggle owns this data. */}
                <div
                  className="flex items-start gap-2"
                  style={{
                    marginTop: 24,
                    padding: '12px 14px',
                    borderRadius: 10,
                    background: 'var(--bg-raised)',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <span aria-hidden="true" style={{ color: 'var(--text-muted)', display: 'inline-flex', marginTop: 1 }}>
                    <LockIcon size={16} />
                  </span>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                    This profile is read-only. To edit your profile, visit Kaggle directly —{' '}
                    <a href={accountUrl} target="_blank" rel="noreferrer noopener">
                      kaggle.com/{user?.kaggle_user ?? 'account'}
                    </a>
                    .
                  </div>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn-primary-glow" onClick={onClose}>
                  Close
                </button>
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  )
}
