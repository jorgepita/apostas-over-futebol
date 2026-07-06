# Current Status

**Last Updated:** 2026-07-07 (Phase 26.18 — provider API error visibility; "No matches to settle" root cause resolved)

---

## Overall Project Status

**Operational — stable.**

The bot is running in production. Pick generation, settlement, and the dashboard are all functional. The Railway backend is stable. Manual bets, bankroll movements, and bot picks all settle and synchronize correctly via GitHub Actions, on-demand settlement from the dashboard, and cloud recovery on fresh browser sessions.

A recurrence of "No matches to settle." was root-caused to an expired API-Football subscription returning HTTP 200 with empty fixtures instead of a visible error — not a settlement or matching defect. The subscription was renewed (fixing the immediate symptom with no code change), and provider response validation, structured error logging, a distinct dashboard warning, and persistent per-provider health tracking were added so the same failure mode is visible immediately next time, for either provider. See `08_Change_Log.md` — Phase 26.18 for full detail.

The Live Center staleness investigation (LIVE-1) resolved in the previous phase, along with two related defects discovered during that investigation (bankroll movements lost on cloud recovery; a Railway environment misconfiguration), remain stable. See `08_Change_Log.md` — Phase 26.17.

---

## Completed Areas

**Pick generation.** GitHub Actions runs at 17:00 UTC (main) and 23:00 UTC (top-up for non-EU leagues). Poisson model generates O2.5 and BTTS picks across 21 leagues. Picks are committed to GitHub and sent via Telegram.

**Settlement.** Runs at 07:00 and 22:30 UTC via GitHub Actions, and on demand via the dashboard. Bot picks and manual bets share the same `update_dataframe()` engine. football-data.org is the primary source for EU leagues; API-Football is used for blocked EU and all non-EU leagues. Both providers' responses are now validated for embedded errors (plan/quota/auth/network/server) before being trusted, with the result surfaced in the settlement summary, dashboard, logs, and a persistent per-provider health record in `cloud_state.json` (Phase 26.18 — see `04_Backend.md` §7 and ADR-011).

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

No active investigation. The temporary read-only audit harness used to root-cause SETTLEMENT-1 lived outside the repository (scratchpad only) and never touched production code or data — there was no in-repo diagnostic instrumentation to remove for this phase. The codebase otherwise remains clean of the LIVE-1-era temporary instrumentation (`debugger` statements, `[F1]`–`[F6]`, `[BOOT-DIAG]`, `[RECOVERY]`, `[RECOVERY-SCHEMA]`, `[STEP 1]`–`[STEP 5]`). Normal production logging (`[settlement] ...` in `update_results.py`, the new always-on `[API-FOOTBALL]`/`[FOOTBALL-DATA.ORG]` provider-error blocks, `console.error` in `index.html` catch blocks, the feature-flagged `diag_log()` helper) is unchanged or additive.

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
4. Monitor `cloud_state.json["providerHealth"]` after real settlement runs to confirm the "warning" threshold (2 consecutive failing runs) is well-tuned in practice — it has only been validated with synthetic scenarios and one real (successful) production run so far.

---

## Notes

No diagnostic instrumentation remains in the codebase as of Phase 26.18. The provider-error handling added this phase (`ProviderError`, `classify_provider_error()`, `build_provider_error()`, `update_provider_health()`, etc.) is permanent production code, not temporary diagnostics — it is not expected to be removed in a future cleanup pass.
