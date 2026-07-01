# Current Status

**Last Updated:** 2026-07-01 (Phase 26.17 — manual bet/bankroll cloud synchronization fixed)

---

## Overall Project Status

**Operational — stable.**

The bot is running in production. Pick generation, settlement, and the dashboard are all functional. The Railway backend is stable. Manual bets, bankroll movements, and bot picks all settle and synchronize correctly via GitHub Actions, on-demand settlement from the dashboard, and cloud recovery on fresh browser sessions.

The Live Center staleness investigation (LIVE-1) that was the active focus as of the previous update is now resolved, along with two related defects discovered during that investigation (bankroll movements lost on cloud recovery; a Railway environment misconfiguration). See `08_Change_Log.md` — Phase 26.17 for full detail.

---

## Completed Areas

**Pick generation.** GitHub Actions runs at 17:00 UTC (main) and 23:00 UTC (top-up for non-EU leagues). Poisson model generates O2.5 and BTTS picks across 21 leagues. Picks are committed to GitHub and sent via Telegram.

**Settlement.** Runs at 07:00 and 22:30 UTC via GitHub Actions, and on demand via the dashboard. Bot picks and manual bets share the same `update_dataframe()` engine. football-data.org is the primary source for EU leagues; API-Football is used for blocked EU and all non-EU leagues.

**Railway backend.** Five endpoints operational (`/`, `/health`, `/load`, `/save`, `/run-settlement`). Stateless, single worker, 300-second timeout. `cloud_state.json` is the persistence bridge between browser and GitHub. `GITHUB_OWNER`/`GITHUB_REPO` environment variables verified correct (see Phase 26.17 in the change log for the misconfiguration that was found and fixed).

**Dashboard.** All pages functional: Daily Picks, Live Center, Pending, Manual Bets, History, Analytics, Bot vs Manual, Bankroll/Settings. Auto-save to cloud with 4-second debounce. Scout workspace with Poisson analysis for manual bet creation. Pending KPI, Pending page, and the "Muitas apostas abertas" alert all read from the same `getPendingRows()` helper and cannot numerically diverge.

**Manual bet and bankroll cloud synchronization.** `cloud_state.json` is the authoritative source for both `manualBets` and `movements` (bankroll deposits/withdrawals). A fresh browser session (e.g. Incognito, a new device, or cleared localStorage) reconstructs the exact same runtime state — bankroll, movements, manual bets, pending/live classification, KPIs, alerts — as a session that already has local data. This was verified end-to-end: a normal window and a fresh Incognito window loading the same cloud state render byte-identical bankroll figures, movement history tables, and dashboard KPIs.

**Synchronization model is event-driven, not polling-based.** The 60-second `setInterval` in `boot()` refreshes only the read-only picks CSVs (`loadData()`), league stats, and pending-alert checks. It never re-fetches `cloud_state.json` and never touches `state.manualBets` or `state.movements`. Manual bets and movements are instead refreshed on four explicit events:
- **Boot** — `_doLoadCloudState()` (fresh/anonymous session) or `_reloadManualBetsFromCloud()` (returning session), gated by the `_bootSyncComplete` guard so only one runs per boot.
- **Settlement** — `runSettlement()` calls `_reloadManualBetsFromCloud()` after a successful on-demand settlement.
- **Load Cloud** — the manual "Load Cloud" button calls `_doLoadCloudState({ fromUser: true })`.
- **Visibility change** — returning to a backgrounded tab triggers `_reloadManualBetsFromCloud()`, covering settlement that ran (e.g. via GitHub Actions) while the tab was not focused.

No periodic polling of `cloud_state.json` exists or is planned; this is a deliberate design choice to avoid one Railway→GitHub API request every 60 seconds per open browser tab (see `01_Architecture.md`, Architectural Rules).

**Telegram notifications.** New picks sent after each generation run with deduplication via `sent_state.json`.

**League registry.** 21 leagues managed via `src/league_registry.py`. All settlement routing derived automatically.

**Documentation.** Complete documentation system established under `docs/`. Includes: project context, architecture decisions (10 ADRs), architecture map, repository navigation guide (`PROJECT_MAP.md`), data flow, dashboard reference, backend reference, known issues, roadmap, change log, development guidelines, and session handover template. `CLAUDE.md` added at repository root as the workflow entry point for new Claude sessions.

---

## Current Development

No active investigation. The codebase is clean of temporary diagnostic instrumentation — all `debugger` statements and `[F1]`–`[F6]` / `[BOOT-DIAG]` / `[RECOVERY]` / `[RECOVERY-SCHEMA]` / `[STEP 1]`–`[STEP 5]` logging added during the LIVE-1 investigation have been removed. Normal production logging (`[settlement] ...` in `update_results.py`, `console.error` in `index.html` catch blocks, the feature-flagged `diag_log()` helper) is unchanged.

---

## Active Investigations

None.

---

## Blockers

None.

---

## Next Priorities

1. Implement ST-3: SHA conflict retry in `sync_server.py`.
2. Implement ST-2: Telegram settlement notifications.
3. Consider refreshing `01_Architecture.md` Section 3 ("Startup Flow") and the "60-second browser interval" architectural rule — both still describe the pre-Phase-26.17 design (no auto-recovery of movements, no event-driven manual-bet refresh) and should be brought in line with the current event-driven model described above.

---

## Notes

No diagnostic instrumentation remains in the codebase as of Phase 26.17.
