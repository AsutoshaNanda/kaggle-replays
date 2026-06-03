# Frontend — Kaggle Replay Analytics Platform

Phase 3: a React + TypeScript single-page app (Vite + Bootstrap 5) for the
platform. Users sign in with Kaggle, browse competitions, pick submissions, and
download replays (single or bulk) with outcome filtering and live progress.

## Stack

- **Vite 5** + **React 18** + **TypeScript 5** (strict mode, zero `any`)
- **Bootstrap 5.3** (CSS + SCSS variable overrides; no Bootstrap JS)
- **React Router 6** · **Axios** · **Zustand** (global state)
- **sass** (dev) to compile the SCSS overrides · **@types/node** (dev) for `vite.config.ts`

## Run

```bash
npm install
cp .env.example .env        # set VITE_API_BASE_URL (default http://localhost:8000)
npm run dev                 # dev server at http://localhost:5173
npm run build               # tsc -b && vite build  -> dist/
npm run typecheck           # tsc --noEmit
```

The backend (Phase 2) must be running and its `ALLOWED_ORIGINS` must include
`http://localhost:5173` (it does by default).

## Layout

```
src/
├── main.tsx                # entry; imports Bootstrap CSS + SCSS overrides
├── App.tsx                 # Router, auth guard, providers
├── types/index.ts          # all shared interfaces (no inline types)
├── api/
│   ├── client.ts           # axios instance; in-memory token; refresh-on-401
│   └── endpoints.ts        # one typed function per backend endpoint
├── auth/                   # AuthContext + useAuth
├── hooks/                  # useWebSocket (auto-reconnect), useDownloadJob (WS+poll)
├── store/downloadStore.ts  # Zustand: selected submission + active job
├── pages/                  # Login, Competitions, Submissions, Downloads
├── components/
│   ├── layout/             # Navbar, Sidebar, PageWrapper
│   ├── competitions/       # CompetitionCard, TabFilter, Grid
│   ├── submissions/        # SubmissionRow, SubmissionTable (sortable)
│   ├── downloads/          # DownloadControls, EpisodeFilterChips, FormatToggle,
│   │                       # DownloadProgressCard, DownloadHistoryTable,
│   │                       # BulkDownloadButton (top-right)
│   └── shared/             # LoadingSkeleton, ToastProvider, ConfirmModal,
│                           # ThemeToggle, ErrorBoundary
└── styles/                 # bootstrap-overrides.scss, global.scss
```

## Security model

- **Access token lives only in module memory** (`api/client.ts`) — never in
  localStorage/sessionStorage. A new tab must re-authenticate (the refresh token
  is an httponly cookie the server sets; JS can't read it).
- No `dangerouslySetInnerHTML`, no `eval`, no dynamic script injection.
- All API calls go through `endpoints.ts`; components never call axios/fetch.
- Dark-mode preference is the only thing in sessionStorage (not security-sensitive).

## Theming

Bootstrap variables are overridden via CSS custom properties in
`bootstrap-overrides.scss`. Dark mode flips them under `[data-theme="dark"]`,
toggled by `ThemeToggle` (sets the attribute on `<html>`). Component styles read
the variables, so no hardcoded colors in JSX.

## Verified

`npm run build` passes (tsc strict + vite, 0 errors). Manual browser checks:
Login renders (light + dark), Competitions grid + tabs render from the live API,
Navbar shows the top-right **Bulk Download All** button, the bulk modal opens
with its ⚠️ warning + summary table + filter/format dropdowns, theme toggle
switches the palette, and there are **no console errors** across navigation.
