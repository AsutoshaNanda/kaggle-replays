// WebSocket hook for live download progress, with auto-reconnect
// (max 5 attempts, exponential backoff). Returns the latest DownloadJob or null.

import { useEffect, useRef, useState } from 'react'
import { buildWsUrl } from '@/api/endpoints'
import type { DownloadJob, WsProgressFrame } from '@/types'

const MAX_RECONNECTS = 5
const TERMINAL = new Set<DownloadJob['status']>(['done', 'failed', 'cancelled'])

export function useWebSocket(
  jobId: string | null,
  token: string | null,
): DownloadJob | null {
  const [job, setJob] = useState<DownloadJob | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const attemptsRef = useRef<number>(0)
  const timerRef = useRef<number | null>(null)
  const closedByUs = useRef<boolean>(false)

  useEffect(() => {
    // token is part of the dependency list so the connection is rebuilt if it
    // rotates; we don't otherwise read it here (URL is built in buildWsUrl).
    void token
    if (!jobId) {
      setJob(null)
      return
    }

    closedByUs.current = false
    attemptsRef.current = 0

    const connect = (): void => {
      const url = buildWsUrl(jobId)
      if (!url) return

      const ws = new WebSocket(url)
      socketRef.current = ws

      ws.onmessage = (event: MessageEvent<string>) => {
        try {
          const frame = JSON.parse(event.data) as WsProgressFrame
          const pct =
            frame.total > 0 ? (frame.completed / frame.total) * 100 : frame.pct_complete
          setJob((prev) => ({
            job_id: jobId,
            status: frame.status,
            total: frame.total,
            completed: frame.completed,
            failed_count: frame.failed_count,
            skipped: prev?.skipped ?? 0,
            pct_complete: Math.round(pct * 10) / 10,
            elapsed_seconds: prev?.elapsed_seconds ?? 0,
            estimated_remaining_seconds: prev?.estimated_remaining_seconds ?? null,
          }))
          if (TERMINAL.has(frame.status)) {
            closedByUs.current = true
            ws.close()
          }
        } catch {
          // ignore malformed frames
        }
      }

      ws.onclose = () => {
        if (closedByUs.current) return
        if (attemptsRef.current < MAX_RECONNECTS) {
          const delay = Math.min(1000 * 2 ** attemptsRef.current, 16000)
          attemptsRef.current += 1
          timerRef.current = window.setTimeout(connect, delay)
        }
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      closedByUs.current = true
      if (timerRef.current !== null) window.clearTimeout(timerRef.current)
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [jobId, token])

  return job
}
