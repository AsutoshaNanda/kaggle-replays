// Global download-jobs state (Zustand). Tracks the latest live job and which
// submission the user picked to download, so DownloadsPage can react to both.

import { create } from 'zustand'
import type { DownloadJob, Submission } from '@/types'

interface DownloadState {
  // The submission selected for a NEW download (set when navigating from a row).
  selectedSubmission: Submission | null
  setSelectedSubmission: (s: Submission | null) => void

  // The job currently being watched live.
  activeJobId: string | null
  setActiveJobId: (id: string | null) => void

  // Latest progress snapshot per job id (fed by the WS hook).
  jobs: Record<string, DownloadJob>
  upsertJob: (job: DownloadJob) => void
  clearJob: (id: string) => void
}

export const useDownloadStore = create<DownloadState>((set) => ({
  selectedSubmission: null,
  setSelectedSubmission: (s) => set({ selectedSubmission: s }),

  activeJobId: null,
  setActiveJobId: (id) => set({ activeJobId: id }),

  jobs: {},
  upsertJob: (job) =>
    set((state) => ({ jobs: { ...state.jobs, [job.job_id]: job } })),
  clearJob: (id) =>
    set((state) => {
      const next = { ...state.jobs }
      delete next[id]
      return { jobs: next }
    }),
}))
