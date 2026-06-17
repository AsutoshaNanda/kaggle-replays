// Collections page: pick one of your Kaggle collections, browse its items
// (medal→votes sorted), filter All / Notebooks / Discussions, and start a
// ZIP download job (notebooks via kaggle CLI, discussions as Markdown).

import { useCallback, useEffect, useState, type CSSProperties, type JSX } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getCollectionItems,
  getCollections,
  startCollectionDownload,
  startCollectionItemDownload,
  syncCollectionItems,
  syncCollections,
} from '@/api/endpoints'
import { CollectionItemDrawer } from '@/components/collections/CollectionItemDrawer'
import { ConfirmModal } from '@/components/shared/ConfirmModal'
import { LastSynced } from '@/components/shared/LastSynced'
import { LoadingSkeleton } from '@/components/shared/LoadingSkeleton'
import { DownloadIcon, MedalIcon } from '@/components/shared/icons'
import { useToast } from '@/components/shared/ToastProvider'
import { useDownloadStore } from '@/store/downloadStore'
import type { Collection, CollectionItem, CollectionItemFilter, Medal } from '@/types'

const FILTERS: { value: CollectionItemFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'notebooks', label: 'Notebooks' },
  { value: 'discussions', label: 'Discussions' },
  { value: 'datasets', label: 'Datasets' },
  { value: 'competitions', label: 'Competitions' },
]

const MEDAL_COLOR: Record<string, string> = {
  gold: '#d4a017',
  silver: '#9ea7b3',
  bronze: '#b08d57',
}

const MEDALS: Medal[] = ['gold', 'silver', 'bronze']

// 7 columns: Medal | Type | Title | Author | Votes | Comments | Download
const GRID = '60px 110px minmax(220px, 2fr) minmax(140px, 1fr) 70px 90px 56px'

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
  const [medals, setMedals] = useState<Medal[]>([])

  const [cap, setCap] = useState(50)
  const [modalOpen, setModalOpen] = useState(false)
  const [starting, setStarting] = useState(false)
  // Which single item is currently being queued (its row spinner), by item id.
  const [itemBusy, setItemBusy] = useState<number | null>(null)

  // Drill-down drawer: clicking a COMPETITION/DATASET item shows its notebooks
  // and discussions in-app instead of redirecting to Kaggle.
  const [drillItem, setDrillItem] = useState<CollectionItem | null>(null)

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
    async (
      collection: Collection,
      itemFilter: CollectionItemFilter,
      medalSel: Medal[],
    ): Promise<void> => {
      setLoadingItems(true)
      try {
        const res = await getCollectionItems(collection.id, itemFilter, medalSel)
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
    setMedals([])
    void loadItems(collection, 'all', [])
  }

  const handleFilter = (value: CollectionItemFilter): void => {
    setFilter(value)
    if (selected) void loadItems(selected, value, medals)
  }

  const toggleMedal = (medal: Medal): void => {
    const next = medals.includes(medal)
      ? medals.filter((m) => m !== medal)
      : [...medals, medal]
    setMedals(next)
    if (selected) void loadItems(selected, filter, next)
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
      setMedals([])
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
      const res = await startCollectionDownload(selected.id, filter, cap, medals)
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

  const handleItemDownload = async (item: CollectionItem): Promise<void> => {
    if (!selected) return
    setItemBusy(item.id)
    try {
      // A single COMPETITION/DATASET fans out into its top notebooks + discussions
      // (each a slow Kaggle-CLI pull). A cap of 50 = ~100 sub-items ≈ over an hour,
      // so heavy single-item downloads use a small, fast cap; notebooks/topics
      // ignore the cap entirely.
      const heavy = item.document_type === 'COMPETITION' || item.document_type === 'DATASET'
      const itemCap = heavy ? 10 : cap
      const res = await startCollectionItemDownload(selected.id, item.id, itemCap, medals)
      setActiveJobId(res.job_id)
      notify('success', 'Item download started.')
      navigate('/downloads')
    } catch {
      notify('error', 'Failed to start the item download.')
    } finally {
      setItemBusy(null)
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
            {/* Medal filter — applies to notebooks only. */}
            <div className="flex gap-1" title="Filter notebooks by medal">
              {MEDALS.map((m) => {
                const active = medals.includes(m)
                return (
                  <button
                    key={m}
                    type="button"
                    className="btn-ghost"
                    aria-pressed={active}
                    onClick={() => toggleMedal(m)}
                    style={{
                      padding: '6px 10px',
                      fontSize: '0.8rem',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 5,
                      textTransform: 'capitalize',
                      color: active ? MEDAL_COLOR[m] : 'var(--text-muted)',
                      border: `1px solid ${active ? MEDAL_COLOR[m] : 'var(--border-subtle)'}`,
                      background: active ? 'var(--bg-raised)' : 'transparent',
                    }}
                  >
                    <MedalIcon size={14} />
                    {m}
                  </button>
                )
              })}
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
              <div className="data-table" style={{ minWidth: 820 }}>
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
                  <div
                    className="data-table-header"
                    style={{ display: 'flex', justifyContent: 'center' }}
                  >
                    Get
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
                      {item.document_type === 'COMPETITION' ||
                      item.document_type === 'DATASET' ? (
                        <button
                          type="button"
                          onClick={() => setDrillItem(item)}
                          style={{
                            ...TRUNCATE,
                            background: 'none',
                            border: 'none',
                            padding: 0,
                            cursor: 'pointer',
                            color: 'var(--accent-cyan-hover)',
                            font: 'inherit',
                            textAlign: 'left',
                            width: '100%',
                          }}
                          title={`Show notebooks & discussions for this ${item.document_type.toLowerCase()}`}
                        >
                          {item.title}
                        </button>
                      ) : item.url ? (
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
                    <div className="data-table-cell" style={{ justifyContent: 'center' }}>
                      <button
                        type="button"
                        className="btn-icon"
                        style={{ padding: '6px 8px' }}
                        disabled={itemBusy !== null}
                        onClick={() => void handleItemDownload(item)}
                        title="Download just this item (code + output + log for notebooks)"
                        aria-label={`Download ${item.title}`}
                      >
                        {itemBusy === item.id ? '…' : <DownloadIcon size={15} />}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      <CollectionItemDrawer
        open={drillItem !== null}
        collectionId={selected?.id ?? null}
        item={drillItem}
        onClose={() => setDrillItem(null)}
      />

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
