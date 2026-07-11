# Current Status

**Last Updated:** 2026-07-11 (Phase 26.25 — Full dashboard localization to European Portuguese, PT-PT)

---

## Overall Project Status

**Operational — stable.**

The bot is running in production. Pick generation, settlement, and the dashboard are all functional. The Railway backend is stable. Manual bets, bankroll movements, and bot picks all settle and synchronize correctly via GitHub Actions, on-demand settlement from the dashboard, and cloud recovery on fresh browser sessions.

This phase translated every remaining piece of English UI text in `index.html` to natural PT-PT — the dashboard now actually matches the language rule already stated in `03_Dashboard.md` §1 and `DEVELOPMENT_GUIDELINES.md` ("Keep all UI text in European Portuguese. Do not mix languages in user-facing strings."), which had drifted out of compliance as features were added in English across several prior phases (most visibly the Opinion Validation/Recommendations/Simulator/Strategy Lab additions below, plus the older Season Archive/Close Season flow and assorted analytics tables). No business logic, calculation, threshold, or persistence changed — see Phase 26.25 in `08_Change_Log.md` for full detail, including the `ptLabel()` pattern used to translate display text without touching the English internal codes several rule engines compare against.

Phases 26.20–26.24 (below) shipped in a prior session but were never given their own `Current Development`/handover write-up at the time — only a one-line Change Log summary and the technical reference in `03_Dashboard.md` §10. This entry backfills that gap so this document reflects everything actually in production.

The provider API error visibility work (Phase 26.18), the Manual Bet lifecycle rework (Phase 26.19), and the Live Center/sync fixes (Phase 26.17) remain stable — no changes to those code paths this phase.

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

**Opinion analytics suite (Phases 26.20–26.23, Bot vs Manual tab).** Below the existing Opinion Performance/Calibration/Insights sections: **Opinion Validation** — expected-vs-actual ranking, a weighted-pairwise Calibration Score (0–100) with a configurable tolerance for insignificant inversions, an Opinion Pair Analysis table, a Decision Cost metric, per-opinion trend sparklines, a sample-size Confidence indicator, ranked insights, a trend warning, and a calibration-over-time chart. **Opinion Engine Recommendations** — a deterministic (non-AI) rule engine over that same analytics, producing severity-ranked, evidence-backed recommendations and one overall Opinion Engine Health label. **Recommendation Simulator** — a pure what-if layer (three sliders, ephemeral, never persisted) that replays settled opinion bets through a parameterized copy of the real classifier, with a bounded (≤1331-combination) "Best Nearby Configuration" search. All three are analytics-only and read-only; see `03_Dashboard.md` §10 for full technical detail and ADR references.

**Strategy Lab (Phase 26.24, own tab).** A frontend-only betting-strategy backtester, distinct from the Opinion analytics above: a Strategy Builder (opinion/score/edge/odds/stake/league/market/season filters) feeds a Historical Replay, a Compare-Against-Production panel, a Robustness Score explicitly designed so tiny samples can never outrank large ones, chronological-thirds Stability, Risk Analysis, a bounded (≤81-combination) Strategy Optimizer, and a pure JSON export. No persistence, no writes to production state. See `03_Dashboard.md` §10.

**Dashboard localization (Phase 26.25).** Every page's visible UI text is now natural PT-PT, including the four analytics features above and the Season Archive/Close Season flow. Internal English status/severity codes used in rule-engine comparisons (e.g. `'Broken'`, `'HIGH'`, `'PROMOTE'`) are unchanged — only translated at render time via a shared `ptLabel()` lookup — so no comparison logic, threshold, or persisted value changed. See Phase 26.25 in `08_Change_Log.md`.

**Documentation.** Complete documentation system established under `docs/`. Includes: project context, architecture decisions (13 ADRs), architecture map, repository navigation guide (`PROJECT_MAP.md`), data flow, dashboard reference, backend reference, known issues, roadmap, change log, development guidelines, and session handover template. `CLAUDE.md` added at repository root as the workflow entry point for new Claude sessions.

---

## Current Development

No active investigation. This phase (26.25, PT-PT localization) touched only `index.html` visible text — `update_results.py` and `sync_server.py` were not modified. Validated with `node --check` after every batch of edits, a full-page `innerText` extraction across all 11 tabs iteratively grepped for stray English until clean, and the complete existing Playwright regression suite (6 suites, 130+ checks, covering the Manual Bet lifecycle and all four Opinion/Strategy Lab analytics features) re-run and passing — confirming the translation changed no calculation, threshold, or comparison. The suite's own text assertions were updated in the scratchpad copy to expect PT-PT strings going forward; none of that test tooling is committed to the repository. The codebase remains clean of diagnostic instrumentation from this or prior phases.

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
6. Minor documentation debt, low priority: Phases 26.20–26.24 (Opinion Validation, Opinion Engine Recommendations, Recommendation Simulator, Strategy Lab) were never given a detailed `08_Change_Log.md` phase section or a session handover at the time they shipped — only a one-line summary-table row each and the technical reference already in `03_Dashboard.md` §10. This document and the Change Log summary table are now current; the detailed narrative write-up for those five phases specifically was not reconstructed retroactively this session (only Phase 26.25/localization has a full section, since that is the phase actually implemented this session). Worth doing in an idle session if the historical record matters, not blocking.

---

## Notes

No diagnostic instrumentation remains in the codebase as of Phase 26.25. Any future UI text added to `index.html` must be written directly in PT-PT (see `DEVELOPMENT_GUIDELINES.md`) — do not add English strings and plan to translate them later; Phase 26.25 exists precisely because that happened silently across several earlier phases.
