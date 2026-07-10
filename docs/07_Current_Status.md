# Current Status

**Last Updated:** 2026-07-10 (Phase 26.19 — Manual Bet lifecycle rework: Scout duplicate prevention, rejected bets preserved as analytical records, lifecycle/settlement decoupling)

---

## Overall Project Status

**Operational — stable.**

The bot is running in production. Pick generation, settlement, and the dashboard are all functional. The Railway backend is stable. Manual bets, bankroll movements, and bot picks all settle and synchronize correctly via GitHub Actions, on-demand settlement from the dashboard, and cloud recovery on fresh browser sessions.

This phase reworked the Manual Bet lifecycle end-to-end: the Scout workspace no longer lets a user accidentally create a duplicate bet while the first is still pending; the backend independently refuses duplicate fixture+market bets in `POST /save`; rejecting a bet no longer deletes it (it becomes a permanent, settleable, analytical record instead); a bet's lifecycle status (`pending`/`approved`/`rejected`/`settled`) is now fully independent from its settlement result (`resultado`/`placar`); and the History page gained a "Rejeitadas" view for reviewing rejected bets without them ever touching bankroll/ROI. See `08_Change_Log.md` — Phase 26.19 and ADR-012/ADR-013 for full detail.

The provider API error visibility work (Phase 26.18) and the Live Center/sync fixes (Phase 26.17) remain stable — no changes to that code path this phase.

---

## Completed Areas

**Pick generation.** GitHub Actions runs at 17:00 UTC (main) and 23:00 UTC (top-up for non-EU leagues). Poisson model generates O2.5 and BTTS picks across 21 leagues. Picks are committed to GitHub and sent via Telegram.

**Settlement.** Runs at 07:00 and 22:30 UTC via GitHub Actions, and on demand via the dashboard. Bot picks and manual bets share the same `update_dataframe()` engine, including rejected manual bets — the engine does not filter by lifecycle status (Phase 26.19; see ADR-012). Both write sites now also capture the final score (`Placar`, e.g. `"2-1"`) alongside `Resultado`/`Lucro€`, for both bot picks and manual bets. football-data.org is the primary source for EU leagues; API-Football is used for blocked EU and all non-EU leagues. Both providers' responses are validated for embedded errors (plan/quota/auth/network/server) before being trusted, with the result surfaced in the settlement summary, dashboard, logs, and a persistent per-provider health record in `cloud_state.json` (Phase 26.18 — see `04_Backend.md` §7 and ADR-011).

**Manual Bet lifecycle (Phase 26.19).** A bet's lifecycle status and its settlement result are independent (ADR-012): `status` (`pending`/`approved`/`rejected`/`settled`) tracks the workflow decision; `resultado`/`placar` tracks what actually happened in the match. A rejected bet is settled by the same engine as any other bet but never advances to `status: 'settled'` and never affects bankroll, ROI, or any financial calculation (`getResolvedManualBets()` excludes it). Rejected bets remain visible in the Manual Bets list and in a dedicated "Rejeitadas" view on the History page (`getRejectedManualBets()`), reusing the existing History table/filter bar rather than a new page.

**Duplicate manual bet prevention (Phase 26.19).** Three independent layers: (1) the Scout workspace hides a fixture's card the instant any bet exists for it, in any lifecycle state, not just once approved/rejected — the card only reappears if the bet is removed; (2) `findManualBetByOpportunity()` guards both the Scout create path and the manual entry form synchronously, so a double-click cannot create two records; (3) the backend (`POST /save` → `_dedupe_manual_bets()`) independently drops later duplicates for the same fixture+market before persisting to GitHub, as an authoritative backstop, and the frontend resyncs from the cloud if it ever has to (ADR-013).

**Railway backend.** Five endpoints operational (`/`, `/health`, `/load`, `/save`, `/run-settlement`). Stateless, single worker, 300-second timeout. `cloud_state.json` is the persistence bridge between browser and GitHub. `POST /save` now also deduplicates `manualBets` before writing (Phase 26.19).

**Dashboard.** All pages functional: Daily Picks, Live Center, Pending, Manual Bets, History (now with a Resolvidas/Rejeitadas toggle), Analytics, Bot vs Manual, Bankroll/Settings. Auto-save to cloud with 4-second debounce. Scout workspace with Poisson analysis for manual bet creation. Pending KPI, Pending page, and the "Muitas apostas abertas" alert all read from the same `getPendingRows()` helper and cannot numerically diverge.

**Manual bet and bankroll cloud synchronization.** `cloud_state.json` is the authoritative source for both `manualBets` and `movements` (bankroll deposits/withdrawals). A fresh browser session (e.g. Incognito, a new device, or cleared localStorage) reconstructs the exact same runtime state — bankroll, movements, manual bets, pending/live classification, KPIs, alerts — as a session that already has local data.

**Synchronization model is event-driven, not polling-based.** The 60-second `setInterval` in `boot()` refreshes only the read-only picks CSVs (`loadData()`), league stats, and pending-alert checks. It never re-fetches `cloud_state.json` and never touches `state.manualBets` or `state.movements`. Manual bets and movements are instead refreshed on explicit events: boot (`_doLoadCloudState()` / `_reloadManualBetsFromCloud()`), on-demand settlement completing, the "Load Cloud" button, tab visibility change, and now also whenever a save drops a server-side duplicate (`duplicatesRemoved` in the `/save` response — Phase 26.19).

**Telegram notifications.** New picks sent after each generation run with deduplication via `sent_state.json`.

**League registry.** 21 leagues managed via `src/league_registry.py`. All settlement routing derived automatically.

**Documentation.** Complete documentation system established under `docs/`. Includes: project context, architecture decisions (13 ADRs), architecture map, repository navigation guide (`PROJECT_MAP.md`), data flow, dashboard reference, backend reference, known issues, roadmap, change log, development guidelines, and session handover template. `CLAUDE.md` added at repository root as the workflow entry point for new Claude sessions.

---

## Current Development

No active investigation. This phase's changes were validated with an automated Chromium (Playwright) walkthrough of the live dashboard plus isolated Python checks of the settlement bridge — both are scratchpad-only tooling, not committed to the repository, and left no diagnostic instrumentation behind in `index.html`, `update_results.py`, or `sync_server.py`. The codebase remains clean of prior-phase temporary instrumentation.

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
3. Consider refreshing `01_Architecture.md` Section 3 ("Startup Flow") and the "60-second browser interval" architectural rule — both still describe the pre-Phase-26.17 design and should be brought in line with the current event-driven model.
4. Monitor `cloud_state.json["providerHealth"]` after real settlement runs to confirm the "warning" threshold (2 consecutive failing runs) is well-tuned in practice.
5. No dashboard implementation exists yet for rejected-bet analytics (rejected win rate, theoretical ROI, false-negative rate, by league/market/confidence/opinion) — the data model supports it (Phase 26.19; see `03_Dashboard.md` §9 and ADR-012), but no chart or KPI was built, per the original request's scope ("no dashboard implementation is required now").

---

## Notes

No diagnostic instrumentation remains in the codebase as of Phase 26.19. The Manual Bet lifecycle changes this phase (`findManualBetByOpportunity()`, `getRejectedManualBets()`, `_historyViewMode`, `_dedupe_manual_bets()`, the `Placar` CSV column, the `apply_df_results_to_manual_bets()` rejected-status guard) are permanent production code, not temporary diagnostics.
