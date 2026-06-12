// Collections page: pick one of your Kaggle collections, browse its items
// (medal→votes sorted), filter All / Notebooks / Discussions, and start a
// ZIP download job (notebooks via kaggle CLI, discussions as Markdown).

import { useCallback, useEffect, useState, type CSSProperties, type JSX } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getCollectionItems,
  getCollections,
  startCollectionDownload,
  syncCollectionItems,
  syncCollections,
} from '@/api/endpoints'
import { ConfirmModal } from '@/components/shared/ConfirmModal'
import { LastSynced } from '@/components/shared/LastSynced'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { MedalIcon } from '@/components/shared/icons'
import { useToast } from '@/components/shared/ToastProvider'
import { useDownloadStore } from '@/store/downloadStore'
import type { Collection, CollectionItem, CollectionItemFilter } from '@/types'

const FILTERS: { value: CollectionItemFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'notebooks', label: 'Notebooks' },
  { value: 'discussions', label: 'Discussions' },
]

const MEDAL_COLOR: Record<string, string> = {
  gold: '#d4a017',
  silver: '#9ea7b3',
  bronze: '#b08d57',
}

// 6 columns: Medal | Type | Title | Author | Votes | Comments
const GRID = '60px 110px minmax(220px, 2fr) minmax(140px, 1fr) 70px 90px'

const TRUNCATE: CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

// "COMPETITIONS_GRANDMASTER" → "Grandmaster"
function tierLabel(tier: string | null): string {
  if (!tier) return ''
  const last = tier.split('_').pop() ?? tier
  return last.charAt(0) + last.slice(1).toLowerCase()
}

