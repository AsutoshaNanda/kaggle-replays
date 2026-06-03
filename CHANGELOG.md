# Changelog

All notable changes to this project will be documented in this file. Format based on [Keep a Changelog](https://keepachangelog.com).

## [Unreleased]

### Added

- Browse competitions you have entered, with active/completed status.
- View submissions per competition, with skill-rating score and episode count.
- List a submission's episodes with a computed outcome (win, loss, or draw).
- Bulk-download replays as JSON or ZIP, optionally filtered by outcome, with live progress over a WebSocket.
- Current public leaderboard view with a top-ten-percent cutoff, search, and a competition selector.
- "Top 10% Replays": daily leaderboard snapshots and the top performers' replay episode IDs.
- Read-only profile panel sourced from the Kaggle session.
- Rate-limit-safe data layer: reads are served from a local cache, refreshed only by a daily scheduler or an explicit sync.
- JWT authentication with rotating refresh tokens and a security layer (rate limiting, CORS allow-list, audit log).

### Changed

- [nothing yet]

### Fixed

- [nothing yet]

### Removed

- [nothing yet]
