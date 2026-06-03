// Combined live job-status hook: prefers WebSocket frames, falls back to polling
// GET /downloads/{uuid}/status so the elapsed/remaining estimates stay fresh.

import { useEffect, useState } from 'react'
import { getAccessToken } from '@/api/client'
import { getJobStatus } from '@/api/endpoints'
import type { DownloadJob } from '@/types'
import { useWebSocket } from './useWebSocket'

const TERMINAL = new Set<DownloadJob['status']>(['done', 'failed', 'cancelled'])
const POLL_MS = 3000

export function useDownloadJob(jobId: string | null): DownloadJob | null {
  const token = getAccessToken()
  const wsJob = useWebSocket(jobId, token)
  const [polled, setPolled] = useState<DownloadJob | null>(null)

  useEffect(() => {
    if (!jobId) {
      setPolled(null)
      return
    }
    let active = true
    let timer: number | undefined

    const tick = async (): Promise<void> => {
      try {
        const status = await getJobStatus(jobId)
        if (!active) return
        setPolled(status)
        if (!TERMINAL.has(status.status)) {
          timer = window.setTimeout(() => void tick(), POLL_MS)
        }
      } catch {
        if (active) timer = window.setTimeout(() => void tick(), POLL_MS)
      }
    }
    void tick()

    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [jobId])

  // Merge: WS gives the freshest status/counts; polling supplies elapsed/ETA.
  if (wsJob && polled) {
    return {
      ...polled,
      status: wsJob.status,
      completed: wsJob.completed,
      total: wsJob.total,
      failed_count: wsJob.failed_count,
      pct_complete: wsJob.pct_complete,
    }
  }
  return wsJob ?? polled
}