export function CollectionsPage(): JSX.Element {
  const { notify } = useToast()
  const navigate = useNavigate()
  const setActiveJobId = useDownloadStore((s) => s.setActiveJobId)

  const [collections, setCollections] = useState<Collection[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)

  const [selected, setSelected] = useState<Collection | null>(null)
  const [items, setItems] = useState<CollectionItem[]>([])
  const [itemsSyncedAt, setItemsSyncedAt] = useState<string | null>(null)
  const [loadingItems, setLoadingItems] = useState(false)
  const [syncingItems, setSyncingItems] = useState(false)
  const [filter, setFilter] = useState<CollectionItemFilter>('all')

  const [cap, setCap] = useState(50)
  const [modalOpen, setModalOpen] = useState(false)
  const [starting, setStarting] = useState(false)

  const loadCollections = useCallback(async (): Promise<void> => {
    setLoading(true)
    setLoadError(null)
    try {
      const res = await getCollections()
      setCollections(res.collections)
    } catch {
      setLoadError('Could not load collections.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadCollections()
  }, [loadCollections])

  const loadItems = useCallback(
    async (collection: Collection, itemFilter: CollectionItemFilter): Promise<void> => {
      setLoadingItems(true)
      try {
        const res = await getCollectionItems(collection.id, itemFilter)
        setItems(res.items)
        setItemsSyncedAt(res.last_synced_at ?? null)
      } catch {
        notify('error', 'Could not load collection items.')
      } finally {
        setLoadingItems(false)
      }
    },
    [notify],
  )

  const handleSelect = (collection: Collection): void => {
    setSelected(collection)
    setFilter('all')
    void loadItems(collection, 'all')
  }

  const handleFilter = (value: CollectionItemFilter): void => {
    setFilter(value)
    if (selected) void loadItems(selected, value)
  }

  const handleSyncCollections = async (): Promise<void> => {
    setSyncing(true)
    try {
      const res = await syncCollections()
      setCollections(res.collections)
      notify('success', 'Collections synced from Kaggle.')
    } catch {
      notify('error', 'Sync failed — check your Kaggle session.')
    } finally {
      setSyncing(false)
    }
  }

  const handleSyncItems = async (): Promise<void> => {
    if (!selected) return
    setSyncingItems(true)
    try {
      const res = await syncCollectionItems(selected.id)
      setFilter('all')
      setItems(res.items)
      setItemsSyncedAt(res.last_synced_at ?? null)
      notify('success', `Synced ${res.total} items.`)
    } catch {
      notify('error', 'Item sync failed — check your Kaggle session.')
    } finally {
      setSyncingItems(false)
    }
  }

  const handleDownload = async (): Promise<void> => {
    if (!selected) return
    setStarting(true)
    try {
      const res = await startCollectionDownload(selected.id, filter, cap)
      setActiveJobId(res.job_id)
      notify('success', `Download started (${res.total_items} items).`)
      setModalOpen(false)
      navigate('/downloads')
    } catch {
      notify('error', 'Failed to start the collection download.')
    } finally {
      setStarting(false)
    }
  }

  const hasCompetitions = items.some((i) => i.document_type === 'COMPETITION')

  return (
    <div className="flex flex-col gap-8">
      <div className="animate-in">
        <h1
          className="gradient-text mb-2"
          style={{ fontSize: 'clamp(1.8rem, 4vw, 2.5rem)', fontWeight: 700 }}
        >
          Collections
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>
          Browse your saved Kaggle collections and download notebooks and discussions.
        </p>
      </div>

      <section className="animate-in stagger-1">
        <div className="flex items-center gap-3 mb-4" style={{ flexWrap: 'wrap' }}>
          <h2 style={{ fontSize: '1.25rem', margin: 0 }}>Your Collections</h2>
          <button
            type="button"
            className="btn-ghost"
            style={{ padding: '6px 14px', fontSize: '0.8rem' }}
            disabled={syncing}
            onClick={() => void handleSyncCollections()}
          >
            {syncing ? 'Syncing…' : 'Sync from Kaggle'}
          </button>
        </div>

        {loading ? (
          <LoadingSkeleton shape="row" />
        ) : loadError ? (
          <div
            className="glass-card flex flex-col items-center gap-3 text-center"
            style={{ padding: 32, color: 'var(--text-muted)' }}
          >
            <p style={{ margin: 0 }}>{loadError}</p>
            <button type="button" className="btn-ghost" onClick={() => void loadCollections()}>
              Retry
            </button>
          </div>
        ) : collections.length === 0 ? (
          <div className="text-center py-10" style={{ color: 'var(--text-muted)' }}>
            <p>No collections yet — press “Sync from Kaggle”.</p>
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
              gap: 12,
            }}
          >
            {collections.map((collection) => {
              const active = selected?.id === collection.id
              return (
                <button
                  key={collection.id}
                  type="button"
                  className="glass-card"
                  onClick={() => handleSelect(collection)}
                  style={{
                    padding: 16,
                    textAlign: 'left',
                    cursor: 'pointer',
                    border: active
                      ? '1px solid var(--accent-cyan)'
                      : '1px solid var(--border-subtle)',
                  }}
                >
                  <div style={{ ...TRUNCATE, fontWeight: 600 }} title={collection.name}>
                    {collection.name}
                  </div>
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: 4 }}>
                    {collection.item_count} saved item{collection.item_count === 1 ? '' : 's'}
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </section>

      {selected && (
        <section className="animate-in stagger-2">
          <div className="flex items-center gap-3 mb-4" style={{ flexWrap: 'wrap' }}>
            <h2 style={{ fontSize: '1.15rem', margin: 0, ...TRUNCATE, maxWidth: 320 }}>
              {selected.name}
            </h2>
            <div className="flex gap-1">
              {FILTERS.map((f) => (
                <button
                  key={f.value}
                  type="button"
                  className={filter === f.value ? 'btn-primary-glow' : 'btn-ghost'}
                  style={{ padding: '6px 14px', fontSize: '0.8rem' }}
                  onClick={() => handleFilter(f.value)}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="btn-ghost"
              style={{ padding: '6px 14px', fontSize: '0.8rem' }}
              disabled={syncingItems}
              onClick={() => void handleSyncItems()}
            >
              {syncingItems ? 'Syncing…' : 'Sync items'}
            </button>
            <button
              type="button"
              className="btn-primary-glow"
              style={{ padding: '6px 16px', fontSize: '0.8rem' }}
              disabled={items.length === 0 || starting}
              onClick={() => setModalOpen(true)}
            >
              Download ({items.length})
            </button>
            <LastSynced at={itemsSyncedAt} />
          </div>

          {loadingItems ? (
            <div className="glass-card" style={{ padding: 16 }}>
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} style={{ marginBottom: 10 }}>
                  <LoadingSkeleton shape="row" />
                </div>
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-10" style={{ color: 'var(--text-muted)' }}>
              <p>No items cached — press “Sync items”.</p>
            </div>
          ) : (
            <div className="glass-card overflow-hidden" style={{ overflowX: 'auto' }}>
              <div className="data-table" style={{ minWidth: 760 }}>
                <div style={{ display: 'grid', gridTemplateColumns: GRID }}>
                  <div className="data-table-header">Medal</div>
                  <div className="data-table-header">Type</div>
                  <div className="data-table-header">Title</div>
                  <div className="data-table-header">Author</div>
                  <div
                    className="data-table-header"
                    style={{ display: 'flex', justifyContent: 'flex-end' }}
                  >
                    Votes
                  </div>
                  <div
                    className="data-table-header"
                    style={{ display: 'flex', justifyContent: 'flex-end' }}
                  >
                    Comments
                  </div>
                </div>
                {items.map((item) => (
                  <div
                    key={item.id}
                    className="data-table-rowwrap"
                    style={{ gridTemplateColumns: GRID }}
                  >
                    <div className="data-table-cell">
                      {item.medal ? (
                        <span style={{ color: MEDAL_COLOR[item.medal] }} title={item.medal}>
                          <MedalIcon size={16} />
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-faint)' }}>—</span>
                      )}
                    </div>
                    <div
                      className="data-table-cell"
                      style={{ ...TRUNCATE, color: 'var(--text-muted)', fontSize: '0.8rem' }}
                    >
                      {item.document_type}
                    </div>
                    <div className="data-table-cell" style={TRUNCATE} title={item.title}>
                      {item.url ? (
                        <a
                          href={`https://www.kaggle.com${item.url}`}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: 'inherit' }}
                        >
                          {item.title}
                        </a>
                      ) : (
                        item.title
                      )}
                    </div>
                    <div
                      className="data-table-cell"
                      style={{ ...TRUNCATE, color: 'var(--text-muted)', fontSize: '0.82rem' }}
                      title={item.author_username ?? undefined}
                    >
                      {item.author_username ?? '—'}
                      {item.author_tier ? ` (${tierLabel(item.author_tier)})` : ''}
                    </div>
                    <div
                      className="data-table-cell mono"
                      style={{ ...TRUNCATE, justifyContent: 'flex-end' }}
                    >
                      {item.votes}
                    </div>
                    <div
                      className="data-table-cell mono"
                      style={{ ...TRUNCATE, justifyContent: 'flex-end', color: 'var(--text-muted)' }}
                    >
                      {item.total_comments}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      <ConfirmModal
        open={modalOpen}
        title="Download collection"
        confirmLabel={starting ? 'Starting…' : 'Start download'}
        confirmDisabled={starting}
        onConfirm={() => void handleDownload()}
        onCancel={() => setModalOpen(false)}
      >
        <p style={{ marginTop: 0 }}>
          Download <strong>{items.length}</strong>{' '}
          {filter === 'all' ? 'items' : filter} from{' '}
          <strong>{selected?.name}</strong> as a ZIP?
        </p>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          Notebooks are pulled with the Kaggle CLI; discussions are saved as Markdown.
        </p>
        {filter === 'all' && hasCompetitions && (
          <label
            className="flex items-center gap-2"
            style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}
          >
            Top items per competition
            <input
              type="number"
              min={0}
              max={1000}
              value={cap}
              onChange={(e) => setCap(Math.max(0, Math.min(1000, Number(e.target.value) || 0)))}
              style={{
                width: 90,
                padding: '6px 8px',
                borderRadius: 6,
                border: '1px solid var(--border-subtle)',
                background: 'var(--bg-raised)',
                color: 'var(--text-primary)',
              }}
            />
            (0 = no cap)
          </label>
        )}
      </ConfirmModal>
    </div>
  )
}
