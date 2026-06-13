// Drill-down modal for a COMPETITION/DATASET collection item: fetches and lists
// that item's top notebooks and discussions (vote-ordered) so the user can see
// what a saved competition/dataset contains without leaving the app. Individual
// notebooks/discussions still link out to Kaggle.

import { useEffect, useState, type CSSProperties, type JSX } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { getCollectionItemContents } from '@/api/endpoints'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { ArrowUpRightIcon, InboxIcon, MedalIcon, XIcon } from '@/components/shared/icons'
import type { CollectionDrillItem, CollectionItem } from '@/types'

const MEDAL_COLOR: Record<string, string> = {
  gold: '#d4a017',
  silver: '#9ea7b3',
  bronze: '#b08d57',
}

const TRUNCATE: CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

interface CollectionItemDrawerProps {
  open: boolean
  collectionId: number | null
  item: CollectionItem | null
  onClose: () => void
}

export function CollectionItemDrawer({
  open,
  collectionId,
  item,
  onClose,
}: CollectionItemDrawerProps): JSX.Element {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notebooks, setNotebooks] = useState<CollectionDrillItem[]>([])
  const [discussions, setDiscussions] = useState<CollectionDrillItem[]>([])

  useEffect(() => {
    if (!open || collectionId === null || item === null) return
    let active = true
    setLoading(true)
    setError(null)
    setNotebooks([])
    setDiscussions([])
    getCollectionItemContents(collectionId, item.id)
      .then((res) => {
        if (!active) return
        setNotebooks(res.notebooks)
        setDiscussions(res.discussions)
      })
      .catch(() => active && setError('Could not load this item — Kaggle may be rate-limiting. Try again shortly.'))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [open, collectionId, item])

  const kind = item?.document_type === 'DATASET' ? 'dataset' : 'competition'

  return (
    <AnimatePresence>
      {open && item && (
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
              style={{ maxWidth: 720 }}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
            >
              <div className="modal-header">
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-faint)' }}
                  >
                    {kind}
                  </div>
                  <h3 style={{ fontSize: '1.05rem', ...TRUNCATE, maxWidth: 560 }} title={item.title}>
                    {item.title}
                  </h3>
                </div>
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
                    lineHeight: 1,
                  }}
                >
                  <XIcon size={18} />
                </button>
              </div>
              <div className="modal-body">
                {loading ? (
                  <div className="flex flex-col gap-2">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <LoadingSkeleton key={i} shape="row" />
                    ))}
                  </div>
                ) : error ? (
                  <div className="text-center py-8" style={{ color: 'var(--text-muted)' }}>
                    <p style={{ margin: 0 }}>{error}</p>
                  </div>
                ) : (
                  <div className="flex flex-col gap-6">
                    <DrillSection title="Notebooks" items={notebooks} />
                    <DrillSection title="Discussions" items={discussions} />
                    {notebooks.length === 0 && discussions.length === 0 && (
                      <div className="text-center py-6" style={{ color: 'var(--text-muted)' }}>
                        <div className="mb-2 flex justify-center" style={{ color: 'var(--text-faint)' }}>
                          <InboxIcon size={36} />
                        </div>
                        <p style={{ margin: 0 }}>No notebooks or discussions found for this {kind}.</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  )
}

function DrillSection({ title, items }: { title: string; items: CollectionDrillItem[] }): JSX.Element | null {
  if (items.length === 0) return null
  return (
    <section>
      <div
        className="form-label"
        style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}
      >
        {title}
        <span className="pill pill-neutral" style={{ padding: '1px 8px', fontSize: '0.7rem' }}>
          {items.length}
        </span>
      </div>
      <div className="flex flex-col">
        {items.map((it, idx) => (
          <a
            key={`${it.url ?? it.title}-${idx}`}
            href={it.url ? `https://www.kaggle.com${it.url}` : undefined}
            target="_blank"
            rel="noreferrer"
            className="data-table-rowwrap"
            style={{
              gridTemplateColumns: '24px minmax(0, 1fr) auto',
              alignItems: 'center',
              padding: '8px 4px',
              color: 'inherit',
              borderRadius: 8,
            }}
          >
            <span style={{ color: it.medal ? MEDAL_COLOR[it.medal] : 'var(--text-faint)', display: 'inline-flex' }}>
              {it.medal ? <MedalIcon size={15} /> : null}
            </span>
            <span style={{ minWidth: 0 }}>
              <span style={{ ...TRUNCATE, display: 'block' }} title={it.title}>
                {it.title}
              </span>
              {it.author_username && (
                <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>{it.author_username}</span>
              )}
            </span>
            <span className="flex items-center gap-2" style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
              {it.votes !== null && <span className="mono">▲ {it.votes}</span>}
              <ArrowUpRightIcon size={14} />
            </span>
          </a>
        ))}
      </div>
    </section>
  )
}
