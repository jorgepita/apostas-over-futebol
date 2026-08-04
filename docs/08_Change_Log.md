# Change Log

Major architectural phases in reverse chronological order. Minor commits, CSV updates, and hotfixes are not listed — see `git log` for the full record.

---

## Summary

| Phase | Date | Summary |
|---|---|---|
| 29.3 | 2026-08-04 | Implemented the Analytics dual-view UI (Current Season + All-Time) on Phase 29.2's audited, deployed aggregation pipeline. The page now reads top-to-bottom as three groups (no tabs, both perspectives always visible): a new **Visão Geral** comparison (`renderAnalyticsOverview()`, mirroring `renderVersus()`'s existing card pattern) showing Settled Bets/Profit/ROI/Yield/Hit Rate/Average Odds/Maximum Drawdown for `currentSeason` vs `allTime`; **Época Atual**, re-pointing the real-bet-history League/Market/Source tables and Top/Worst Performers (`renderAnalytics()`/`renderAnalyticsPerformers()`) from `allTime` to `currentSeason`, plus Performance Over Time (left on its own independent rolling-window logic, deliberately not forced onto either bundle); and **Histórico Completo**, keeping League Analytics/Classification, Market Intelligence, Edge Validation, Strategy Validation, Model Calibration, Action Engine, and Learning Center unchanged on `allTime`. `buildAnalyticsDataset()`'s `summary` gained two additive fields (`avgOdds`, `maxDrawdown`) computed by reusing existing pure helpers (`avg()`, `computeDrawdownAnalysis()`) over the same rows already in scope — no restructuring, no new dataset. `renderStreaks()`/`#streakCards` deliberately left untouched on `allTime`, since that element lives on Dashboard Home, not Analytics. Verified: all 15 pre-existing element IDs preserved (1 new added, 0 lost); the 7 All-Time sections plus the `league_stats.csv` table confirmed byte-for-byte identical to the Phase 29.2 baseline; `currentSeason` figures independently cross-checked against a fresh session filter and confirmed genuinely different from `allTime`. Full Python suite 430/430 and QuantEngine golden vectors 285/285 unchanged. See `03_Dashboard.md` §6/§10 |
| 29.2 | 2026-08-04 | Consolidated Analytics-tab aggregation into one shared, memoized pipeline. All 12 Analytics render functions previously recomputed their own per-league/market/source/edge/odds/weekday/hour aggregates and streaks independently on every render — the same `buildAnalytics()` calls and inline bucket-reduction logic copy-pasted across the file. New `buildAnalyticsDataset()`/`getAnalyticsAggregates()` (memoized via the existing `memoizeDataFn()` mechanism, ADR-016) is now the single source every section reads from, returning `{ allTime, currentSeason }` — `allTime` fully wired into all 12 sections this phase; `currentSeason` is present in the shared structure (reusing the Phase 28.5 season-boundary helpers) but not yet consumed by any renderer, preparing for a future dual-view Analytics phase without duplicating this pipeline again. Preserved one genuine pre-existing inconsistency rather than silently unifying it: two distinct edge-bucket filters ("loose" — edge≥0 only, used by Edge Validation/Strategy Validation; "strict" — also requires real odds>1.0 and a settled result, used by Action Engine/Learning Center) are now two named shared builders (`buildEdgeBuckets()`/`buildEdgeBucketsStrict()`) instead of two independent inline computations. Purely an internal refactor — verified with a byte-for-byte Playwright snapshot diff of `#tab-analytics` against a rich synthetic dataset (identical before/after), plus the full Python suite (430/430) and QuantEngine golden vectors (285/285), both unchanged. No new test file committed — Playwright is not a repository dependency (no `package.json`, consistent with ADR-005's no-build-step constraint) and this project's established convention keeps such DOM regression scripts scratchpad-only. See `03_Dashboard.md` §10 |
| 28.5 | 2026-08-04 | Implemented the fix identified by the same-day, read-only Phase 28.4 audit: after a correctly-executed Season Close, History/Bank/Dashboard Home/Bot vs Manual (and the Opinion suite inheriting from it) kept showing previous-season data — not a Season Close bug, but `06_Roadmap.md`'s DX-4, a documented gap where the existing `isOnOrAfterSession()` season-boundary primitive was never wired into the functions those pages actually render from. Two new shared helpers, `getSessionRealResolvedBotHistory()`/`getSessionResolvedManualBets()` (`index.html`), now feed `getMetrics()`'s `sessao` bundle, `getBankrollState()` (eliminating a second, independently-diverging bankroll calculation), `renderBankrollPerformanceBreakdown()`, and `renderVersus()` (which had 8 independent re-derivations of the same manual-bet pool collapsed into 1 — the single change that makes the entire Opinion Validation/Calibration/Recommendation Engine/Simulator suite season-aware automatically, with no code of its own). `getFilteredRealClosedRows()` gained one optional, default-`false` `sessionOnly` parameter, applied only at History/Dashboard Home/Bank's evolution chart — every other caller (archive snapshot, Analytics, the Close Season wizard) untouched by design. Analytics stays all-time, unchanged — `league_stats.csv` has no season concept in the Python backend; fixing that is an explicit, separate, out-of-scope backend change. Season Close, archive generation, backups, R2, Railway, cloud sync, and Strategy Lab's own pre-existing season filter were not modified. Real-browser (Playwright/Chromium) regression: 27/27 assertions across 3 scenarios. Full Python suite 430/430; QuantEngine golden vectors 285/285; both unchanged, as expected for a JS-only, dashboard-only change. See `05_Known_Issues.md` DASHBOARD-8 |
| 28.3A | 2026-08-04 | Fixed a boot-time synchronization defect a read-only audit (Phase 28.3) found: a returning browser (any browser with a bankroll ever configured) never re-checked the cloud on boot, so a Season Close executed on a *different* device left it showing its own stale season indefinitely — even though `cloud_state.json` on GitHub already held the correct new season (confirmed live via Railway `/load` during the audit). New `isCloudSeasonNewer()` helper (`index.html`) — one read-only `GET /load`, compares `sessionStartDate` only, mutates nothing. `boot()`'s auto-recovery gate now also runs the existing, unmodified `_doLoadCloudState({fromUser:false})` when the cloud season is strictly newer than the local one; same-or-older cloud seasons leave today's behaviour (local wins) completely unchanged, preserving every existing protection against overwriting genuinely newer or unsynced local data. `executeSeasonClose()`, `saveCloudState()`, and the manual "Load Cloud" button's own guard were not touched. Verified with a real-browser (Playwright/Chromium) test against the unmodified `index.html`, 6 scenarios / 22 assertions, all passing. Full Python suite 430/430; QuantEngine golden vectors 285/285; both unchanged, as expected for a JS-only, boot-sequence-only change. See `05_Known_Issues.md` DASHBOARD-7 |
| 28.2 | 2026-08-03 | Integrated three new leagues as full first-class production leagues: Switzerland Super League (`suica`, af_id=207), Spain Segunda División (`espanha2`, af_id=141), Portugal Liga Portugal 2 (`portugal2`, af_id=95) — all `"european"` season model, IDs confirmed live against API-Football. A fourth requested league, France Ligue 2, was found already fully active (`franca2`, af_id=62) and deliberately not re-added after an audit found no hidden gaps. `src/league_registry.py`, `config.json` (`leagues`/`api_football.league_ids`/new `historical.seasons_by_league` override), `fetch_oddsapi_fixtures.py` (`DEFAULT_LEAGUE_IDS`), `fetch_historical.py` (`LEAGUE_INFO`) all updated — the latter two dicts were previously undocumented but universally-followed steps, now added to `04_Backend.md`'s checklist. `data_raw/{suica,espanha2,portugal2}.csv` built from real, live API-Football data (2024+2025 seasons, 459/935/615 rows), force-added since `data_raw/*.csv` is gitignored by pattern. `index.html`'s `LEAGUE_NORMALIZE` extended; dashboard filters needed no change (dynamically populated). No hardcoded per-league special cases — settlement, analytics, and backups confirmed generic via direct testing against real code paths. 12 new tests (`tests/test_phase28_new_leagues.py`); full suite 430/430 passing; QuantEngine golden vectors 285/285 unchanged. No production runtime data modified. See ADR-004's Phase 28.2 update |
| 27.4 | 2026-08-02 | Removed football-data.org entirely following a read-only dependency audit that found it was first-attempt provider for only 6 of 22 leagues, with API-Football already providing complete, proven fallback coverage everywhere. API-Football is now the sole result provider for both bot pick and manual bet settlement. `update_results.py`: removed `classify_fd_status()`, `should_use_api_football_fallback()`, `http_get_json_football_data()`, `fetch_matches_for_league_date()`, `_respect_fd_api_spacing()`, all FD constants/caches, and `FOOTBALL_DATA_API_KEY`; the ~180-line multi-branch provider-selection block in `update_dataframe()` collapsed to one unconditional `_run_af_and_account()` call per row — `update_dataframe()` itself was not split or redesigned. `src/league_registry.py` rewritten: removed `fd_code`/`fd_blocked`/`BLOCKED_FOOTBALL_DATA_CODES`; every league's internal routing `code` value deliberately preserved byte-for-byte (zero behaviour change) despite the FD-derived naming now being purely historical. Removed `FOOTBALL_DATA_API_KEY` from `.env`, `.env.example`, and all three jobs in `bot.yml`. Dashboard (`index.html`): removed the now-dead `football-data.org` competition-code block from `LEAGUE_NORMALIZE` and the `PROVIDER_HEALTH_LABELS` entry (both proven zero-visual-change before removal). 2 tests updated, 1 redundant test deleted (its AF-equivalent coverage already existed); full suite 418/418 passing; QuantEngine golden vectors 285/285 unchanged. `update_results.py` net -447 lines; full diff -805/+270 across 12 source/config/test files plus documentation. See ADR-004's Phase 27.4 update |
| 27.3 | 2026-08-02 | Production-hardened the Phase 27.2 backup subsystem following Phase 27.2A's resource-audit approval. Fixed a real bug: `restore()` downloaded the same R2 archive twice; now downloads once. Added configurable R2 connection tuning (region/timeouts/retries, all optional with defaults) and per-operation error classification (`R2ConnectionError`/`R2PermissionError`/`R2OperationError`), never exposing credential values. Deduplicated repeated R2-client-acquisition logic across the three action endpoints. Added local-development support (`load_dotenv()` + a new `.env.example`). Incidentally found and fixed prospectively: a pre-existing, unrelated `.env` file with real, live API keys was tracked in git in this public repository — untracked and gitignored (keys remain exposed in history and should be rotated). 20 new tests (120 total in the backup subsystem); full suite 419/419 passing. See ADR-020's Phase 27.3 addendum |
| 27.2 | 2026-08-02 | Implemented the backup & disaster-recovery subsystem designed in Phase 27.1: Cloudflare R2 as the permanent backup archive, GitHub unchanged as the production source of truth, Railway holding zero backup bytes at rest by construction (every archive built fully in memory, never written to disk). New `src/backup/*` package; four new Railway endpoints; a GitHub Actions scheduled backup job (every 6h) and weekly R2 integrity sweep; a new dashboard "Backups" tab; a mandatory (but not-yet-configured-tolerant) pre-End-of-Season critical backup that also finally gives the Season Archive a durable copy outside browser `localStorage`. 100 new tests against an in-memory R2 double — no real Cloudflare bucket exists yet, so live upload/restore is unverified pending real credentials. See ADR-020 |
| 26.46 | 2026-07-29 | Added a fixture-level approval exposure warning: before either approval mutation (Daily Picks' `.js-bot-approve` or Manual Bets' `mbHandleRowApprove()`) commits, `confirmFixtureApprovalExposure()` checks whether another approved, unresolved bet (bot or manual, any market) already exists on the same fixture (`Date+League+Game`, market-agnostic) and, if so, shows a PT-PT `confirm()` describing the existing exposure, the candidate's own stake, and the resulting total — Cancel leaves state untouched, "Aprovar na mesma" runs the existing, unmodified approval mutation exactly once. Warning only — no hard cap, no change to stake sizing, Kelly, bankroll, or eligibility. Deliberately independent from ADR-018 (bot generation lock). A pre-commit audit (same phase, before any commit) traced whether one logical bet could be counted more than once by the new lookup — empirically confirmed it cannot; no production-code fix required, only a clarifying code comment and documentation note. See ADR-019 and `03_Dashboard.md` "Fixture-Level Approval Exposure Warning" |
| 26.45 | 2026-07-27 | Implemented Policy A, the fixture-level bot-pick market lock, closing the cross-run O2.5/BTTS correlated-duplication gap confirmed in production (West Ham vs Leeds, Gnistan vs Mariehamn). New `apply_fixture_market_lock()` (`src/pipeline.py`) runs before `dedupe_correlated_picks()`'s unchanged same-run selection; once a fixture's first market is persisted to `picks_history.csv`, the competing market can never be generated again, regardless of approval/settlement state. Bot-only; manual bets, settlement, ADR-015/ADR-017, and the dashboard are untouched. See ADR-018 |
| 26.44 | 2026-07-21 | Fixed Dashboard → Análises → "A — Desempenho por Liga" showing only ~15 stale league/market rows frozen since 2026-05-24, regardless of ~2 months of continuous settlement/generation (root cause found via a read-only investigation into MLS's absence from the table). `league_stats.csv` was correctly regenerated by `update_league_stats()` on every settlement (`update_results.py::main()`) and generation (`main.py`) run, but never uploaded to GitHub in either path — a local-only write on an ephemeral GitHub Actions runner with zero durable effect. Fixed additively: `update_results.py::main()` now uses a new `_persist_league_stats()` helper (compute + upload in one try/except, preserving this derived file's existing failure tolerance); `main.py`'s `upload_outputs()` call now includes the `league_stats.csv` path. `update_results.py::run_settlement_remote()` (Railway on-demand settlement) never called `update_league_stats()` and remains unaffected, as before. Zero Analytics calculation semantics changed. Verified against real production data (scratch output only): a fresh calculation produces 27 rows including `MLS/O2.5` (21 picks, ROI −18.05%) and `MLS/BTTS` (1 pick) — proving MLS was fully eligible and purely blocked by the upload gap; MLS Next Pro correctly still produces no row (zero current records, a separate deferred issue, not forced). A related audit found `sent_state.json`/`team_alias_cache.json` share the same never-uploaded pattern — reported, not fixed, out of scope. The Huntsville City vs Crown Legacy historical-identity/corruption issue found during the triggering investigation was also deliberately deferred, untouched. See `05_Known_Issues.md` ANALYTICS-1 and `04_Backend.md` §11 |
| 26.43 | 2026-07-21 | Postponed/cancelled/abandoned/missing-fixture bets no longer stay exposed indefinitely. Two safeguards: automatic voiding (explicit `PST`/`CANC`/`ABD` status after 48h since original kickoff; a persistently undiscoverable fixture after 72h + repeated genuine-`NO_MATCH` evidence + a bounded final rediscovery search) and a manual "Anular aposta" fallback in Live Center (any unresolved approved bet, 24h after kickoff). Both write the existing `P` result through the existing shared settlement engine — no new financial arithmetic, no new result code. Thresholds configurable in `config.json["settlement"]["void_policy"]`. New additive `SettlementReason`/`MissingAttempts` CSV columns and manual-bet fields for the audit trail. Prompted by Chicago Fire vs Vancouver Whitecaps (2026-07-17), flagged unresolved during Phase 26.42. A pre-commit safety audit (same session) found and corrected three defects before proceeding: SUSP/INT/SUSPENDED were unsafely auto-void-eligible (could void a match still going to resume — reclassified out); the manual-bot bridge case never surfaced its reason in History (merge-point fix in `getRowWithLocalEdits()`); and a pre-existing, already-active production bug (`HISTORY_COLUMNS` silently stripping `Placar` since Phase 26.19) was found and fixed preventatively. See ADR-017 |
| 26.42 | 2026-07-21 | Fixed a production settlement failure affecting every current senior MLS bet: `src/league_registry.py`'s `"mls"` entry had `af_id=909` (API-Football's MLS Next Pro competition) since Phase 26.12, while `config.json` correctly held `253` the whole time — settlement queried the wrong competition for every `"MLS"`-labelled bet. Restored `"mls"` to `af_id=253` and established MLS Next Pro (`"mls_next_pro"`, `af_id=909`) as a fully independent, first-class 22nd league — actively configured for fixture fetching, generation, dashboard display, and settlement exactly like every other league, never substituting for or depending on senior MLS. Removed the root cause of the original collision: `fetch_oddsapi_fixtures.py` no longer silently substitutes a different competition when a configured league ID returns zero fixtures for a date. One historical, deterministically-identifiable unresolved row (`"Huntsville City vs Crown Legacy"`) relabelled `MLS` → `MLS Next Pro`; all 28 already-settled historical MLS Next Pro rows left untouched. Also fixed a related frontend display gap: manual bets' persisted `kickoffUTC` was never propagated through `getManualRowsMerged()` nor preferred over the live-fixture lookup in Pending/Live Center, producing "Kickoff: —" once a fixture aged out of the rolling fixtures window. See ADR-004 update, `05_Known_Issues.md` SETTLEMENT-3/DASHBOARD-6 |
| 26.41 | 2026-07-15 | Concluded the H1/H2/H3 Performance Optimisation Programme. An independent architecture audit found Phase 26.40's dispatcher migration incomplete: the Manual Bets action surface (5 handlers) still called `markDirty()` then the legacy `rerenderManualOnly()` wrapper (duplicate render + always rendering invisible `tab-pending`/`tab-live` DOM — measured ~67ms/27% waste per action), and `addMovement()`/delete-movement retained a redundant direct `renderBankrollPage()` call left over from Phase 26.40's own Issue B fix. All 7 mutation paths migrated to `markDirty()` alone; 3 confirmed-dead wrapper functions (`rerenderSummaryOnly()`, `rerenderPendingOnly()`, `rerenderLiveOnly()`) removed. `rerenderDayOnly()`/`rerenderHistoryOnly()`/`rerenderManualOnly()` deliberately retained for their remaining UI-only (non-mutating) filter/edit-mode-toggle callers. Manual Bet actions now measure ~202–212ms on the real account, matching Bot Pick actions (~199–263ms) — the explicit goal. New 15-check Playwright script; full 14-suite regression harness passing |
| 26.40 | 2026-07-15 | Fixed two issues found during the Performance Audit's own validation (Issue A: `pendingCancel()` left "Aprovar" unbound for a same-session re-approval — fixed with a `bindBotTableControls()` call; Issue B: `addMovement()`/delete-movement never called `markDirty()` — fixed by reusing it instead of a standalone `invalidateDataCache()`), then implemented the audit's third and final optimisation (H3): an active-tab-gated render dispatcher. H3.1 (`renderActiveTabIfStale()`, a `_dataGeneration`-aware dedup guard) eliminates duplicate render passes for one logical action. H3.2 (`PAGE_RENDERERS`, a dependency map from tracing each render function's real DOM target) stops rebuilding invisible tabs' DOM, while every tab remains fully mounted and instantly current on activation — not lazy-loading. `renderVersus()` kept as one deliberate GLOBAL exception (cross-tab `window._opnSimCache` dependency). A live-input regression (Pending page's Odd Real/Stake Real inputs destroying themselves on every keystroke) was caught and fixed via new `markDirty(skipRender)`/`update(...,skipActiveTabRender)` parameters. Measured on the real account: `rerenderAll()` ~177ms, Approve ~224ms, Cancel ~201ms — down from Phase 26.39's ~1.1–2.7s and the original 87.7s baseline. See ADR-016 |
| 26.39 | 2026-07-15 | Second Performance Audit fix: introduced a single, shared data-layer memoization cache (`_dataGeneration` counter + `memoizeDataFn()`) for the 8 aggregate functions the audit identified as pure-for-one-state (`getHistoryRowsMerged`, `getDailyRowsMerged`, `getAllBotRowsMergedUnique`, `getManualRowsMerged`, `getResolvedManualBets`, `getMetrics`, `getRiskMetrics`, `getStakeContext`). Every state mutation in the file (13 explicit call sites plus a hook inside `markDirty()`, covering the ~20 functions that mutate `footballHistory`/`footballDaily`/`manualBets`/`manualBetsRemote`/`localEdits`/`movements`/`bankrollInicial(Set)`) now calls `invalidateDataCache()`. `getPendingRows()`/`getPendingCount()` and `computeRecommendedStake()` itself are deliberately NOT cached (time-dependent / per-row respectively). Measured: `renderPendingQueue()` (H1's remaining largest cost) 18.8s → 0.11s (-99.4%); `rerenderAll()` 28.7s → 1.1–1.2s (-96%); Approve bot pick 35.9s → ~2.3–2.7s; Cancel 41.9s → ~0.7–0.8s. Combined with H1, total improvement from the original 87.7s audit baseline is >98%. Full 11-suite regression harness plus a new 10-check cache-invalidation-scenario suite (Approve/Cancel/Stake edit/Odd edit/manual create/delete/settlement/cloud reload) all pass. See "Next Priorities" in `07_Current_Status.md` for the residual DOM/duplicate-render cost this did not address |
| 26.38 | 2026-07-15 | Performance fix from the completed Performance Audit: `getPendingRows()` was being called from `computeAlerts()`, `renderSummaryHeadlineStats()`, and `renderMobileHomeDash()` purely for `.length` — but since Phase 26.36 every bot row inside it calls `computeRecommendedStake()`, cascading into `getRiskMetrics()`/`getMetrics()` and ~9 full history/manual-bet rebuilds per pending row. Measured at 14.7–19.8s per call on the real account (271 approved picks). Added a new, minimal `getPendingCount()` helper that mirrors `getPendingRows()`'s two filter predicates but skips the `.map()`/`computeRecommendedStake()` step entirely, and repointed the three count-only call sites to it. `getPendingRows()` itself is byte-for-byte unchanged — the Pending page's behaviour, ordering, filtering, and Stake rec./Stake Real values are identical. Measured result: `rerenderAll()` 87.7s → 28.7s (-67.3%); `renderAlertsCenter()` 23.7s → 1.10s (-95.4%); `renderSummaryHeadlineStats()` 18.9s → 0.28s (-98.5%); `renderTopDecisionBlock()` 17.5s → 1.09s (-93.8%). `renderPendingQueue()`/`rerenderManualOnly()` are unchanged by design (~15–20s) and are now the single largest remaining cost — see "Next Priorities" in `07_Current_Status.md` |
| 26.37 | 2026-07-15 | Final wording refinement to the Phase 26.36 Pending page fix: reverted the desktop table's shared column header from "Stake rec." back to plain "Stake", since that single header also sits above manual rows, which have no recommendation concept — "Stake rec." was semantically wrong for them. The underlying **value** is unchanged: bot rows still display `computeRecommendedStake()`'s result, manual rows still display their own entered stake. The mobile card (already row-type-aware) is unaffected — bot cards still say "Stake rec.", manual cards still say "Stake". Desktop-header wording only; no value, calculation, exposure, bankroll, or persistence change |
| 26.36 | 2026-07-15 | Pending page UX fix: bot rows' "Stake" column now shows `computeRecommendedStake()`'s value ("Stake rec.") instead of the raw model stake (`_stakeModeloNum`, "Stake mod."), and the column header/mobile-card label renamed to "Stake rec." — making it directly comparable to the adjacent "Stake Real" column. Reuses the existing recommendation function (no duplicated logic); manual bet rows are completely unchanged (still their own entered `stake`, no rec/real distinction to display). No change to `computeRecommendedStake()`, exposure, bankroll, settlement, persistence, or StakeReal behaviour — display-only |
| 26.35 | 2026-07-15 | Fixed the Phase 26.33 StakeReal auto-fill guard: it used string truthiness (`!existingStakeReal`) to decide whether a pick "already had" a real stake, so a stored `"0"` (a non-empty string) was wrongly treated as a deliberate user value and permanently blocked the default — understating that pick's `StakeReal` and Open Exposure, and surviving indefinitely across Cancel→re-approve cycles since `pendingCancel()` never clears `stakeReal`. Guard now parses the value with the existing `num()` helper and auto-fills whenever it is `null` or `<= 0` (empty, undefined, NaN, invalid string, zero, or negative) — `computeRecommendedStake()` itself is unchanged and, by its own hard floor (`clamp(x, 1, maxCap)`), can never legitimately produce zero, so treating a stored zero as "not set" cannot ever suppress a real recommendation. No change to `computeRecommendedStake()`, exposure calculation, or bankroll calculation. See `05_Known_Issues.md` DASHBOARD-5 |
| 26.34 | 2026-07-15 | Fixed a manual-result-override precedence flaw: `resultadoManual` (the History-page/"Live Settle" bridge for bot picks automated settlement can't resolve) used to permanently mask the CSV's real `Resultado` even after automated settlement later determined the actual result — found to have already caused two real, silent bankroll/ROI misstatements (Saint Etienne vs Nice, Nice vs Saint Etienne). `getRowWithLocalEdits()` and `getDailyRowsMerged()` now always prefer a valid CSV result once one exists; the manual override is consulted only while the CSV is still empty. No automatic deletion of stale overrides — they're simply ignored once superseded, preserving the audit trail. See ADR-015 and `05_Known_Issues.md` DASHBOARD-4 |
| 26.33 | 2026-07-15 | Bot pick approval now defaults `StakeReal` to the pick's displayed "Stake rec." (`computeRecommendedStake()`) value the first time it's approved, but only when the user hasn't already typed a `StakeReal` in first — a typed value always takes precedence and is never overwritten. Single change point: the `.js-bot-approve` click handler in `bindBotTableControls()`. No change to Kelly, `computeRecommendedStake()` itself, bankroll logic, settlement, persistence format, or CSV schema — purely a one-time default applied to the existing `localEdits[pickKey].stakeReal` field at the moment of approval. Manual bets and previously-approved picks are untouched |
| 26.32 | 2026-07-12 | Fixed manual bets settling out of sync with bot picks for the same fixture (a manual bet settled immediately while its equivalent bot pick stayed LIVE until a later run). Root cause: not a settlement-engine bug — `update_dataframe()`'s `KICKOFF_TOO_EARLY` gate only applies `if kickoff_str:`, and manual bets never actually had `kickoffUTC` persisted (a documentation claim from Phase 26.7–26.9 to the contrary was inaccurate — corrected). Fix: `addManualBetFromFixture()` now persists `kickoffUTC`/`homeTeam`/`awayTeam`/`leagueId` at creation time for fixture-backed (Scout) bets, so settlement receives equivalent input to what bot picks already provide. Zero changes to the settlement engine, `RESULT_READY_DELAY`, matching logic, or persistence. Free-form manual bets (no fixture) are unaffected — documented limitation, not a bug. See `05_Known_Issues.md` SETTLEMENT-2 |
| 26.31 | 2026-07-11 | Corrected rejected-bet lifecycle visibility: Phase 26.28's fix removed the duplicate from the wrong page. `getRejectedManualBets()` reverted to showing every rejected bet (settled or not) — "Rejeitadas" is the permanent archive, exactly as originally designed. The actual fix: `renderManualBets()` (operational "Apostas Manuais" list) now hides a rejected bet once it's settled, since a settled bet no longer needs attention there. No change to settlement, persistence, `cloud_state.json`, QuantEngine, or any analytical module — all verified via the full 6-suite Playwright regression harness (now 6/6 fully green) plus a new 24-check targeted script |
| 26.30 | 2026-07-11 | Closed the one gap found by the post-migration QuantEngine architecture audit: the per-league lambda-boost clamp-and-multiply step was duplicated, unverified inline arithmetic in both `src/pick_generation.py` and `analyzeFixture()`. Extracted into `apply_lambda_boost()` (Python, canonical) and mirrored as `QuantEngine.applyLambdaBoost()` (JavaScript), with 8 new golden vectors (142/285 total Python/JS assertions). Verified byte-identical to the pre-extraction inline formula. No other quantitative duplication remains inside the Bot + Scout architecture — see ADR-014 |
| 26.29 | 2026-07-11 | Introduced a shared Quantitative Engine: `src/calculations.py` is now the canonical implementation (extended with named `confidence_factor()`, `fair_odds()`, `expected_value()` functions), and `index.html` gained an isolated `QuantEngine` module that mirrors it exactly, replacing a previously hand-ported, partially-drifted JS copy (missing BTTS diagnostics, missing confidence, a hardcoded `config.json` mirror). A golden-vector conformance suite (`tests/golden_vectors.json` + Python/JS test siblings, 261+134 assertions) is the permanent safeguard against the two drifting again. Score/Opinion decision logic was extracted out of the Scout's `analyzeFixture()` into a separate `classifyManualOpinion()`, consuming — never duplicating — the engine's output. Zero change to bot pick generation, settlement, or CSV output (verified via before/after `apply_stakes()` comparison and the full existing 6-suite Playwright regression harness). See ADR-014 |
| 26.28 | 2026-07-11 | Fixed `getRejectedManualBets()` so History → Rejeitadas only shows rejected bets that haven't been settled yet — previously it showed every rejected bet forever regardless of settlement, creating duplicate visibility with Strategy Lab/Opinion Validation/etc. once a rejected bet settled. Single-predicate fix (`&& b._lucro === null`, the existing project convention — confirmed no dedicated settlement helper exists to reuse instead of introducing one). No change to settlement, persistence, `cloud_state.json`, bankroll, ROI, or any analytical module; all verified via the existing 6-suite Playwright regression harness plus a new targeted 19-check script |
| 26.27 | 2026-07-11 | Removed the legacy NBA subsystem entirely: 8 NBA-exclusive files deleted (5 scripts, 1 config file, 2 data/output CSVs) and 3 dead NBA keys removed from `config.json` (`bankroll.nba_over`, `rules.nba_over`, top-level `nba` block). Preceded by a full read-only audit (previous session) that verified zero shared code between the NBA and football pipelines, and by an archival git tag (`legacy-nba-final`) at the pre-removal commit. Full validation (syntax, test suite, config-equivalence, import checks) confirmed zero football behaviour changed. Repository is now exclusively football |
| 26.26 | 2026-07-11 | Repository hygiene cleanup: removed obsolete `PROJECT_RULES.md` (superseded by `docs/`), replaced the content-free root `README.md` placeholder with a real landing page, committed `CLAUDE.md` and `.claude/settings.json` for the first time (closing a 3-session-old gap where docs already described them as committed), deleted stale diagnostic `audit_output*.txt` files, and added `.gitignore` rules for `.claude/settings.local.json` and `audit_output*.txt`. No code, business logic, or runtime behaviour changed |
| 26.25 | 2026-07-11 | Full dashboard localization to European Portuguese (PT-PT): translated every remaining English UI string in `index.html` — the Season Archive/Close Season wizard, the four Opinion analytics features (26.20–26.23), Strategy Lab (26.24), and assorted pre-existing analytics tables/labels/alerts — to natural PT-PT. No business logic, calculation, threshold, or persistence changed. Internal English status/severity codes used in `===` comparisons across the calibration and recommendation rule engines were kept as-is and only translated at render time via a new shared `ptLabel()` lookup, so no comparison was touched. All 6 existing Playwright regression suites (130+ checks) re-run and passing |
| 26.24 | 2026-07-10 | New "Strategy Lab" page (own tab/nav entry): a pure betting-strategy backtester over settled, Scout-analysed manual bets (including rejected ones). Strategy Builder (opinion/score/edge/odds/stake/league/market/season filters) feeds a Historical Replay (reusing computeStreaks()/computeDrawdownAnalysis()), a Compare-Against-Production panel (reusing window._opnSimCache's calibration/decision-cost/confidence functions), a Robustness Score explicitly designed so tiny samples can never outrank large ones, chronological-thirds Stability, Risk Analysis, a bounded (≤81-combination) Strategy Optimizer ranked by robustness, explainability, and a pure JSON export. Analytics-only, no persistence; every prior Opinion analytics/recommendations/simulator section confirmed unchanged and regression-tested (124 checks across 6 suites) |
| 26.23 | 2026-07-10 | New "Recommendation Simulator" card: a pure what-if layer below Opinion Engine Recommendations. Three sliders (STRONG BUY/BUY/AVOID threshold) replay settled opinion bets through a parameterized copy of the real classifier and the existing calibrationScore()/statsFromBets()/confidenceTier() functions — never writes to state, never persists, never touches production thresholds. Shows Current-vs-Simulated distribution/calibration/decision-cost/pair-score/confidence with explainability and a bounded (±5) "Best Nearby Configuration" search. Analytics-only; every prior Opinion analytics/recommendations section confirmed unchanged and regression-tested |
| 26.22 | 2026-07-10 | New "Opinion Engine Recommendations" card: a deterministic, multi-signal rule engine layered on top of Opinion Validation (no new statistics — reads calib/confidence/decisionCost/pairResults/historyPoints/trendSeries already computed there). Produces severity-ranked, evidence-backed recommendations (review-threshold, confidence nudges, hierarchy-healthy, calibration/opinion trend, insufficient-data) and one overall Opinion Engine Health label. Analytics-only; M/N/O and Opinion Validation unchanged and regression-tested |
| 26.21 | 2026-07-10 | Opinion Validation evolved: configurable calibration tolerance (suppresses statistically-insignificant inversions), an Opinion Pair Analysis table (Expected/Obtained/Difference/Status) sharing one pair-evaluation function with the calibration score, Decision Cost (what the AVOID classifier actually cost or saved), per-opinion cumulative-ROI sparklines, an explained Confidence indicator, and richer generalised insights — internal ranking now compares yield (profit/stake) instead of ROI directly (identical results today; future-proofing only). Analytics-only; M/N/O sections unchanged and regression-tested |
| 26.20 | 2026-07-10 | New "Opinion Validation" analytics section (Bot vs Manual tab): expected-vs-actual ranking, a weighted pairwise-concordance Calibration Score (0–100), pairwise ✔/✖ validation, a sample-size Confidence indicator, priority-ranked insights, a trend warning, and a reconstructed calibration-over-time chart — analytics-only, no changes to pick generation, scoring, settlement, or persistence |
| 26.19 | 2026-07-10 | Manual Bet lifecycle reworked: Scout card hides for any pending bet (not just approved/rejected), fixing a duplicate-creation gap; three-layer duplicate protection (Scout hide, frontend creation guard, backend `/save` dedupe); Reject no longer deletes — it's a permanent, settleable, analytical lifecycle state, fully decoupled from settlement result; new `Placar` (final score) field; History page gains a Resolvidas/Rejeitadas toggle |
| 26.18 | 2026-07-07 | "No matches to settle" root-caused to an expired API-Football subscription silently returning HTTP 200 + empty fixtures; provider responses now validated for embedded errors, normalized, logged, surfaced in the settlement summary and dashboard, and persisted as per-provider health in `cloud_state.json` |
| 26.17 | 2026-07-01 | Manual bet/bankroll cloud synchronization fixed; boot sync guard and event-driven refresh replace periodic polling; Railway `GITHUB_REPO` misconfiguration resolved; dashboard KPI/alert consistency fixes; diagnostic instrumentation removed |
| Doc System | 2026-06-29 | Complete documentation system established; `CLAUDE.md` added at repository root |
| 26.16 | 2026-06-28 | Manual settlement unified into `cloud_state.json`; legacy CSV endpoints removed |
| 26.15 | 2026-06 | Automatic cloud-state recovery on fresh browser startup |
| 26.14 | 2026-06 | Canonical league key used in pick deduplication |
| 26.12 | 2026-06 | Calendar-year season model fix for MLS and Nordic leagues |
| 26.11 | 2026-06 | Railway backend introduced; on-demand settlement added |
| 26.7–26.9 | 2026-05 | KickoffUTC propagated end-to-end; live/pending transitions made kickoff-aware |
| 26.6 | 2026-05 | Pending queue redesigned as an execution workspace |
| 20–21 | 2026-04 | Live Center V1; live settlement engine with audit trail |
| 19 | 2026-03 | Pending queue introduced; create → approve → live workflow |
| 17 | 2026-03 | Scout workspace with real-time Poisson analysis; manual bets in financials |
| 14–16 | 2026-02 | History redesigned as an investigation tool; equity curve and drawdown added |
| 8–13 | 2026-01 | Analytics intelligence engine built incrementally |

---

## Phase 29.3 — Analytics Dual-View UI (Current Season + All-Time)

**Implemented:** 2026-08-04

**Background:** Phase 29.1 (read-only design report) classified every Analytics metric into Current-Season/All-Time/Both and recommended a UX approach; Phase 29.2 (implemented and independently audited "SAFE TO PUSH," then deployed) built the prerequisite shared aggregation pipeline, `getAnalyticsAggregates()` returning `{ allTime, currentSeason }`, with `currentSeason` computed but consumed by zero renderers. This phase builds the UI on top of that already-stable architecture — explicitly a presentation-only phase, with the aggregation layer, memoization, `buildAnalyticsDataset()`, and `getAnalyticsAggregates()` reused exactly as they exist, not redesigned.

**New layout (`index.html`, `#tab-analytics` markup only):** the page now reads top-to-bottom as three groups instead of one flat lettered list, no tabs, both perspectives always visible:

1. **Visão Geral (Overview)** — a new `#analyticsOverviewWrap`, populated by a new `renderAnalyticsOverview()`. Two side-by-side cards (Época Atual / Histórico Completo), mirroring `renderVersus()`'s existing `sourceCard()`/`kpiCell()` visual pattern (re-declared locally, following this project's existing precedent of independent local `kpiCell()` helpers rather than a new global one) rather than inventing a new visual language. Shows: Settled Bets (`summary.picks`), Profit (`summary.lucro`), ROI (`summary.roi`), Yield (`summary.roi / 100` — a plain unit conversion, this project's own established convention, see Opinion Validation's `yield`/`roi` distinction — not a new calculation), Hit Rate (`summary.wr`), Average Odds (new `summary.avgOdds`), Maximum Drawdown (new `summary.maxDrawdown`).
2. **Época Atual (Current Season)** — Section A (Market/Source performance tables), Section B (Top/Worst Performers + this tab's own streak cards), Section C (Performance Over Time).
3. **Histórico Completo (All-Time Model Analytics)** — Section D (League Analytics, `league_stats.csv`-driven) through Section K (Learning Center) — the same 8 sections Phase 29.2 already had reading `allTime`, relettered D–K but otherwise untouched.

**Data-source changes (`index.html` script only):**
- `buildAnalyticsDataset()`'s `summary` gained two additive fields: `avgOdds: avg(closedRows.map(r => r.odd).filter(v => v !== null))` and `maxDrawdown: computeDrawdownAnalysis(closedRows)?.maxDrawdown ?? null` — both reuse existing pure helpers over the same `closedRows` parameter the function already receives. No existing field was changed, no new dataset, no restructuring — this is the one place this phase touches the aggregation layer, and only additively.
- `renderAnalytics()`: `analyticsLeagueRows`/`analyticsMarketRows`/`analyticsSourceRows` tables re-pointed from `allTime` to `currentSeason`. Gained a call to the new `renderAnalyticsOverview()`.
- `renderAnalyticsPerformers()`: Top/Worst Performers (`buildTopWorstPerformers()`) and this tab's own streak cards (`#streakCardsAnalytics`) re-pointed from `allTime` to `currentSeason`.
- **`renderStreaks()` (`#streakCards`) deliberately left untouched, still `allTime`.** Found during implementation: this function is called from within `renderAnalytics()` (Analytics tab's own render dispatch), but the element it populates, `#streakCards`, is physically part of the Dashboard Home page (`tab-summary`), not Analytics. Re-sourcing it to `currentSeason` would have silently changed Dashboard Home's own streak display — explicitly forbidden by this phase's scope ("Do NOT modify: Dashboard"). Analytics' own, Analytics-tab-exclusive streak display is `renderAnalyticsPerformers()`'s `#streakCardsAnalytics`, which was re-sourced as intended.
- **`renderPerformanceOverTime()` deliberately left unchanged**, still computing its own rolling 7/30/90-day/all-time windows independently of `getAnalyticsAggregates()` (as it already did before Phase 29.2, confirmed by that phase's own audit). Its windows are a different, orthogonal dimension to "current season" (a fixed-length recency window vs. a variable-length season boundary) — forcing it onto either bundle would have either broken its "Todo o tempo" row or produced a window that doesn't map cleanly to either concept. Physically relocated into the Época Atual group for UX purposes (it answers an operational "how are things going lately" question) without any change to its own calculation.
- The 8 All-Time sections (League Analytics, League Classification, Market Intelligence, Edge Validation, Strategy Validation, Model Calibration, Action Engine, Learning Center) received **zero source changes** — only their section-header lettering (D–K) and physical position moved.

**Verification:**
- Every one of the 15 pre-existing Analytics element IDs confirmed present, unchanged, and non-duplicated (`node`-diffed against the Phase 29.2 baseline); exactly 1 new ID (`analyticsOverviewWrap`) added.
- The 7 All-Time-model `*Wrap` sections plus the `league_stats.csv`-driven `.league-analytics-body` table confirmed **byte-for-byte identical** between the deployed Phase 29.2 baseline and this phase's render, against the same rich synthetic dataset — proving zero value drift in every section that must stay `allTime`.
- `currentSeason.summary.picks` (20 in the synthetic test) independently cross-checked against a fresh, separately-computed `getFilteredRealClosedRows(getSummaryFilters()).filter(r => r.date >= sessionStartDate)` (also 20) — confirming genuine session-scoping, not an aliased or renamed `allTime` reference. `avgOdds`/`maxDrawdown` also confirmed to differ meaningfully between the two bundles.
- `node --check` on the extracted `<script>` block: OK. Full Python suite: 430/430 passing, unchanged. QuantEngine golden vectors: 285/285, unchanged (both expected — JS-only, Analytics-only change).
- Confirmed via `git diff` scope that no non-Analytics markup or function (Dashboard, History, Bank, Bot vs Manual, Strategy Lab, Season Close, Backups, Cloud Sync) was touched.

**Scope:** `index.html` only (`#tab-analytics` markup + the JS functions listed above). No settlement, generation, backup, persistence-format, or backend change. No new committed test file, consistent with this project's established scratchpad-only Playwright convention.

---

## Phase 29.2 — Analytics Aggregation Consolidation (Architecture First)

**Implemented:** 2026-08-04

**Background — Phase 29.1 (read-only architecture/UX design, same day, not separately logged here per this project's convention of not giving read-only design work its own Change Log section):** a full inventory and classification of every Analytics metric into Current-Season-only / All-Time-only / Both, a UX proposal for an eventual dual-view (Current Season + All-Time) Analytics page, and a performance/architecture recommendation — delivered as a report only, no code touched. This phase (29.2) implements the first, purely internal step that report recommended: consolidate the aggregation layer *before* attempting the dual-view UI, so the eventual Current-Season view can reuse the same pipeline rather than duplicating it.

**Problem:** all 12 Analytics-tab render functions (`renderAnalytics`, `renderAnalyticsPerformers`, `renderLeagueAnalytics`, `renderLeagueClassification`, `renderMarketIntelligence`, `renderEdgeValidation`, `renderStrategyValidation`, `renderModelCalibration`, `renderActionEngine`, `renderLearningCenter`, plus two more calling `buildAnalytics()` internally) independently recomputed the same per-league/market/source `buildAnalytics()` call, the same edge/odds/weekday/hour bucket reductions (copy-pasted inline in at least 4 places with only minor variable-naming differences), and `computeStreaks()`, on every single render pass — with no sharing or memoization between them.

**Fix (`index.html` only):**
- New shared aggregation layer inserted between `computeStreaks()` and `renderStreaks()`: `reduceBucketStats(rows)` (the one bucket-statistics reducer every bucket builder now calls, replacing ~4 copy-pasted inline versions), `buildEdgeBuckets()`/`buildEdgeBucketsStrict()` (the "loose"/"strict" edge-filter variants — see below), `buildOddsBuckets()`, `buildWeekdayBuckets()`, `buildHourBuckets()`, `buildTopWorstPerformers()`, and `buildAnalyticsDataset(closedRows, botRows)` — one function returning a complete bundle: `{ byLeague, byMarket, bySource, byEdge, byEdgeStrict, byOdds, byWeekday, byHour, streaks, summary }`.
- `getAnalyticsAggregates()` — memoized via the project's existing `memoizeDataFn()`/`_dataGeneration` mechanism (Phase 26.39, ADR-016) — calls `buildAnalyticsDataset()` twice: once over the full all-time pool (`allTime`), once over the Phase 28.5 session-scoped pool (`currentSeason`, via the existing `getSessionRealResolvedBotHistory()`/`getFilteredRealClosedRows(filters, true)` helpers — no new season logic). Returns `{ allTime, currentSeason }`. Every one of the 12 sections above now destructures `const { allTime } = getAnalyticsAggregates();` instead of recomputing its own aggregate. `currentSeason` is computed and cached but not read by any renderer yet — intentionally, since this phase's scope was the pipeline, not the dual-view UI itself (Phase 29.1's recommended next phase).
- `getRealResolvedBotHistory()` converted from a plain function to a `memoizeDataFn()`-wrapped one — it was being called ~7 times per Analytics render, unmemoized, before this phase; this is a small extension of the existing memoization pattern, not a new mechanism.
- **Genuine pre-existing inconsistency preserved, not unified:** while consolidating, Action Engine's and Learning Center's edge-bucket filter was found to be stricter than Edge Validation's/Strategy Validation's (requires real odds > 1.0 and a settled W/L/P result; the other only requires edge ≥ 0) — a real, pre-existing difference in the codebase. Silently merging them would have changed displayed values, which this phase's explicit constraint forbids. Kept as two named shared builders, `buildEdgeBuckets()` ("loose") and `buildEdgeBucketsStrict()` ("strict"), both exposed on `buildAnalyticsDataset()`'s return object as `byEdge`/`byEdgeStrict`, with a code comment at the strict builder explaining why the two must stay distinct.
- Every consumption site that sorts or reverses a shared, now-cached array was audited for mutation safety (`.sort()`/`.reverse()` mutate in place) — two sites needed an explicit `[...arr]` copy added before sorting (`renderMarketIntelligence()`, Strategy Validation's Market Validation sub-section) where the original code's own `.map()` step had incidentally been providing array freshness before its `.sort()`, and that `.map()` no longer exists once the shared array already carries the needed shape.

**Explicitly not changed:** any displayed value, metric, or layout (verified — see below); `buildSeasonArchiveObject()`'s own independent `buildAnalytics()` snapshot (a different, deliberately separate consumer outside the Analytics tab, per this phase's scope); `renderPerformanceOverTime()` (doesn't share this duplication pattern); Season Close, backups, R2, Railway, GitHub persistence, or any Python backend code.

**Verification:** `node --check` on the extracted `<script>` block: OK. A deterministic, seeded-PRNG Playwright (Chromium) snapshot of the entire `#tab-analytics` panel's `innerHTML`, captured against a rich synthetic dataset (90 bot picks across 4 leagues/2 markets, 20 manual bets, 8 league_stats rows) both **before** and **after** the refactor, are **byte-for-byte identical** (86,010 characters, identical hash) — proving zero visual or data change. Full Python suite: **430/430 passing**, unchanged. QuantEngine golden vectors: **285/285**, unchanged (both expected, since this is a JS-only, Analytics-only change). No new committed test file — Playwright is not a repository dependency (confirmed: no `package.json` exists) and every prior phase's DOM-regression scripts have stayed scratchpad-only, consistent with ADR-005 (no build step) and this project's "keep changes as small as practical" principle; the byte-for-byte snapshot diff above is this phase's validation evidence instead.

**Performance impact:** before this phase, a single Analytics-tab render triggered roughly a dozen independent `buildAnalytics()` calls (3 fields × ~4 call sites) plus ~4 separately-written inline edge/odds/weekday/hour bucket computations and 2 independent `computeStreaks()` calls, all unmemoized and all re-executed on every render, including renders where nothing about the underlying data had changed. After this phase, each dataset's aggregate bundle is computed exactly once per data generation (cached by the existing `_dataGeneration` counter) and shared by reference across all 12 sections — the same reduction in duplicate work this project's Phase 26.39 memoization already achieved for the History/Bank/Home data layer, now extended to Analytics specifically. No new dataset, no new persistence, no backend change; memory impact is one additional cached object (`{ allTime, currentSeason }`) per data generation, replacing what were previously a dozen-plus independently-held, larger arrays recomputed from scratch each time.

**Scope:** dashboard render layer only, Analytics tab only. No settlement, generation, backup, persistence-format, or backend change. This phase is preparatory architecture for the dual-view (Current Season + All-Time) Analytics UI Phase 29.1 designed — that UI itself is not implemented yet. Documentation updated: `03_Dashboard.md` §10 (Analytics), this Change Log, `07_Current_Status.md`, and a new session handover.

---

## Phase 28.5 — End-of-Season Season-Boundary Integration

**Implemented:** 2026-08-04

**Background — Phase 28.4 (read-only architecture audit, same day):** investigated a report that, after cloud sync and boot-time sync were both already confirmed correct (Phase 28.3/28.3A), Bank and History still showed the previous season's data post-close. A complete trace of every page's data source found: Season Close never touches `picks_history.csv` (a permanent, cross-season record by design — confirmed via `06_Roadmap.md`'s MT-4/DX-4 entries, which explicitly describe "History, Analytics, and Bankroll would scope their data to the selected season" as a still-pending piece of that feature). The dashboard's own `isOnOrAfterSession()` primitive already existed and was already correctly used by `getMetrics()`'s `sessao` bundle and by Strategy Lab's default "Época Atual" filter — but `getFilteredRealClosedRows()` (History/Home/Bank's evolution chart), `getBankrollState()` (Bank's documented single source of truth), and `renderVersus()` (Bot vs Manual, and by inheritance the entire Opinion suite via `window._opnSimCache`) never consulted it. Conclusion: not a Season Close defect, not a data-loss issue — a dashboard-side gap in an already-partially-built feature (DX-4), affecting 4 pages through what turned out to be exactly 2 architecturally central functions plus one large function's own internal duplication.

**Fix (`index.html` only, reusing existing infrastructure exclusively):**
- Two new shared, memoized helpers next to `getResolvedManualBets()`: `getSessionRealResolvedBotHistory()` / `getSessionResolvedManualBets()` — each a one-line `.filter(isOnOrAfterSession(...))` wrapper around the existing all-time getters. No new filter logic; both are the *only* place `isOnOrAfterSession()` is now applied to these two pools.
- `getMetrics()`'s `sessao` bundle now calls these two helpers instead of its own inline filter — removing that duplication and making it the first of several consumers of the new shared path.
- `getBankrollState()` — documented as *"the single source of truth for all bankroll values; every page and widget must consume this"* — now sums `getSessionRealResolvedBotHistory()`/`getSessionResolvedManualBets()` instead of the all-time getters it previously (and independently) recomputed from scratch. The per-row profit formula itself (`_lucroRealLocal ?? _lucroModeloLocal`) is unchanged; only the season boundary was added — a formula-divergence between this and `buildMetricsBundle()`'s own `realBotProfit` (which has no such fallback) was found during implementation and deliberately left alone as a separate, pre-existing, out-of-scope issue, not conflated with this fix.
- `renderBankrollPerformanceBreakdown()` (Bank's origin/breakdown widget) and `renderBankrollAudit()` (`.geral` → `.sessao`) updated for the same consistency.
- `renderVersus()` (Bot vs Manual): its top-level `botRows`/`manualRows` now use the two new helpers. The function's own body independently re-derived `getResolvedManualBets()` 7 more times further down (score-band calibration, Opinion Validation's `opinionBets`, Edge Realization, and 3 re-derivations inside the Model Health block) — all 7 now reuse the single top-level `manualRows` variable, collapsing 8 independent computations of the same pool into 1 and applying the season boundary uniformly. Since `window._opnSimCache` is populated from this same `opinionBets`, **Opinion Validation, Opinion Engine Recommendations, and the Recommendation Simulator all became season-aware automatically, with zero code changes of their own** — they were already correctly designed to consume `renderVersus()`'s output rather than re-deriving anything (verified: no other function anywhere in the file independently calls `getResolvedManualBets()` or `getRealResolvedBotHistory()` outside `renderVersus()`, `getMetrics()`, `getBankrollState()`, `getFilteredRealClosedRows()`, `renderBankrollPerformanceBreakdown()`, `renderHistoryIntelligence()`, and the Analytics-tab functions — a complete grep-verified inventory, not an assumption).
- `getFilteredRealClosedRows(filters, sessionOnly = false)` gained one optional parameter — a uniform final filter (`isOnOrAfterSession(r.date)`) applied only when `sessionOnly` is `true`. Exactly 4 of its ~20 call sites now pass `true`: `getHistoryFilteredRows()` (History), `renderSummaryHeadlineStats()` and `renderBankrollChart()` (Dashboard Home), `renderBankrollEvolution()` (Bank). Every other call site — `buildSeasonArchiveObject()` (the archive snapshot), `renderLeagueAnalytics()`'s enrichment call, all 11 other Analytics-tab sub-renderers, `csmGoStep4()` (the Close Season wizard's own review step), and `renderMobileHomeDash()` (already date-filtered to "today" — no change needed there) — was left as a bare call with no flag, i.e. byte-identical behaviour to before this phase. `renderHistoryIntelligence()`'s separate "highest edge" anomaly card (`getRealResolvedBotHistory()` → `getSessionRealResolvedBotHistory()`) was the one additional History-page call site found outside `getHistoryFilteredRows()` itself.
- `exportRealCsv()` now calls `getHistoryFilteredRows()` directly instead of an independent, slightly different `getFilteredRealClosedRows(getHistoryFilters())` call — the export always matches the table exactly (and, as a side effect, now respects the odds-range filter it previously silently ignored).

**Explicitly not modified, per this phase's scope:** `executeSeasonClose()`, `csmExecute()`/`csmGoStep4()` (Season Close flow), `buildSeasonArchiveObject()` (archive generation), the backup subsystem/R2/Railway/GitHub persistence, cloud synchronization, and Strategy Lab's own pre-existing `getStrategyLabPool(seasonMode)` season filter (confirmed working correctly and left completely untouched). Analytics (`league_stats.csv`) is unchanged and remains all-time by architecture, since `src/league_stats.py` has no `sessionStartDate` concept anywhere in the Python backend — closing that gap would require a backend redesign, explicitly out of scope for this phase and documented as such rather than attempted.

**Verification:** `node --check` on the extracted `<script>` block: OK. Full Python suite: **430/430 passing**, unchanged. QuantEngine golden vectors: **285/285**, unchanged. Real-browser (Playwright/Chromium, network fully mocked/deterministic, driving the real unmodified `index.html`) regression, **27/27 assertions across 3 scenarios**:
1. **Immediately after Season Close** (old-season bot pick present in the underlying store, no new-season activity yet): History page empty; Dashboard Home summary rows and DOM both show zero/empty; Bot vs Manual KPI row shows no non-zero counts; Bank shows current bankroll = starting bankroll, P/L = €0, global result = €0, session ROI = 0%, session W/L = 0/0, session resolved count = 0; the evolution chart shows its "no data" empty state rather than replaying pre-close history; the old-season row is confirmed still present in `getHistoryRowsMerged()` (the all-time, undeleted store); no unexpected `POST /save` fired.
2. **A new-season bet correctly appears** (one new bot pick + one new manual bet, both dated on/after `sessionStartDate`): History page shows exactly the 2 new-season rows, old one excluded; Bank bankroll reflects only the new-season wins; `sessao` resolved count = 2; `.geral` (the untouched all-time bundle Analytics/the archive still use) correctly still sees all 3 bets; `window._opnSimCache`'s `opinionBets` correctly contains exactly the 1 new-season manual bet.
3. **Regression**: Strategy Lab's own season pool, Pending, Live Center, Manual Bets (operational list), and Daily Picks all compute without error and are unaffected; Analytics's enrichment call is confirmed to still see the full all-time pool (all 3 bets) and renders without error, proving it is genuinely untouched, not just "probably fine."

**Scope:** dashboard read/render layer only. No settlement, generation, backup, or persistence-format change. Documentation updated: `03_Dashboard.md` (Home/Summary, History, Analytics, Bankroll, Bot vs Manual sections), `05_Known_Issues.md` (new `DASHBOARD-8`, resolved), `06_Roadmap.md` (DX-4 updated from "Deferred" to "Partially done"), `07_Current_Status.md`, this Change Log, and a new session handover.

---

## Phase 28.3A — Fix Boot-Time Season Synchronization

**Implemented:** 2026-08-04

**Background — Phase 28.3 (read-only audit, same day):** investigated a report that the dashboard showed the old season immediately after a successful End-of-Season execution. Fetched the live production Railway `/load` response directly (`GET https://apostas-over-futebol-production.up.railway.app/load`, read-only) and confirmed `cloud_state.json` already held the correct new season — `sessionStartDate: 2026-08-03`, a round starting bankroll, zero `manualBets`/`movements`/`localEdits`. `sync_server.py`'s `/load` does a live, uncached `GET` against the GitHub Contents API on every request (`get_file_from_github()`), so Railway can never itself be the stale layer. **Conclusion: no production data was lost.** The defect was entirely in `index.html`'s boot sequence.

**Root cause:** `boot()`'s auto-recovery gate, `if (!hasMeaningfulLocalState())`, is a one-time "is this a brand-new/anonymous browser" check. `hasMeaningfulLocalState()` returns `true` for any browser that has ever had a bankroll configured — forever — so the full cloud-recovery path (`_doLoadCloudState()`, which restores `bankrollInicial`/`sessionStartDate`/`localEdits` alongside `manualBets`/`movements`) was skipped unconditionally on every subsequent boot for a returning browser, regardless of how much newer the cloud's season had become. Such a browser instead fell to `_reloadManualBetsFromCloud()`, which only patches `manualBets`/`movements`/`providerHealth` — leaving `bankrollInicial`/`sessionStartDate`/`localEdits` stuck on the old season, producing a visibly inconsistent, part-old/part-new dashboard. The browser/tab that actually executed Season Close was never affected: `executeSeasonClose()` writes the new season directly into its own `localStorage` (Steps 8–9) before the cloud push (Step 12), and `csmExecute()` re-renders the already-updated in-memory `state` immediately (`rerenderAll()` at the end of the modal flow) — this defect only ever affected *other* browsers, tabs, or devices carrying their own pre-existing local season data.

**Fix (`index.html` only):**
- New `isCloudSeasonNewer()` — a single read-only `GET /load`, comparing `content.sessionStartDate` to `state.sessionStartDate` (identical string-comparison style to the existing manual "Load Cloud" recency guard) and returning a boolean. Mutates nothing — no `state` write, no `localStorage` write, no render.
- `boot()`'s auto-recovery gate: when `hasMeaningfulLocalState()` is `true` (previously the unconditional end of the story), it now additionally calls `isCloudSeasonNewer()`. If the cloud season is strictly newer, it calls the **same, unmodified** `_doLoadCloudState({ fromUser: false })` used by the brand-new-browser branch — no second implementation of the recovery logic. If the cloud season is the same age or older, behaviour is byte-for-byte identical to before this phase: the local snapshot is kept.
- Updated one now-inaccurate comment inside `_doLoadCloudState()` (the `fromUser` recency-guard block) to reflect that its "cloud is never older when `fromUser` is false" invariant is now guaranteed by two independent boot-time checks instead of one.
- `executeSeasonClose()`, `saveCloudState()`, and the manual "Load Cloud" button's own `fromUser: true` recency guard were **not modified**, per this phase's explicit scope.

**Verification:**
- `node --check` on the extracted `<script>` block: OK.
- Full Python suite: **430/430 passing** (unchanged — this is a JS-only change). QuantEngine golden vectors: **285/285** unchanged.
- Real-browser regression (Playwright/Chromium, network fully intercepted/deterministic, driving the actual unmodified `index.html` and its real `boot()`/`hasMeaningfulLocalState()`/`isCloudSeasonNewer()`/`_doLoadCloudState()` — not a reimplementation): **6 scenarios, 22 assertions, all passing**:
  1. The browser that executed Season Close, reloaded (local == cloud, both the new season) — unchanged, no full recovery needed.
  2. A second browser that never ran the close — real old local season, newer cloud season — now correctly adopts the new season in full (bankroll, sessionStartDate, manualBets, movements, localEdits, and the recovered value is persisted back to localStorage).
  3. A fresh/anonymous browser with no localStorage at all — unaffected, exercises the pre-existing `!hasMeaningfulLocalState()` branch.
  4. A browser with very old, minimal local state (bankroll-only signal, no manual bets/movements) — correctly recovers the newer cloud season.
  5. A browser with a genuinely unsynchronised local edit under the *same* season as the cloud (simulating an offline edit not yet pushed) — correctly left untouched, since `isCloudSeasonNewer()` returns `false` when seasons match; this is the existing protection, unchanged.
  6. A browser whose local season is *newer* than the cloud's — correctly left untouched (protects local work; mirrors the manual "Load Cloud" button's own existing guard).

**Scope:** dashboard boot sequence only. Settlement, generation, backup subsystem, and every other dashboard page/feature are untouched. Documentation updated: `00_Project_Context.md`, `01_Architecture.md`, `02_Data_Flow.md`, `03_Dashboard.md`, `05_Known_Issues.md` (new `DASHBOARD-7`, resolved), `07_Current_Status.md`, this Change Log, and a new session handover.

---

## Phase 28.2 — Integrate Four Requested Leagues; Three Were New, One Already Existed

**Implemented:** 2026-08-03

**Requested:** Switzerland Super League, Spain LaLiga Hypermotion (Segunda División), France Ligue 2, Portugal Liga Portugal 2 "Meu Super" — as full first-class production leagues, following the documented `04_Backend.md` "Adding a new league" checklist, no shortcuts, no duplicated code, no temporary solutions.

**Task 1 — Discovery:** queried API-Football's `/leagues` endpoint live (2026-08-03) for Switzerland, Spain, France, and Portugal. Found France Ligue 2 (`af_id=62`) **already a fully active, first-class league** — `src/league_registry.py`'s `franca2` entry, registered in `config.json`'s `leagues`/`api_football.league_ids`, with a 549-row `data_raw/franca2.csv`. A targeted audit (dashboard `LEAGUE_NORMALIZE`, filter dropdowns — dynamically populated, no hardcoded per-league entries needed — `league_stats.py` analytics, backup file manifest, standings — a feature this project does not have at all, for any league) found no hidden gap. Re-adding it was rejected as a duplicate-source-of-truth violation of ADR-004; confirmed with the user before proceeding. The three genuinely new leagues, confirmed against live `/leagues` season-coverage data (fixtures/lineups/statistics/standings all `true` for the two most recently completed seasons, matching every other production league's coverage profile):
- Switzerland Super League — `af_id=207`, `"european"` season model (season runs Jul–May).
- Spain Segunda División — `af_id=141`, `"european"` season model (season runs Aug–Jun).
- Portugal Liga Portugal 2 — `af_id=95` (API-Football's own name: "Segunda Liga"), `"european"` season model (season runs Aug–May).

Display names: the request volunteered each competition's current sponsor-branded name ("LaLiga Hypermotion", "Liga Portugal 2 Meu Super"). Confirmed with the user before implementation: every existing registry entry uses the stable, sponsor-free competition name (e.g. `"LaLiga"` not `"LaLiga EA Sports"`), so `"Segunda División"` and `"Liga Portugal 2"` were used instead — sponsor names change periodically; CSV/history `Liga` values should not.

**Task 2 — Backend integration:**
- `src/league_registry.py`: added 3 `LeagueEntry` rows (`suica`, `espanha2`, `portugal2`), `code` set to the key itself (post-Phase-27.4 convention — no football-data.org legacy code exists for these).
- `config.json`: added the 3 leagues to `leagues` and `api_football.league_ids`. Added a new `historical.seasons_by_league` entry for each (`[2024, 2025]`) — without it, `fetch_historical.py`'s default month-based season fallback would have selected only the "current" 2026/27 season, which had ~0 finished matches on 2026-08-03 (all three seasons had just started or not yet started), producing an almost-empty history file.
- `fetch_oddsapi_fixtures.py`: added the 3 leagues to `DEFAULT_LEAGUE_IDS` — a redundant fallback dict consulted only if `config.json` is missing an entry. Found, during the audit, that every one of the 22 pre-existing leagues already has an entry here despite this never being a documented step; added to the `04_Backend.md` checklist as a discovered gap. Deliberately did **not** add entries to `LEAGUE_INFO_EXT` (feeds `search_league_id_by_api()`, confirmed dead/unreachable in the real fixture-fetch path since Phase 26.42 — no EU league, including the pre-existing `franca2`, has ever been in it either).
- `fetch_historical.py`: added 3 `LEAGUE_INFO` entries (name/country/id), then ran the fetch scoped to only these 3 keys (not the full script, which would have re-fetched and diffed the other 22 leagues' existing files unnecessarily) against real, live API-Football data. Results: `data_raw/suica.csv` (459 rows, seasons 2024+2025), `data_raw/espanha2.csv` (935 rows), `data_raw/portugal2.csv` (615 rows) — all in the exact `Date,HomeTeam,AwayTeam,FTHG,FTAG` schema `compute_lambdas()` (`src/calculations.py`) actually consumes (verified by reading the function; the extra betting-odds columns present in some older EU leagues' football-data.co.uk-sourced files, e.g. `franca2.csv`, are confirmed unused). `data_raw/*.csv` is gitignored by pattern (`.gitignore:17`); the 3 new files were `git add -f`'d, matching how every existing league's history file is a tracked exception to that pattern.
- `index.html`: added canonical (`suica`→`suica`) and display-name-alias (`'super league'`→`suica`, etc.) entries to `LEAGUE_NORMALIZE`. Filter dropdowns needed no change — confirmed dynamically populated from data (`<option value="">Todas as ligas</option>` is the only static option in the source).
- Three purely cosmetic, debug-log-only "EU leagues" set literals (`main.py`'s `_trace()`/`_trace_dropped()`, `src/market_rules.py`, `src/pick_generation.py`'s `verbose` flag) were extended with the 3 new keys for consistency, after confirming by reading every call site that none of them gate real filtering, staking, or generation eligibility — only trace-log verbosity.
- Backup compatibility: confirmed by inspection — `config.json["backup"]["files"]` and `src/backup/backup_engine.py`'s `create_backup()` are filename-based, not league-based; new-league data flows through the same `picks_history.csv`/`league_stats.csv` files as every other league, no change needed.

**Task 3/4 — Generation and settlement pipeline verification** (against the real code paths, not a re-implementation):
- `compute_lambdas()` (`src/calculations.py`) run directly against the new `data_raw/espanha2.csv` with two real teams — produced sane, non-degenerate lambda values, confirming Poisson-engine compatibility end-to-end.
- `update_results.get_api_football_league_id()` and `api_football_season_from_date()` (the real settlement functions) called directly for all 3 leagues — resolved the correct `af_id` from the registry (no `/leagues` API call needed, confirmed via debug log) and the correct season (`2026-02-15` → season `2025`, matching the `"european"` model).
- `update_results._resolve_liga_display_name()` (manual-bet settlement's league-name resolution) verified correct for all 3 keys.
- Live `/fixtures` query confirmed real upcoming fixtures exist for all 3 leagues (e.g. Switzerland: Lausanne vs BSC Young Boys, 2026-08-08). Live `/odds` query confirmed odds are already posted for the nearest Swiss fixture (10 bookmakers); not yet posted for the Spanish/Portuguese fixtures checked (both seasons start 1–2 weeks later) — expected, normal pre-season timing, not a defect; the existing zero-odds fixture filter (generic, no per-league logic) already handles this for every league.
- `src/league_stats.py`'s `update_league_stats()` run against a synthetic history file containing rows for all 3 new leagues (scratch files only) — produced correct, generically-computed ROI/WinRate/Tier figures, confirming zero per-league special-casing in analytics.

**Task 5 — Dashboard verification:** booted the real `index.html` (served locally over HTTP so relative CSV fetches behave like production hosting; all data fetched live from the real Railway/GitHub URLs already hardcoded in the file) and ran `normalizeLeagueCode()` in-page for all 3 new leagues' canonical keys and display names, plus a pre-existing sanity check (`"ligue 2"` → `franca2`) — all 7 assertions passed, zero JS console errors, zero layout regressions (screenshot-verified).

**Task 6 — Testing:** added `tests/test_phase28_new_leagues.py` (12 new tests: registry entries, derived structures, `config.json` wiring, `NON_EU_TOPUP_LEAGUES` exclusion, settlement league-ID/season-model resolution via the real code path, manual-bet display-name resolution, `data_raw` schema and row-count sanity). Full suite: **430/430 passing** (418 pre-existing + 12 new). QuantEngine golden vectors: 285/285 unchanged. `node --check` on the extracted `<script>` block: OK.

**Task 7 — Documentation:** updated `00_Project_Context.md`, `01_Architecture.md`, `04_Backend.md` (league counts 22→25, "Adding a new league" checklist gained the `DEFAULT_LEAGUE_IDS` and `historical.seasons_by_league` steps discovered during this phase's audit, API request-volume math recalculated), `PROJECT_MAP.md`, `09_Architecture_Decisions.md` (new "Update (2026-08-03, Phase 28.2)" section on ADR-004), `07_Current_Status.md`, this Change Log, and a new session handover.

**Task 8 — Final safety audit:** no production runtime data file modified — `cloud_state.json`, `picks_history.csv`, `picks_hoje*.csv`, `picks_over25.csv`, `picks_btts.csv`, `fixtures_today.csv`, `sent_state.json`, `team_alias_cache.json`, `league_stats.csv`, and every pre-existing `data_raw/*.csv` show zero diff — confirmed via `git status`/`git diff --stat`. No generation or settlement was executed. No duplicated code introduced — every touch point was verified to be the single, registry/config-derived source already used by every other league (confirmed via direct grep audits and live execution of the real registry/settlement/analytics functions, not assumption).

**Scope:** Ligue 2 unchanged (already complete, deliberately not touched). No change to settlement engine internals, QuantEngine, the backup subsystem's own logic, or any other league's data/behaviour.

---

## Phase 27.4 — Remove football-data.org Completely

**Implemented:** 2026-08-02

**Preceded by:** a read-only dependency audit (this session, prior to any code change) establishing that football-data.org was first-attempt provider for only 6 of the 22 registered leagues, with API-Football already the fallback — and therefore proven, complete — provider for all of them, including those 6. The decision was made to remove football-data.org entirely rather than keep an unused redundancy path.

**Trigger for this session:** an explicit architectural-simplification instruction: remove football-data.org completely while preserving every existing feature and behaviour. Absolute requirements: do not redesign the settlement engine, do not split `update_dataframe()`, do not introduce a second provider, do not change business logic — only remove football-data.org and simplify.

**Task 1/2 — Settlement engine (`update_results.py`):**
- Removed every football-data.org-specific function and constant: `classify_fd_status()`, `should_use_api_football_fallback()`, `http_get_json_football_data()`, `fetch_matches_for_league_date()`, `_respect_fd_api_spacing()`, `_fd_last_api_call_ts`, `FD_MAX_RETRIES`, `FD_BASE_SLEEP`, `FD_CALL_MIN_INTERVAL`, `FD_FINISHED_STATUS`, `FD_IN_PROGRESS_STATUS`, `FD_NON_PLAYED_STATUS`, `FD_SUSPENDED_INTERRUPTED_STATUS`, `FD_VOID_REASON_BY_STATUS`, and `API_TOKEN` (the `FOOTBALL_DATA_API_KEY` env read).
- `make_shared_runtime_state()` no longer carries `fd_matches_cache`/`blocked_fd_leagues_seen`.
- The routing block inside `update_dataframe()` — originally ~180 lines selecting between football-data.org and API-Football per league, per row — collapsed to a single unconditional `_run_af_and_account(i, row, league_code, "API_FOOTBALL")` call. `_run_af_and_account()` itself (the nested closure that already fully accounted for `NO_MATCH`/`TOO_EARLY`/`NOT_FINISHED`/`UNSUPPORTED_MARKET` bookkeeping) was **not modified** — it was already fully generic. `update_dataframe()` was not split.
- Startup gates changed from a hard `FOOTBALL_DATA_API_KEY` check (with a soft `API_FOOTBALL_KEY` warning) to a single hard `API_FOOTBALL_KEY` gate, in both `run_settlement_remote()` and `main()`.
- Deliberately **not** touched: `get_fixture_status()`, `get_fixture_score()`, `get_fixture_kickoff_dt()` — these are generic dual-shape parsers still actively used by API-Football responses; their dormant football-data.org-shaped branches (e.g. `fixture.get("utcDate")`) were left in place rather than risk a redesign for a cosmetic-only cleanup.

**Task 3 — League registry (`src/league_registry.py`):**
- Removed the `fd_code`/`fd_blocked` fields from `LeagueEntry`, the `_settlement_code()` helper, and `BLOCKED_FOOTBALL_DATA_CODES`.
- Every league's internal routing `code` value (used throughout settlement as an opaque identifier) was deliberately preserved byte-for-byte — e.g. `"PL"` for premier, `"PPL"` for portugal — even though these values originated as football-data.org codes; this was a zero-behaviour-change decision, not a cleanup opportunity.
- `API_FOOTBALL_FALLBACK_COMPETITIONS` renamed to `API_FOOTBALL_COMPETITIONS`, now built unconditionally from `af_id` (every league has one; the field is no longer optional). `AF_SEASON_MODELS`/`LEAGUE_CODE_MAP` simplified to match. All 22 leagues — including MLS (`af_id=253`) and MLS Next Pro (`af_id=909`) kept fully independent — preserved with identical names/ids/season models.

**Task 4 — Configuration:**
- Removed `FOOTBALL_DATA_API_KEY` from the local `.env`, from `.env.example`, and from all three jobs' `env:` blocks in `.github/workflows/bot.yml` (`settlement`, `main-generation`, `topup`).
- After this phase, `API_FOOTBALL_KEY` is the only result-provider credential referenced anywhere in the repository.

**Task 5 — Dashboard (`index.html`):**
- Removed the 13-entry football-data.org competition-code block from `LEAGUE_NORMALIZE` after confirming every canonical key it mapped to is already covered by the dashboard's other normalisation entries.
- Removed the `'football-data.org': 'football-data.org'` entry from `PROVIDER_HEALTH_LABELS` after confirming the existing fallback pattern (`PROVIDER_HEALTH_LABELS[provider] || provider`) produces byte-identical output for that key even with the entry removed — including for any stale `providerHealth` record already present in a real account's `cloud_state.json` from before this phase.
- `node --check` on the extracted `<script>` block passed; `node tests/test_quant_engine_golden.js` — 285/285 passing (QuantEngine untouched).

**Task 6 — Repository-wide audit:** grepped the entire repository for `football-data`, `football_data`, `FOOTBALL_DATA`, `fd_code`, `fd_blocked`, `football-data.org`, and `FD provider`. All dead references in source, config, and tests were removed. Remaining references are confined to: (a) explanatory prose in documentation describing the removal itself, (b) the git history of already-closed historical Change Log/handover entries, which are point-in-time records and are not rewritten.

**Task 7 — Documentation:** updated `09_Architecture_Decisions.md` (a new "Update (2026-08-02, Phase 27.4)" section on ADR-004, plus fixes to ADR-017's status-classification matrix), `01_Architecture.md`, `02_Data_Flow.md`, `04_Backend.md`, `03_Dashboard.md`, `00_Project_Context.md`, `06_Roadmap.md`, `PROJECT_MAP.md`, this Change Log, and a new session handover. `05_Known_Issues.md` was reviewed and deliberately left unmodified — its one remaining football-data.org mention (SETTLEMENT-1) is an accurate historical description of a fix made in Phase 26.18, when football-data.org was still in use; rewriting historical fix descriptions to match current architecture would misrepresent what was actually shipped at the time.

**Task 8 — Testing:** `tests/test_void_policy.py` — deleted `test_fd_suspended_after_48h_remains_unresolved()` (tested the now-removed `fetch_matches_for_league_date()`; fully redundant with the still-passing AF-equivalent test) and removed the football-data.org-specific assertions from `test_suspended_interrupted_classification_falls_through_to_scheduled_unknown()`, keeping its API-Football assertions. `tests/test_mls_league_routing.py` — renamed `API_FOOTBALL_FALLBACK_COMPETITIONS` → `API_FOOTBALL_COMPETITIONS` (4 occurrences). Full suite: 418/418 passing. QuantEngine golden vectors 285/285 unchanged.

**Task 9 — Simplification metrics:** `update_results.py` net -447 lines (2 constants/functions removed: `classify_fd_status()`, `should_use_api_football_fallback()`, plus 4 HTTP/caching helpers, plus ~8 FD-only constants). `src/league_registry.py`: -100/+~65 lines net, 1 field removed from `LeagueEntry`, 1 helper function removed, 1 module-level constant removed. `audit_settlement.py` (diagnostic-only, not wired into any production path): -140 lines, mirroring the same simplification. No files deleted (audit_settlement.py was simplified in place, not removed, since it remains independently useful as a diagnostic tool). Full repository diff: -805/+270 lines across 12 source/config/test files (documentation not included in this count). Settlement routing complexity: a 3-way branch (football-data.org / API-Football-direct / blocked-league fallback) per league per row collapsed to exactly one path.

**Task 10 — Safety audit (explicit confirmation):** no production runtime files modified — `cloud_state.json`, `picks_history.csv`, `picks_hoje_simplificado.csv`, `picks_hoje_github.csv`, `picks_over25.csv`, `picks_btts.csv`, `fixtures_today.csv`, `sent_state.json`, `team_alias_cache.json`, `manual_bets.csv`, `league_stats.csv`, and `data_raw/*.csv` all show zero diff (verified via `git diff --stat` against each by name). No generation or settlement was executed — verified via the absence of any diff to the above files and no network calls made by this session outside the test suite (which runs entirely against local fixtures and mocks). API-Football is now the sole production result provider.

**Scope:** architectural simplification only. Zero change to Generation, Settlement business logic, Manual bets, MLS/MLS Next Pro routing, the Backup subsystem, QuantEngine, or the H1/H2/H3 rendering architecture.

---

## Phase 27.3 — Backup Subsystem Production Hardening

**Implemented:** 2026-08-02

**Preceded by:** Phase 27.2A, a dedicated memory/scalability audit of the Phase 27.2 implementation, which approved the architecture without requiring a redesign but identified one self-contained, quantified bug (restore downloading the same archive twice) and asked for the configuration/error-handling maturity a real production integration needs before real R2 credentials are added.

**Trigger for this session:** complete the subsystem for production readiness — real R2 initialization, the identified restore fix, endpoint/GitHub-Actions review, a security audit, and only the documentation/tests the production integration actually requires. Explicitly: do not redesign, do not execute a real production backup, do not push.

**Task 1/2 — Configuration and R2 initialization:**
- `src/backup/config.py::get_r2_settings()` gained four new, all-optional settings with documented defaults: `region` (`auto`), `connect_timeout_seconds` (10), `read_timeout_seconds` (60), `max_retry_attempts` (3) — each falling back to its default on a missing or invalid value via the same per-key defensive style `get_backup_config()`/`src/config.py::get_void_policy()` already use.
- `load_dotenv()` added to `config.py` (python-dotenv never overrides an already-set variable, so this is a no-op on Railway/GitHub Actions — no `.env` exists on either — and only fills gaps for local development).
- `R2Client.__init__()` now passes `region_name`/`connect_timeout`/`read_timeout`/retry `max_attempts` through to `boto3.client()`, and wraps construction failures (a malformed endpoint/region reaching botocore's own validation) as a classified `R2OperationError` instead of an unhandled crash.
- Every real R2 operation (`put`/`head`/`get`/`delete`/`list`) now routes its exception through one shared classifier, `_classify_and_raise()`, producing exactly one of three new exception types: `R2ConnectionError` (endpoint unreachable — DNS/network/connect-or-read-timeout), `R2PermissionError` (credentials rejected — wrong key, insufficient bucket permission; covers both explicit 403s and `SignatureDoesNotMatch`, which a wrong secret key typically surfaces as), `R2OperationError` (reached R2, credentials accepted, operation still failed for another reason). `R2ObjectNotFoundError` (404) stays separate, as before — expected control flow, not an operational failure. No classified message ever includes a credential value; only R2's own error Code/Message and the object key involved.
- New `.env.example` (committed, placeholder-only values) documents every environment variable this project actually reads (enumerated via a full grep of this project's own source, not guessed), including the new R2 tuning variables.

**Task 3 — Restore double-download fix:**
- `backup_restore.py` gained one internal helper, `_validate_restore_with_bytes()`, shared by both the public `validate_restore()` (still never returns the downloaded bytes — that's the exact shape `POST /backup/validate-restore` serializes to JSON, and raw archive bytes have no business in an HTTP response) and `restore()` (which now reuses that single download instead of fetching the identical object a second time). Integrity verification, restore validation, and GitHub write safety (the mandatory pre-restore safety snapshot, per-file write reporting) are all unchanged in substance — only the redundant second R2 GET was removed.
- Verified via a new precise regression test (`test_restore_downloads_the_archive_exactly_once`) that counts `get_object()` calls *by key*, deliberately excluding `create_backup()`'s own unrelated index-object reads from the count, so the assertion measures exactly what Task 3 asked for — one download of the archive itself per restore, not an incidental total across the whole test setup.

**Task 4 — Endpoint review:**
- The `get_r2_client(get_r2_settings())` + `except R2NotConfiguredError` pattern, previously hand-copied identically across all three action endpoints (`create`/`validate-restore`/`restore`), is now one shared helper, `_r2_client_or_error_response()`. `GET /backup/status` deliberately keeps its own inline handling — reporting "not configured" there is a successful (200) status response, not an error, a different semantic from the action endpoints' 503.
- Every endpoint gained a final `except Exception` fallback beneath its more specific catches (`BackupError`/`RestoreError`), so an unclassified failure (e.g. an `R2ConnectionError` surfacing from a call path that isn't already wrapped) always produces the project's consistent `{"error": "..."}` JSON shape instead of an unhandled 500 with no explanation.
- Authentication was reviewed and **deliberately left unchanged**: no `/backup/*` endpoint has its own auth, matching every pre-existing Railway endpoint in this file (`/save`, `/load`, `/run-settlement`) — none of them have authentication either, relying on CORS and an unguessable Railway URL. Adding authentication to only the backup endpoints would be inconsistent with the existing security model and a larger change than "production readiness for this subsystem" — noted as a whole-system consideration, not fixed here.

**Task 5/6 — GitHub Actions and production-readiness review:**
- `bot.yml`'s `backup`/`backup-integrity` jobs gained the four new optional R2 tuning secrets in their `env:` blocks (referencing a non-existent GitHub Actions secret evaluates to an empty string, which `get_r2_settings()`'s defensive fallback already handles correctly — no YAML-side conditional needed).
- `backup_job.py`/`backup_integrity_job.py` needed no code changes — both already call `get_r2_client(get_r2_settings())` generically, so the new region/timeout/retry settings flow through automatically.
- Retry behaviour reviewed: no bespoke retry mechanism was added at the job level — a failed scheduled backup is retried by the next 6-hourly cron run, matching this project's existing "skip rather than fail, retried at the next scheduled run" philosophy already established for settlement (see `01_Architecture.md` §10) — adding a different mechanism here would be inconsistent, not an improvement.
- Full checklist reviewed against Phase 27.2's implementation with no code changes needed beyond the above: backup creation, catalog update, upload, integrity, restore, retention, Season Archive support (`extraPayload`, unaffected), manual trigger, and scheduler all traced end to end with no architectural regression found.

**Task 7 — Security audit:**
- Grepped every `print()`/log statement in the backup subsystem (`src/backup/*.py`, `backup_job.py`, `backup_integrity_job.py`, `sync_server.py`'s backup endpoints) — none interpolate a settings dict, an access key, a secret key, or a GitHub token; only exception objects, backup ids, filenames, and counts.
- Confirmed `create_backup()`'s index entry and the in-archive manifest (both already existing since Phase 27.2) contain no credential-shaped fields — `id`/`type`/`key`/`createdAt`/`reason`/`sizeBytes`/`fileCount`/`githubCommitSha`/`manifestSha256` only.
- Added a dedicated test file (`tests/test_backup_r2_production.py`) that constructs a distinctive fake secret value and asserts it never appears in: a `R2PermissionError` raised from a simulated `SignatureDoesNotMatch`, a `R2NotConfiguredError`'s "missing fields" message (which names only the missing field, never its value), the full `BackupError` chain from a simulated upload denial through `create_backup()`, or any field of a successful backup's manifest/index entry.
- **Incidental, unrelated finding during the configuration-source audit:** `.env` — containing real `FOOTBALL_DATA_API_KEY`/`API_FOOTBALL_KEY` values — was tracked in git and present at `HEAD`. A GitHub API check (`GET /repos/jorgepita/apostas-over-futebol`) confirmed this repository is **public** (`"private": false`), meaning both keys have been live and publicly visible. Fixed prospectively this phase: `git rm --cached .env` plus a new `.gitignore` entry (with an explanatory comment) — the local working copy is untouched, only future commits are protected. **Not** fixed: the exposed values remain in this repository's git history; scrubbing them requires rewriting history and force-pushing a public repository, a decision explicitly left to the repository owner, not taken unilaterally. **Recommended as an urgent, separate action:** rotate both keys at their respective providers.

**Task 8 — Testing:** 20 new tests — 13 in `test_backup_r2_production.py` (config parsing for the four new settings; `_classify_and_raise()`'s classification for connection/permission/generic/not-found cases; the four security-verification tests described above), 4 new/rewritten in `test_backup_restore.py` (the exactly-once download regression test and its `validate_restore()` sibling, a check that `validate_restore()`'s return shape never contains raw bytes, and a fix to a pre-existing intermittently-flaky test — `test_list_backups_sorted_newest_first` compared two real-time-generated ids that could tie at millisecond resolution; now uses explicit, deterministic ids), and 4 new in `test_backup_endpoints.py` (the two new sync_server.py error-response paths, for both the "R2 client construction fails unexpectedly" and "a classified R2 error surfaces mid-operation" cases). Full suite: 419/419 passing (399 pre-existing + 20 new). QuantEngine golden vectors 285/285 unchanged (no dashboard file was touched this phase).

**Task 9 — Documentation:** updated only what this phase actually affected — `09_Architecture_Decisions.md` (a "Production Hardening" addendum to the existing ADR-020, not a new ADR — this phase extends and hardens that decision, it does not make a new one), `04_Backend.md` §16 (new config table, error types, restore fix, `.env` finding, updated test count), `07_Current_Status.md` (header, new Phase 27.3 narrative, Next Priorities items 15–17), this Change Log, and a new session handover. `01_Architecture.md`/`02_Data_Flow.md`/`03_Dashboard.md` were deliberately **not** touched — nothing structural changed (no new component, no new data flow, no dashboard file was modified this phase).

**Task 10 — Final verification (explicit confirmation):** GitHub remains the production source of truth (unchanged — a backup is a read-only snapshot; restore writes back via the existing `github_put_file()` Contents API primitive, now via one shared download instead of two). R2 remains archive storage only (still never read at runtime by generation/settlement/the dashboard — only by the backup/restore subsystem itself). Railway never stores backup archives (unchanged — every archive is still built as a single in-memory buffer, never written to disk, this phase's error-classification work operates entirely on already-in-flight requests/responses, never introducing a disk write). Restore still writes through the existing GitHub persistence mechanism (unchanged — `github_files.write_file()` → `update_results.github_put_file()`, the identical pre-existing primitive). No new persistence subsystem was introduced (this phase added configuration, error classification, and a bug fix — zero new storage, zero new data model, zero new API beyond the four endpoints Phase 27.2 already added).

**Scope:** production-hardening only. Zero change to bot pick generation, settlement, Kelly staking, the manual bet lifecycle, `index.html`, or any dashboard rendering/calculation path.

---

## Phase 27.2 — Backup & Disaster Recovery Implementation

**Implemented:** 2026-08-02

**Preceded by:** a read-only forensic audit (2026-08-02, not itself a phase) establishing this project had no backup or disaster-recovery subsystem at all — the only durability for `cloud_state.json`/the picks CSVs was GitHub's own commit history, and the dashboard's Season Archive feature wrote exclusively to browser `localStorage`; and a Phase 27.1 architecture-only design report (no code) proposing Cloudflare R2 as the permanent backup archive, explicitly informed by a real production incident in this project's user's sibling codebase (`basketball-over-bot`), whose own backup system once exhausted Railway's persistent volume by treating it as long-term storage.

**Trigger for this session:** implement the Phase 27.1 design exactly as specified, with the explicit constraint that Railway must never accumulate backup bytes regardless of backup count, and full backward compatibility with existing (working) End-of-Season behaviour must be preserved.

**Architecture decisions confirmed with the user before writing code:** (1) a hybrid scheduling model — GitHub Actions cron for routine `scheduled` backups (reusing this project's existing, only scheduler), Railway endpoints for `manual`/`critical` backups (the two types that must be triggered synchronously from a real user action); (2) since no Cloudflare R2 bucket or credentials exist in this environment, the real `boto3`-based client was implemented in full, validated against an in-memory `FakeR2Client` double throughout the test suite, with live upload/restore against a real bucket explicitly deferred until credentials exist.

**Implementation (Task 1 — Backup Engine):**

- `src/backup/backup_validator.py` — `build_manifest()`/`build_archive()` (one `zipfile.ZipFile(io.BytesIO())` buffer, never written to disk) and `validate_archive()` (ZIP structure, required manifest fields, per-file SHA-256 re-verification — distinguishes `healthy`/`warning`/`corrupted`).
- `src/backup/r2_client.py` — `R2Client` (boto3 S3-compatible, lazily imports `boto3` so it's never required unless R2 is actually configured) and `FakeR2Client` (an in-memory double implementing the identical interface — put/head/get/delete/list plus one-shot fault injection — mirroring the `basketball-over-bot` project's own `r2Replication._setTestMode()` precedent, adapted for this project's Python stack).
- `src/backup/backup_engine.py::create_backup()` — the create→upload→verify→index→retention cycle. Uploads, then HEAD-verifies; a size mismatch triggers best-effort cleanup of the unverified object and raises `BackupError` without ever indexing it. `files` is always caller-supplied (never fetched internally) so the identical engine serves both the GitHub Actions path (files already on disk) and the Railway path (files fetched fresh via the Contents API) with no duplicated upload/verify/index logic between them.
- `src/backup/backup_index.py` — the R2-hosted catalog (`backups/index.json`), read-modify-write (documented, accepted race risk given this project's actual write cadence — see "Known limitations" below).
- `src/backup/backup_retention.py::run_retention()` — index-based (never a bucket-listing scan for the eviction decision — a `basketball-over-bot`-derived lesson: a listing-derived view would make a `REMOTE_ONLY`-equivalent backup invisible to eviction forever), per-type: 60-entry count cap for `scheduled`, 90-day age cap for `manual`, unlimited by default for `critical`. Eviction is always R2-object-then-index-entry; a failed R2 delete keeps the index entry rather than orphaning the object.
- `src/backup/backup_restore.py` — `rebuild_index_from_r2()` (every call rebuilds the catalog fresh from R2's own listing — Railway has nowhere durable to cache it between requests, so this isn't a cold-start fallback, it's how the system always works), `validate_restore()` (dry-run — download + validate, write nothing), `restore()` (requires `confirmed=True`; re-validates; takes a mandatory fresh `critical` pre-restore safety snapshot, aborting the whole restore if that snapshot itself fails; writes every archived file back to GitHub, `extra_payload.json` deliberately excluded since it isn't a GitHub-tracked file).
- `src/backup/backup_integrity.py::verify_remote_integrity()` — HEAD-only proactive R2 drift detection. **Deliberately reads the persisted catalog (`backup_index.read_index()`), not a fresh listing** — a listing-derived view can, by construction, never show a deleted object as missing (a real bug caught by this session's own test suite before being fixed, not by static review — see "Bugs found and fixed" below).
- `src/backup/github_files.py` — a thin adapter reusing `update_results.py`'s existing `github_get_file_bytes`/`github_get_sha`/`github_put_file` primitives, imported lazily (matching `sync_server.py`'s own existing convention for `run_settlement_remote`) — not a second GitHub-access implementation.
- `src/backup/config.py::get_backup_config()` — mirrors `src/config.py::get_void_policy()`'s defensive per-key fallback style exactly; `get_r2_settings()` reads five new environment variables only, never `config.json` (the same secret/config separation this project already applies to `GITHUB_TOKEN`).

**Implementation (Tasks 11–14 — Railway endpoints, GitHub Actions, manual/critical triggers):**

- `sync_server.py` gained four endpoints: `GET /backup/status` (optionally `?verify=1` for an on-demand integrity sweep), `POST /backup/create` (`type` must be `manual`/`critical` — `scheduled` is rejected with HTTP 400, since only the GitHub Actions job creates those), `POST /backup/validate-restore`, `POST /backup/restore`. Every handler imports `src.backup.*` lazily inside the request, matching the file's existing `/run-settlement` convention, and holds no module-level state.
- `backup_job.py` (root-level, new) — the GitHub Actions scheduled-backup entry point. Reads files already on disk via `actions/checkout` (no GitHub API call needed for creation). Exits 0 (never fails the workflow) if R2 isn't configured — this repository's actual state as of this phase.
- `backup_integrity_job.py` (root-level, new) — the weekly integrity-sweep entry point. Exits 1 only on a confirmed-missing backup (making the GitHub Actions run visibly fail); a transient check error is a warning, never conflated with confirmed loss.
- `.github/workflows/bot.yml` — two new cron entries (`0 */6 * * *` for `backup`, `0 4 * * 0` for `backup-integrity`) and two new jobs, following the file's existing job structure exactly; `workflow_dispatch` gained matching manual-trigger options. New GitHub Actions secrets required (not yet added — see "Configuration required before activation" below).
- `executeSeasonClose()` (`index.html`) gained a new **Step 0**: `createBackupBeforeSeasonClose(archive)` calls `POST /backup/create {type:'critical', reason:'pre_season_close', extraPayload: archive}` — the season archive object itself, for the first time, gets a durable copy outside `localStorage`. **Deliberately conditional**, not an unconditional hard block: an HTTP 503 (R2 not configured — this repository's actual current state) is tolerated with a console warning only, preserving Season Close's exact pre-Phase-27.2 behaviour; any other failure (R2 configured but the backup genuinely fails) aborts the whole close with nothing changed. This distinction was a deliberate design choice to satisfy this session's explicit "preserve all existing functionality" / "maintain full backward compatibility" requirements — the hard-block behaviour Phase 27.1 originally specified activates automatically the moment an operator adds real R2 credentials, with no further code change.
- New "Backups" dashboard tab (`tab-backups`) — status view, a "Criar Backup Agora" manual-backup button, and a per-backup "Restaurar" flow with three escalating confirmation steps (dry-run validate → `confirm()` with concrete details → a literal `prompt()` requiring the text `RESTORE`) — deliberately the heaviest confirmation gate in this dashboard, since a restore overwrites GitHub's production files. No new modal component was introduced (the dashboard has none — confirmed by the Phase 26.46 audit, unchanged since).

**Configuration:** `config.json["backup"]` (files list, retention caps) and `requirements.txt` gained `boto3`.

**Bugs found and fixed during this session's own test-writing (not by static review):**
1. `src/backup/config.py`'s `_positive_int_or_none()` treated a missing config key (`value is None`) as an unconditional `return None`, rather than falling through to the caller's `default` — meaning `scheduled_max_count`/`manual_max_age_days` silently became `None` (no cap at all) instead of their documented 60/90 defaults whenever `config.json["backup"]["retention"]` omitted a key. Caught by `tests/test_backup_config.py`; fixed by removing the special-cased early return and letting `int(None)` naturally raise into the existing `except`-based fallback.
2. `backup_integrity.verify_remote_integrity()` originally called `backup_restore.list_backups()` (which re-derives its result from a fresh R2 listing) rather than the persisted catalog — meaning an externally-deleted object could never be reported as "missing," because a listing-derived view, by construction, cannot show something that isn't listed as missing; it simply isn't there to iterate over. Caught by `tests/test_backup_integrity.py` (`test_verify_remote_integrity_detects_out_of_band_deletion` initially failed); fixed by switching the function to read `backup_index.read_index()` — the catalog's own *claims* — instead.

**Validation:**
- 100 new Python tests (`tests/test_backup_validator.py`, `test_backup_r2_client.py`, `test_backup_config.py`, `test_backup_index.py`, `test_backup_engine.py`, `test_backup_retention.py`, `test_backup_restore.py`, `test_backup_integrity.py`, `test_backup_github_files.py`, `test_backup_jobs.py`, `test_backup_endpoints.py`) — all against `FakeR2Client` or monkeypatched GitHub primitives, zero real network I/O. Full existing suite re-run alongside them: 399/399 passing (299 pre-existing + 100 new), zero regressions.
- `node tests/test_quant_engine_golden.js` — 285/285 passing, unchanged (no calculation function touched).
- `node --check` on the extracted inline `<script>` content of `index.html` — syntax OK.
- **Not verified:** a real upload/restore cycle against an actual Cloudflare R2 bucket — no bucket or credentials exist in this environment. This is the first thing to validate once an operator provisions them; see `07_Current_Status.md` "Next Priorities."

**Known limitations, documented rather than solved this session (see ADR-020's "Consequences"):** the R2 index write (`backup_index.py`) is a read-modify-write, not a compare-and-swap — a genuinely rare race between two near-simultaneous backup operations could drop one index entry (the R2 object itself would be unaffected and rediscoverable via `rebuild_index_from_r2()`). Accepted given this project's actual backup cadence; flagged for anyone revisiting this if that cadence ever increases materially.

**Scope:** additive infrastructure only. Zero change to bot pick generation, settlement, Kelly staking, the manual bet lifecycle, or any existing dashboard rendering/calculation path — confirmed via the full regression suite and a targeted `git diff` review of every modified file before commit. See ADR-020, `04_Backend.md` §16, `02_Data_Flow.md` §11, `01_Architecture.md`'s new Cloudflare R2 component/failure-boundary/architectural-rule entries, and `03_Dashboard.md`'s new Season Archive/Backups subsections.

---

## Phase 26.46 — Fixture-Level Approval Exposure Warning (Dashboard)

**Implemented:** 2026-07-29

**Trigger:** the dashboard has always allowed a bot pick and a manual bet — or two manual bets, or two bot picks across different markets — to be independently approved on the same real-world fixture, and this remains intentional (a user may deliberately want both an Over 2.5 and a BTTS position on one match). No signal existed, at the moment of approving a *second* bet on an already-exposed fixture, that the user was about to add stake on top of stake already committed to that match.

**Audit first (Part 1 of the request):** a full-file search confirmed exactly one mutation point per approval type — `apostada: true` is set only inside the `.js-bot-approve` click handler in `bindBotTableControls()`; `status: 'approved'` is set only inside `mbHandleRowApprove()` (bound once via `.js-approve-manual` in `bindManualControls()`'s delegated listener). Both were confirmed to be the sole, authoritative mutation paths before any code was written — the gate calls into them, it does not duplicate them.

**Implementation:**

- `fixtureExposureKey(data, liga, jogo)` (`index.html`) — `Date + League + Game`, deliberately excluding Market and Bot/Manual origin. Reuses `manualBetOpportunityKey()`'s exact normalisers (`normalizeDateString()`, `normalizeLeagueCode()`, lowercase-folded `Jogo`) minus the market component — a dashboard-local sibling of ADR-018's Python-side `fixture_id_from_*()` helpers, not a reuse of them (the dashboard has its own client-side row shapes and no existing JS fixture-only identity). `normalizeLeagueCode()`'s exact-map lookup (no fuzzy matching) keeps MLS and MLS Next Pro distinct — verified explicitly by test.
- `getApprovedFixtureExposure(fixtureKey)` — returns every other bet, bot or manual, currently `approved && unresolved` on that fixture, reusing the identical predicates `getRiskMetrics()`'s `stakeOpen` already uses, over the same Phase 26.39 memoized row arrays (`getAllBotRowsMergedUnique()`, `getManualRowsMerged()`) — no new dataset, no full-history recomputation. An unapproved recommendation, a rejected/cancelled bet, and a resolved W/L/P or voided-P bet never count.
- `buildFixtureExposureConfirmMessage(existing, candidateStake)` — PT-PT message: origin/game/market/odd/stake per existing bet, current combined exposure, the candidate's own about-to-be-persisted stake, and the resulting total.
- `confirmFixtureApprovalExposure(data, liga, jogo, candidateStake)` — the shared gate. No exposure → returns `true` immediately, no dialog (byte-identical to pre-Phase-26.46 behaviour). Exposure exists → shows the message via the browser-native `confirm()` (the dashboard has no reusable modal component — confirmed by audit; `manualVoidBet()`'s "Anular aposta" already uses the same pattern) and returns the user's choice.
- Both approval handlers call this gate as the very first thing, before their own existing mutation: `.js-bot-approve`'s `onclick` now looks up the candidate row and its about-to-be-applied `StakeReal` (including a Phase 26.33/26.35 auto-filled "Stake rec." default, if one applies) *before* calling `update()`; `mbHandleRowApprove()` calls it before `state.manualBets[betIdx] = {...}`. In both, returning `false` from the gate returns from the handler immediately — zero mutation.
- Self-exclusion required no dedicated logic: because the gate always runs before the mutation it guards, the candidate bet is provably not yet `approved` at lookup time, so the same predicates that already exclude "not yet approved" bets exclude it automatically.

**Validation:** a new 42-check Playwright script (scratchpad-only, not committed, per project convention) drives the real bound `.js-bot-approve`/`.js-approve-manual` handlers in a real Chromium page (network fully intercepted — no production data touched), covering the complete Part 12 test matrix: no-warning baseline (bot and manual), all four Bot↔Manual/same-and-cross-market combinations, Bot→Bot and Manual→Manual same-fixture warnings, multiple simultaneous existing bets (combined exposure correctly summed and displayed), Cancel (zero mutation, verified on both approval types), Approve Anyway (exactly one mutation, exactly one `confirm()` call), exposure-math correctness (current/candidate/resulting totals), self-exclusion, unapproved/rejected/resolved-W/L/P/voided-P bets never counting, live and pending bets both counting, MLS vs MLS Next Pro non-collision, different-date/different-league/different-fixture non-matches, desktop and mobile viewports, and bankroll/exposure figures (`getRiskMetrics().stakeOpen`) unchanged after Cancel and correctly increased after Approve Anyway. All 42 checks pass. Full Python suite: 299/299 passing, unchanged (no Python file touched). QuantEngine golden vectors: 285/285 passing, unchanged (no calculation function touched). Lookup performance measured against a synthetic 1500-bot-row/300-manual-bet dataset (exceeding the real account's documented ~271-pick scale): ~0.3ms/call, negligible against the ~150–350ms per-action cost already established by ADR-016.

**Scope:** dashboard-only (`index.html`); no Python file was touched. This is a **warning, not a restriction** — there is no hard fixture-exposure cap, and approval remains possible after the warning. Explicitly independent from ADR-018 (which constrains bot pick *generation*, not dashboard *approval*) — neither reads the other's identity keys or code paths. See ADR-019.

**Phase 26.46's pre-commit audit (same phase, before any commit) resolved one open question: can a single logical bet be counted more than once by `getApprovedFixtureExposure()`?** Traced (not assumed) via a dedicated 29-check duplication audit before committing anything. Answer: **no** — a bot pick legitimately exists in both `state.footballHistory` and `state.footballDaily` simultaneously (approval never removes the row from today's daily CSV), but `getAllBotRowsMergedUnique()`'s pre-existing exact-`_pickKey` `Map` already collapses this to one entry, safe because both arrays are normalised through the identical `normalizeBotCsvRow()`; confirmed with three distinct JS object instances sharing one `_pickKey` collapsing to one row. A manual bet has no equivalent dual representation — `state.manualBets` holds one mutable record per `id`; the only other array `getManualRowsMerged()` merges in (`state.manualBetsRemote`, the dead `manual_bets.csv`) is excluded entirely via `isLocal === true`, confirmed by seeding a hypothetical non-empty remote duplicate and observing zero contribution. Also explicitly re-verified: 2 genuinely distinct approved bot markets on one fixture both count; 2 genuinely distinct approved manual markets both count; Bot+Manual on the same market and on different markets both produce exactly 2 exposures; a settled bot bet with a stale unresolved daily-CSV copy is correctly excluded (history wins); every void variant (`postponed_timeout`, `missing_fixture_timeout`, `manual_void` — all just `P` plus a `SettlementReason` label, per ADR-017) is excluded identically to a plain `P`, for both bot and manual; the Phase 26.33/26.35 StakeReal auto-fill default still applies correctly when a conflict warning is shown and confirmed. **No production code fix was required** — a small, additive code comment and two documentation notes (ADR-019, `03_Dashboard.md`) now record the verified guarantee so a future reader does not need to re-derive it. 29 new targeted checks plus a re-run of the original 42 (71 total) all pass; full Python suite 299/299 and QuantEngine golden vectors 285/285 unchanged.

---

## Phase 26.45 — Fixture-Level Bot-Pick Market Lock (Policy A)

**Implemented:** 2026-07-27

**Trigger:** a dedicated read-only lifecycle investigation (prior session) into the O2.5 vs BTTS market-selection architecture, requested to determine when a bot pick's recommended market should become immutable. That investigation reconfirmed `dedupe_correlated_picks()` correctly selects one market per fixture *within a single generation run* (`Edge DESC → KellyTrue DESC → ProbModel DESC → Odd DESC`), but found persisted identity everywhere downstream (`picks_history.csv`, `localEdits`, settlement, `sent_state.json`) is market-specific, not fixture-specific — so a later run's re-evaluation of the same fixture has no visibility into an earlier run's already-persisted pick, and can silently add the competing market if the Edge ranking flips. Two real production cases confirmed this had already happened: **West Ham vs Leeds** (O2.5 persisted 2026-05-20, BTTS added ~24h later across ≥8 intervening runs; both markets subsequently show `apostada:true` with identical real stake/odd in `cloud_state.json["localEdits"]`) and **Gnistan vs Mariehamn** (O2.5 persisted 2026-07-07, BTTS added ~4 days later). Both are cross-run duplications — `dedupe_correlated_picks()` was never given a chance to compare the two candidates, because they were never in the same run's candidate set at the same time. The investigation recommended **Policy A** (first persisted market is permanent) over Policy B (pre-approval re-evaluation), given the current architecture's cost/benefit and the small settled-history sample available to justify Policy B's added complexity.

**Implementation:**

- `src/history.py` gained three fixture-identity helpers — `fixture_id_from_parts()`, `fixture_id_from_simple()` (Data/Liga/Jogo-schema rows), `fixture_id_from_candidate()` (Date/LeagueName/HomeTeam/AwayTeam-schema in-memory rows) — `Date + League(display name) + Game`, deliberately excluding Market. `history_pick_id_from_simple()` (the pre-existing, market-specific history merge key) was refactored to build on `fixture_id_from_simple()` rather than duplicating the string construction; its output is unchanged.
- `src/pipeline.py` gained `build_locked_fixture_markets()` (fixture id → set of markets already in `picks_history.csv`, built once per run from `load_history()`) and `apply_fixture_market_lock()` (rejects any candidate whose market is not already among the markets recorded for its fixture).
- `main.py` gained exactly one call site: `apply_fixture_market_lock(combo_pre)`, immediately after the O2.5+BTTS candidate concatenation and **before** `dedupe_correlated_picks()`. Both `main(topup_mode=False)` (17:00 UTC) and `main(topup_mode=True)` (23:00 UTC) execute this identical code path — there is no separate top-up implementation.
- The lock triggers regardless of `Apostada`, `Resultado`, or `SettlementReason` — an unapproved recommendation, an approved-with-real-stake pick, a cancelled approval, a settled `W`/`L`/`P`, and any void (`manual_void`, `postponed_timeout`, `missing_fixture_timeout`) all lock the fixture identically, since the backend never reads approval state to begin with (that lives only in `cloud_state.json["localEdits"]`, a frontend/cloud-sync concern the generation pipeline never touches).
- Regenerating the *same* market for an already-locked fixture is unaffected — it passes the lock, continues through staking and the daily-file pipeline exactly as before, and `merge_into_history()`'s pre-existing `[Data, Liga, Jogo, Mercado]` key (unchanged) prevents it from creating a second history row.
- Ordering was deliberately chosen as lock-before-dedupe, not dedupe-then-filter: filtering after `dedupe_correlated_picks()` would let a locked fixture's own market lose that run's same-run Edge comparison to the (about-to-be-rejected) competing market and disappear from that day's recommendation entirely, even if it still independently qualified. Locking first means the locked market's own per-run qualification (`apply_market_rules()`) is the only thing that decides whether the fixture is recommended that run.
- The two historical production cases are **not** retroactively migrated, deleted, or altered — this fix is preventative only. `build_locked_fixture_markets()` naturally treats a fixture already holding both markets as locked-to-both, so neither existing row is ever touched.

**Validation:** 37 new tests (`tests/test_fixture_id.py`, `tests/test_fixture_market_lock.py`) covering normalization/identity equivalence, direct lock behaviour (unapproved/approved/cancelled/W/L/P/void), cross-run flips on both main and top-up paths, rolling multi-day re-evaluation, top-up daily-file non-duplication, MLS/MLS Next Pro independence, the legacy dual-market case, and source-level guards proving the single shared call site and correct ordering in `main.py`. Full suite: 299/299 passing (262 pre-existing + 37 new). QuantEngine golden-vector conformance suite (285/285) re-run and passing, as expected — this is a Python-only, generation-side change; `index.html` was not modified. No production data (`cloud_state.json`, `picks_history.csv`, `fixtures_today.csv`, any `picks_*.csv`, `league_stats.csv`, `sent_state.json`) was read or written outside of tests, which exclusively use `tmp_path` fixtures.

**Scope:** bot picks only. Manual bets (`state.manualBets`) are completely unaffected — a user may still deliberately create manual bets on both O2.5 and BTTS for the same fixture via Scout; confirmed by construction (`src/pipeline.py` never references `manualBets`/`cloud_state`/`localEdits`). Policy B (pre-approval re-evaluation) was explicitly out of scope for this phase and was not implemented. See ADR-018.

---

## Phase 26.44 — `league_stats.csv` Persistence Fix (Dashboard League Analytics Was Frozen for ~2 Months)

**Implemented:** 2026-07-21

**Trigger:** a dedicated read-only investigation into why MLS and MLS Next Pro were absent from Dashboard → Análises → "A — Desempenho por Liga", prompted after Phase 26.42/26.43 shipped real MLS settlement activity that should have been visible there.

**Root cause:** the table (and its 4 top insight cards — same dataset) is entirely data-driven from `state.leagueStats`, loaded from `league_stats.csv` via `loadLeagueStats()`. That file is a *derived* artifact, regenerated from `picks_history.csv` by `src/league_stats.py::update_league_stats()` on two production paths — `update_results.py::main()` (settlement, 07:00/22:30 UTC) and `main.py` (generation, 17:00 UTC + 23:00 UTC top-up, via `src/pipeline.py::persist_history()`). **Neither path ever uploaded the regenerated file to GitHub** — `update_results.py::main()`'s `upload_csv_to_github()` calls covered only `HISTORY_FILE`/`DAILY_FILE`; `main.py`'s `upload_outputs()` list covered only the picks output files. Since GitHub Actions runners are ephemeral, the correctly-computed local file was silently discarded at the end of every run. The committed `league_stats.csv` was frozen at `LastUpdate: 2026-05-24T11:43:08Z` — its last real update — while 852+ subsequent settlement/generation commits advanced `picks_history.csv` with zero effect on it. This affected every league equally; nothing about the gap was MLS-specific.

**Fix (additive, two files):**
1. `update_results.py`: new module constants `LEAGUE_STATS_FILE`/`REMOTE_LEAGUE_STATS_NAME`, and a new `_persist_league_stats(history_file, league_stats_file, remote_name)` helper — `update_league_stats()` immediately followed by `upload_csv_to_github()`, in one `try/except` (deliberately not two — this both guarantees correct ordering by construction and preserves the exact failure tolerance this derived file already had: a computation or upload problem is logged and skipped, never allowed to abort the history/daily settlement that already succeeded above it). `main()`'s prior inline try/except now calls this helper.
2. `main.py`: the `upload_outputs()` call's file list gained `HISTORY_PATH.parent / 'league_stats.csv'` — the exact same default-output-path convention `update_league_stats()` itself uses internally, verified to agree by a dedicated test.

`update_results.py::run_settlement_remote()` (the Railway on-demand "Executar Resolução" path) does not call `update_league_stats()` at all — unaffected by this fix, exactly as before. `run_main.py`/`run_topup.py`/`gerar_picks.py` all funnel through `main.py`'s single `main()` function (subprocess or direct import) and inherit the fix automatically — no separate change needed in any of them.

**Zero Analytics calculation semantics changed** — `groupby(['Liga','Mercado'])`, `TotalPicks`/`Wins`/`Losses`/`Pending` definitions, the `Resultado.isin(['W','L'])` "resolved" gate (P excluded from both resolved and pending), `WinRate%`/`ROI%`/`Yield%`/`AvgKelly`, and the `Tier` thresholds (`<3` picks → Unproven, `≥12%`/`≥5%`/`≥0%` ROI bands) are byte-identical to before.

**Verification against real production data (scratch output only, `picks_history.csv` never modified or committed):** running the real `update_league_stats()` produced 27 rows (vs. the stale file's 14 data rows) including `MLS/O2.5` (21 picks: 11 W, 7 L, 3 pending; ROI −18.05%; Tier Weak) and `MLS/BTTS` (1 pick, 100% win rate; Unproven) — confirming MLS was always fully Analytics-eligible and was purely blocked by the upload gap. MLS Next Pro correctly produced no row: zero records currently carry `Liga="MLS Next Pro"` anywhere in production (a separate, deliberately deferred data-identity/corruption issue involving the Huntsville City vs Crown Legacy bridge record — **not investigated or touched in this phase**). This is expected, data-driven behaviour — no row was forced.

**Frontend validated unchanged (Playwright, fresh `league_stats.csv` fixture served via route interception, no production file touched):** `loadLeagueStats()`, `getLeagueAnalyticsRows()`, `renderLeagueAnalytics()`, `renderLeagueAnalyticsInsights()`, the league search filter, and the market filter all correctly surface MLS the moment fresh data is supplied — proving the frontend needed, and received, zero code changes.

**Related finding, not fixed (deliberately out of scope):** a narrow audit for the same local-write-never-upload pattern found `sent_state.json` (`src/state.save_sent_state()`) and `team_alias_cache.json` (`update_results.py::save_team_alias_cache()`) share it — both files' last commits predate or coincide with `league_stats.csv`'s, suggesting a repeated mistake rather than an isolated one. Flagged in `04_Backend.md` §11 for a future, separately-scoped investigation; neither file is directly dashboard-visible the way `league_stats.csv` is, so impact and priority need their own assessment.

**Tests:** `tests/test_league_stats_persistence.py` — 9 new tests covering `_persist_league_stats()`'s call ordering, failure tolerance (computation failure and upload failure both swallowed without propagating, matching pre-existing semantics), `main.py`'s upload-list inclusion (source-level guard, since `main()` end-to-end is not practically unit-testable without mocking live fixture fetches), path-convention agreement between `main.py` and `update_league_stats()`'s own default, and a generic (non-MLS-specific) proof that any league needs only 1 history row to become Analytics-eligible. Full suite: 262/262 passing (253 pre-existing + 9 new). A new Playwright script (`test_league_stats_dashboard.js`, 8 checks) plus the existing regression set and QuantEngine golden vectors (285/285) re-run with zero regressions.

**Files modified:** `update_results.py`, `main.py`, `tests/test_league_stats_persistence.py` (new), `docs/04_Backend.md`, `docs/05_Known_Issues.md` (new `ANALYTICS-1`), `docs/07_Current_Status.md`, `docs/08_Change_Log.md` (this entry), handover.

**Explicitly preserved/untouched:** MLS → API-Football 253 / MLS Next Pro → API-Football 909 routing; the shared settlement engine; Phase 26.43's void policy (SUSP/INT classification, `SettlementReason` bridge, `HISTORY_COLUMNS`); ADR-015 CSV-wins precedence; `QuantEngine`; the H1/H2/H3 render dispatcher; bankroll/exposure calculations; manual bets. No production runtime file (`cloud_state.json`, `picks_history.csv`, `fixtures_today.csv`, `picks_btts.csv`, `picks_hoje*.csv`, `picks_over25.csv`) was modified — all verification used scratch output paths or monkeypatched temp paths. The Huntsville City vs Crown Legacy record was neither modified nor investigated beyond preserving this finding as a deferred item.

---

## Phase 26.43 — Postponed/Cancelled/Missing-Fixture Bets No Longer Stay Exposed Indefinitely

**Implemented:** 2026-07-21

**Problem:** an approved real-money bet whose fixture was postponed, cancelled, abandoned, or became undiscoverable through the normal settlement lookup (a fixture rescheduled far enough from its original date) had no path to closure — the settlement engine correctly never settled it incorrectly (no `FT`/`AET`/`PEN` status was ever observed), but it also never resolved any other way, leaving it financially exposed forever. Chicago Fire vs Vancouver Whitecaps (2026-07-17, `picks_history.csv`) was the concrete case, flagged as a deferred follow-up during the Phase 26.42 investigation.

**Two safeguards, both settling exclusively through the existing shared `update_dataframe()` engine (ADR-002/ADR-009) and always writing the existing `P` (push/void) result:**

1. **Automatic — explicit non-played status.** A new status classification (`classify_af_status()`/`classify_fd_status()`) extends the pre-existing `AF_FINISHED_STATUS`/`FD_FINISHED_STATUS` sets with `IN_PROGRESS` (never void-eligible, at any age — the crucial safety rule), `NON_PLAYED` (`PST`/`CANC`/`ABD` for API-Football; `POSTPONED`/`CANCELLED` for football-data.org — see the pre-commit safety audit correction below regarding `SUSP`/`INT`/`SUSPENDED`), and a default `SCHEDULED_UNKNOWN` bucket. A `NON_PLAYED` status still observed `POSTPONED_VOID_AFTER_HOURS` (default 48h) after the bet's own persisted **original** `KickoffUTC` settles as `P`.
2. **Automatic — persistent missing fixture.** A genuine `NO_MATCH` (fixtures fetched successfully, none matched — never a provider error, which never reaches this path) increments a new persisted `MissingAttempts` counter. Voiding requires all three: `MISSING_FIXTURE_VOID_AFTER_HOURS` (default 72h) elapsed since original kickoff; `MissingAttempts >= missing_fixture_min_attempts` (default 3); and a final, bounded rediscovery search (`attempt_rediscovery_af()` — AF only, forward-only, `+2..+14` days, reusing the existing per-run fixture cache) also finding nothing. If rediscovery finds the fixture already finished, it settles normally (`W`/`L`) instead of voiding. If it finds the fixture not yet finished, the bet keeps waiting and the counter resets to 0.
3. **Manual — "Anular aposta".** A Live Center-only fallback for any still-unresolved approved bet, available `manual_void_available_after_hours` (default 24h) after its own original kickoff, gated purely on elapsed time. Requires an explicit PT-PT confirmation. Distinct from, and does not change, the pre-existing generic quick-settle `P` button (unrestricted, no reason stamped, kept for "I already know the result").

**Configuration:** all four values live in `config.json["settlement"]["void_policy"]`, defensively validated (`src.config.get_void_policy()`, per-key fallback to a `DEFAULT_*` constant), following the exact pattern every other config-driven value in this project already uses (ADR-010). The dashboard reads the one value it needs (`manual_void_available_after_hours`) via a new `loadVoidPolicyConfig()`, reusing the same GitHub raw-content `config.json` fetch Scout's `loadModelConfig()` already established.

**Audit trail (additive, non-breaking):** `CSV_COLUMNS` gained `SettlementReason` (blank for every ordinary W/L/P; populated only for a void) and `MissingAttempts` (a working evidence counter). Existing rows read both back as `""` via `ensure_columns()`, exactly like `Placar` did when it was added (Phase 26.19). Manual bets carry the same two fields as `bet['settlementReason']`/`bet['missingAttempts']`; `apply_df_results_to_manual_bets()` now returns `(newly_settled, evidence_changed)` so `cloud_state.json` is saved whenever the missing-fixture evidence counter changes, even for a bet that stays unresolved — without this, the counter would silently reset every run and the safeguard would never mature for manual bets. History's expandable row detail shows a PT-PT "Motivo" line (`settlementReasonLabel()`) whenever a reason is present.

**Refactor (incidental, reduces duplication):** `try_update_row_via_api_football()`'s three near-identical call sites inside `update_dataframe()` were consolidated into one nested helper, `_run_af_and_account()` — also the single place the missing-fixture safeguard is invoked from, so it applies identically regardless of which fallback path produced the `NO_MATCH`.

**Pre-commit safety audit (same session, before any commit) — three defects found and corrected:**

1. **SUSP/INT/SUSPENDED were unsafely auto-void-eligible.** The initial implementation grouped them with `PST`/`CANC`/`ABD` under the 48h explicit-status timeout, reasoning that a suspended/interrupted match needed the identical treatment. A dedicated audit constructed the counter-scenario: a match interrupted Monday, still reporting `INT`/`SUSP` on Wednesday (48h later), that legitimately resumes and finishes Friday — the original implementation would have auto-voided it Wednesday, incorrectly, since the match was always going to produce a real result. Corrected: `SUSP`/`INT` removed from `AF_NON_PLAYED_STATUS`, `SUSPENDED` removed from `FD_NON_PLAYED_STATUS` — they now fall through to the pre-existing `SCHEDULED_UNKNOWN` default (never automatically void-eligible, any age; the 24h manual fallback remains available). Documented via `AF_SUSPENDED_INTERRUPTED_STATUS`/`FD_SUSPENDED_INTERRUPTED_STATUS` (not consulted by the classifiers, kept only so a future edit doesn't silently re-add them). See ADR-017's "Correction" section.
2. **`getRowWithLocalEdits()` never merged `edit.settlementReason`.** The write side (`manualVoidBet()` → `settleBotBet(key, 'P', reason)`) worked correctly, but nothing merged the reason back into the canonical row object History reads from — a bot pick manually voided while its CSV result was still empty (the `resultadoManual` bridge case, ADR-015) showed a correct `P` with a blank "Motivo". Fixed by resolving `settlementReasonFinal` with the exact same branch condition `resultadoFinal` already uses — tracking which source the *result itself* came from, not an independent "CSV wins whenever non-empty" fallback. An initial fix attempt used the latter shape and was caught by its own regression test: it left a stale "Anulada manualmente" reason showing next to a CSV-authoritative `W`, since the CSV's own (correctly blank, because a win has no void reason) `SettlementReason` lost to the non-empty stale local value under that logic.
3. **`src/history.py`'s `HISTORY_COLUMNS` schema drift — found to be a pre-existing, already-active production bug, not something this phase introduced.** `HISTORY_COLUMNS` was never updated when `Placar` was added (Phase 26.19). `ensure_simple_columns()`'s reindex (`load_history()`/`merge_into_history()`, on the daily-generation path `main.py` → `persist_history()`) silently stripped it from every settled row on each cycle — confirmed against the real, live `picks_history.csv`: 90 of 93 settled rows had an empty `Placar`. `SettlementReason`/`MissingAttempts` (this phase's own new fields) were exposed to the identical erasure path — this is what surfaced the pre-existing bug while verifying the new one. Fixed by extending `HISTORY_COLUMNS` to mirror `update_results.py`'s `CSV_COLUMNS` exactly, plus explicit blank-column assignments in `src/pipeline.py`'s `save_all_outputs()` (a second, separate consumer without `ensure_simple_columns()`'s add-if-missing safety net — verified it would otherwise raise `KeyError` on every generation run). **Preventative only** — does not reconstruct the already-lost historical `Placar` values; see `05_Known_Issues.md` SETTLEMENT-4 (a dedicated, explicitly-approved data-repair task would be required for that, out of scope here).

**Chicago Fire vs Vancouver Whitecaps assessment (read-only, no live settlement run, no production data touched) — corrected by the audit.** Stored `KickoffUTC` is `2026-07-17T00:30:00+00:00`; at the time of this phase the fixture was already ~106.6 hours old — past both the 48h and 72h thresholds. The prior session's live investigation already established it is not found in API-Football's schedule within a ±10-day window of its stored kickoff (consistent with genuine postponement, not a matching failure), which is the missing-fixture pathway, not the explicit-status one. **The implementation's initial report incorrectly projected this would auto-void on the very next settlement run**, reasoning `MissingAttempts` was "already well past the minimum from ~8 settlement runs since 2026-07-17" — this was wrong: the live `picks_history.csv` does not yet have the `MissingAttempts` column at all (the new policy has never run against production), so the effective current value is 0, not ~8. The correct expected lifecycle: run 1, genuine `NO_MATCH` → `MissingAttempts` 0→1, no rediscovery (below the minimum of 3), no void; run 2 → 1→2, same; run 3 → 2→3, meets the minimum, triggers the bounded rediscovery search — if it also finds nothing (consistent with the prior ±10-day finding), voids as `P` with `SettlementReason="missing_fixture_timeout"`. At the normal twice-daily settlement cadence this is approximately 1.5 days after the new mechanism begins accumulating evidence, assuming every run produces a genuine `NO_MATCH` and provider health stays valid. This is still a code-level projection, not a live-verified outcome — no settlement was run this session.

**Validation:** `tests/test_void_policy.py` — 28 Python tests after the audit correction (25 original + `test_fd_suspended_after_48h_remains_unresolved`, `test_suspended_interrupted_very_old_fixture_still_never_auto_voids`, `test_suspended_interrupted_classification_falls_through_to_scheduled_unknown`; the original `test_suspended_interrupted_after_threshold_becomes_p` renamed and flipped to `test_suspended_interrupted_after_48h_remains_unresolved`, now asserting no void occurs). `tests/test_history_schema.py` — 9 new tests (`HISTORY_COLUMNS`/`CSV_COLUMNS` parity, `ensure_simple_columns()` legacy-row tolerance, `merge_into_history()` realistic round-trips preserving all three fields, a legacy row with none of the new columns, `save_all_outputs()` not raising, a 3-run `MissingAttempts` lifecycle routed through the *actual* history-merge path, `SettlementReason`/`Placar` surviving a simulated generation cycle after a void). Full suite: **253/253 passing** (216 original + 28 void-policy + 9 history-schema). A new Playwright script, `test_settlementreason_bridge.js` (17 checks — the full bridge lifecycle: void → localStorage-persistence-equivalent reload → later CSV-authoritative settlement correctly overriding both the result and the reason, per ADR-015), plus `test_manual_void.js` (15 checks, re-run) and the full pre-existing Playwright regression set (7 scripts) all re-run and passing with zero regressions. JS golden-vector conformance suite re-run: 285/285 (`QuantEngine` untouched).

**Files modified (including the audit correction):** `update_results.py`, `config.json`, `src/config.py`, `src/history.py`, `src/pipeline.py`, `index.html`, `tests/test_void_policy.py` (new, updated), `tests/test_history_schema.py` (new), `docs/09_Architecture_Decisions.md` (ADR-017, new + "Correction" section), `docs/04_Backend.md`, `docs/03_Dashboard.md`, `docs/02_Data_Flow.md`, `docs/05_Known_Issues.md` (SETTLEMENT-4, new), `docs/07_Current_Status.md`, `docs/08_Change_Log.md` (this entry).

**Explicitly preserved:** the shared settlement engine was not split (ADR-002/ADR-009); the MLS/MLS Next Pro fix (Phase 26.42) was not touched; `QuantEngine` and its golden-vector conformance suite were not touched (re-verified: 285/285 JS assertions passing); the H1/H2/H3 render dispatcher (ADR-016) was not touched (re-verified via the existing H3 dispatcher/migration Playwright scripts); no production bet was manually altered; no production runtime file (`picks_history.csv`, `cloud_state.json`, `fixtures_today.csv`, `picks_hoje*.csv`, `picks_btts.csv`, `picks_over25.csv`) was modified — all validation used isolated temporary files/mocked state.

---

## Phase 26.42 — MLS and MLS Next Pro Established as Two Independent, First-Class Leagues; Manual Kickoff Display Gap Closed

**Implemented:** 2026-07-20 – 2026-07-21

**Investigated:** a read-only investigation (prior session) found every current senior-MLS bet (bot and manual, four known examples: Chicago Fire vs Vancouver Whitecaps, St. Louis City vs Sporting Kansas City, Nashville SC vs Atlanta United FC, Los Angeles Galaxy vs Los Angeles FC) stuck unsettled well past `RESULT_READY_DELAY`, while older `"MLS"`-labelled bets from earlier in the season had settled correctly.

**Root cause:** `src/league_registry.py`'s `"mls"` `LeagueEntry` had `af_id=909` — API-Football's **MLS Next Pro** competition — hardcoded since commit `2288d080` (Phase 26.12, 2026-06-28), while `config.json`'s `api_football.league_ids.mls` held the correct senior-MLS ID (`253`) the entire time, unnoticed because fixture generation (`fetch_oddsapi_fixtures.py`) reads `config.json` directly and never imports the registry. At the time of the Phase 26.12 change this was not a mistake in isolation: the 13 bets it fixed genuinely were reserve-team fixtures, because `fetch_fixtures_for_league_date()`'s zero-fixture retry (`search_league_id_by_api()`) fuzzy-matched the configured league's short name (`"MLS"`) against API-Football's `/leagues` listing — since `"major league soccer"` does not contain the substring `"mls"` but `"MLS Next Pro"` does, every date where senior MLS legitimately had no scheduled fixture silently substituted MLS Next Pro fixtures under the `"MLS"` label instead, with no warning surfaced anywhere. A systematic comparison of every league's `config.json` `league_ids` value against `league_registry.py`'s `af_id` found this collision was unique to MLS — all 20 other leagues agreed exactly.

**Requirement clarified mid-implementation:** an initial fix pass (2026-07-20, within this same still-uncommitted session) restored `"mls"` to `af_id=253` and registered `"mls_next_pro"` for settlement-routing purposes only, deliberately absent from `config.json` so it could not generate picks. This was a misreading of the actual requirement — generating MLS Next Pro picks was always an intentional part of this project's coverage; the defect was never that MLS Next Pro fixtures were produced, only that they were silently obtained via a fallback *from* MLS and stored under MLS's canonical identity. This was corrected before commit: the final architecture makes both competitions genuinely independent, first-class, actively-generating leagues.

**Fix — canonical routing:** `"mls"` restored to `af_id=253`, `af_name="Major League Soccer"`. A new, distinct entry, `"mls_next_pro"` (`name="MLS Next Pro"`, `af_id=909`, `season_model="calendar"`), was added to `REGISTRY` immediately after it. Every consumer of the registry (`LEAGUE_CODE_MAP`, `BLOCKED_FOOTBALL_DATA_CODES`, `API_FOOTBALL_FALLBACK_COMPETITIONS`, `AF_SEASON_MODELS`, `REGISTRY_BY_KEY`) was audited before the change; none required any code change beyond the registry entries themselves, confirming ADR-004's "single registration point" design held up under this fix.

**Fix — MLS Next Pro activated as a first-class generating league:** registering a competition in `src/league_registry.py` gives it a settlement identity only — `fetch_oddsapi_fixtures.py` never imports the registry, and decides which leagues to fetch fixtures for purely from `config.json`. `mls_next_pro` was therefore also added to: `config.json`'s `leagues` section (`{"name": "MLS Next Pro", "country": "USA"}`) and `api_football.league_ids` (`909`); `fetch_oddsapi_fixtures.py`'s `DEFAULT_LEAGUE_IDS`, `LEAGUE_INFO_EXT`, and the `summer_leagues` calendar-season set inside `season_for_date()`; `main.py`'s `NON_EU_TOPUP_LEAGUES` frozenset, so the 23:00 UTC late-odds top-up run treats it identically to MLS (both are US leagues with late UTC kickoffs); and `fetch_historical.py`'s `LEAGUE_INFO`/`summer_leagues` for future manual history refreshes. A real `data_raw/mls_next_pro.csv` history file (535 finished matches, seasons 2025–2026, fetched live from API-Football via `fetch_historical.py`) was generated — without it, `process_league_fixtures()` (`src/pick_generation.py`) would silently skip the league every single day regardless of every other configuration step, since a missing `data_raw/{key}.csv` short-circuits to zero candidates with only a `[WARN]` print. `tools/analyse_edge.py`, a standalone, non-scheduled calibration-research script covering a hand-picked league subset (not all 21/22 leagues even before this phase), was deliberately left untouched as genuinely out of scope.

**End-to-end verification (live, read-only, no writes to production CSVs):**
- Fixture fetch independence: `fetch_fixtures_for_league_date()` was called live for both `253` and `909` across seven consecutive dates. Results: both zero on some dates; MLS Next Pro alone had fixtures on 2026-07-22 while MLS had zero that day (proves zero MLS fixtures never disables or substitutes MLS Next Pro); both had fixtures simultaneously on 2026-07-23 (15 senior MLS fixtures + 2 MLS Next Pro fixtures, zero team overlap) and 2026-07-26 (14 + 7) — proving full, simultaneous independence.
- Pick generation independence: `process_league_fixtures()` was called directly (no CSV writes, no GitHub upload, no Telegram) for one real fixture per league on the same date (2026-07-23). Both independently computed real Poisson lambdas from their own `data_raw/*.csv`, real O2.5 model probabilities, and a positive-edge candidate: MLS (Philadelphia Union vs New York Red Bulls, λ=1.946/1.184, edge +3.4%) and MLS Next Pro (Vancouver Whitecaps II vs Austin II, λ=1.716/1.900, edge +11.2%).
- Dashboard distinction: a dedicated Playwright script confirmed `normalizeLeagueCode()` maps `"MLS"` → `mls` and `"MLS Next Pro"` → `mls_next_pro` (never the same code), pick keys differ, and both leagues appear as two separate entries in the data-driven league filter list with zero merging.

**Fix — fixture-generation fallback removed (still in effect, unchanged from the initial pass):** `fetch_oddsapi_fixtures.py::fetch_fixtures_for_league_date()` no longer retries a zero-fixture response with `search_league_id_by_api()`. Since every league reaching this function already has an explicitly configured `af_id`, a zero-fixture response now simply means no fixtures for that league on that date — logged for visibility, never substituted, for either MLS or MLS Next Pro. `search_league_id_by_api()` itself remains defined but disconnected, with a comment against reconnecting it. `fetch_historical.py` has its own, separate copy of the same helper pattern (unused by the automated pipeline — `.github/workflows/bot.yml` never calls it); it now also knows about `mls_next_pro` (added this phase for the manual-refresh use case) but was not otherwise rewritten.

**Historical data audit (no destructive migration — re-confirmed after activating MLS Next Pro generation):** every `"MLS"`-labelled row in `picks_history.csv` (21 rows) and `cloud_state.json["manualBets"]` (20 rows) was individually inspected. Activating MLS Next Pro as a first-class league does not change the conclusion below — already-settled historical data is not migrated merely because the competition it actually belongs to is now actively tracked.

- **28 already-settled rows** (14 bot picks, 14 manual bets) are genuine MLS Next Pro fixtures (reserve/"II" teams — `Atlanta United II`, `Chattanooga`, `Real Monarchs`, `Crown Legacy`, `The Town`, `Huntsville City` [as a home/away side in other, already-settled fixtures], etc.) — left completely untouched. Reclassifying an already-resolved row was judged an unjustified, purely cosmetic change with no correctness benefit.
- **Exactly one unresolved row** was both stale and deterministically identifiable by team identity: `picks_history.csv`, `"2026-06-21;MLS;Huntsville City vs Crown Legacy"` — both clubs exist only in MLS Next Pro, never senior MLS. `Liga` changed to `"MLS Next Pro"` (no other column touched) so it remains resolvable under the corrected routing. The corresponding `cloud_state.json["localEdits"]` key was re-keyed from `"2026-06-21|mls|Huntsville City vs Crown Legacy|Over 2.5"` to `"2026-06-21|mls_next_pro|Huntsville City vs Crown Legacy|Over 2.5"` (`resultadoManual: "P"`, `settledAt`, `apostada` all preserved verbatim) — required because `index.html`'s own JS-side league-name-to-key mirror (`LEAGUE_NORMALIZE`) had no entry for `"mls next pro"` and would otherwise have computed a different pick key for this row than the CSV's now-different `Liga` string, silently orphaning its existing manual-result bridge (ADR-015). `LEAGUE_NORMALIZE` gained `['mls_next_pro','mls_next_pro']` and `['mls next pro','mls_next_pro']` entries (previously `'mls next pro'` incorrectly mapped to `'mls'`) so this stays consistent going forward.
- **6 unresolved manual bets** (the four known cases plus two rejected-but-still-settling bets, `CF Montreal vs Toronto FC` and `Seattle Sounders vs Portland Timbers`, both 2026-07-17) and **3 unresolved bot-pick rows** (the four known cases minus St. Louis City, which has no bot pick — only a manual bet) already correctly carried senior-MLS identity (`leagueId: 253`, real senior club names) and needed no data change; they simply settle correctly now that routing is fixed.
- No row's `Resultado`/`Lucro€`/`resultado`/`lucro` field was read, written, or migrated by this phase.

**Fix — manual kickoff display:** a related, separate frontend gap was found and fixed while validating the four known cases: `getManualRowsMerged()` never propagated `kickoffUTC` from a raw `state.manualBets` entry onto its merged row object, so even though Phase 26.32 already persists it correctly at bet-creation time, every downstream consumer received `undefined`. Fixed by adding `kickoffUTC: cleanString(b.kickoffUTC || '')` to the merged local-row object. A second gap — `getPendingRows()`/`getLiveRows()`/`getPendingCount()` deriving a manual bet's kickoff exclusively via `findFixtureKickoff()` (a live lookup against the current rolling `fixtures_today.csv` window, empty once a fixture ages out of it) rather than ever reading the persisted field — was fixed with a new `resolveManualKickoff(b)` helper (`b.kickoffUTC || findFixtureKickoff(...)`), used at all four call sites; `getPendingCount()` was included specifically to preserve its Phase 26.38 invariant (`getPendingCount() === getPendingRows().length`). Bot-pick kickoff handling (`r['KickoffUTC']`, read directly from the CSV) was not touched. Backend settlement was already reading `bet.get('kickoffUTC')` correctly (`manual_bets_to_settlement_df()`) — this was a display/classification-only gap, confirmed to have zero effect on `RESULT_READY_DELAY` timing. The Manual Bets tab's own row table (`renderManualBets()`) still calls `findFixtureKickoff()` directly and was left unchanged — outside this fix's stated scope (Pending + Live Center only), noted as a residual, lower-priority instance of the same latent pattern.

**Settlement verification (read-only, live API-Football, under the corrected `af_id=253` routing):**

| Fixture | Provider status | Score | Over 2.5 result once settled |
|---|---|---|---|
| St. Louis City vs Sporting Kansas City | `FT` | 3–2 | W |
| Nashville SC vs Atlanta United FC | `FT` | 1–0 | L |
| Los Angeles Galaxy vs Los Angeles FC | `FT` | 0–3 | W |
| Chicago Fire vs Vancouver Whitecaps | not found in API-Football's schedule within a ±10-day window of its stored kickoff | — | remains open — no incorrect settlement |

Chicago Fire and Vancouver Whitecaps were confirmed to have each resumed play against different opponents (2026-07-22) with no head-to-head fixture reappearing in that window — consistent with a genuine postponement whose rescheduled date (if any) falls outside the settlement engine's current date-window matching strategy. `update_dataframe()` was confirmed, by code inspection, to have no path that could settle this as W/L/P without first matching a fixture with a `FT`/`AET`/`PEN` status — it degrades safely to "stays open," not "settles wrong." No dedicated postponed-fixture lifecycle exists (unchanged from before this phase — see `05_Known_Issues.md` for the residual gap this does not close: a fixture rescheduled far enough from its original date may not be automatically rediscovered by the existing date-window search). This was assessed but not implemented, per this task's explicit scope boundary — it is recommended as a separate, dedicated follow-up phase if it recurs often enough to matter.

**Validation:** `tests/test_mls_league_routing.py` (23 tests, includes routing, independent/simultaneous fixture-fetch mocks, generation-config presence, topup-set membership, and manual-bet routing for both leagues) and `tests/test_fixture_fetch_no_substitution.py` (3 tests) — new this phase — plus 2 tests added to `tests/test_season_model.py` for `mls_next_pro`. Full existing Python suite: **216 tests passing**, zero modified/deleted assertions beyond replacing the one test that had asserted the (incorrect) settlement-only exclusion with one asserting active generation. Scratchpad-only Playwright scripts (project convention — not committed): the manual-kickoff-display script (7 checks) and a new dashboard-league-distinction script (8 checks, confirms `normalizeLeagueCode()`/pick keys/league filter list never collapse the two leagues) both pass; the full pre-existing manual-bet-lifecycle suite (14 checks) and render-dispatcher sanity check were re-run with zero regressions.

**No change** to the shared settlement engine (`update_dataframe()`), ADR-002/ADR-009's bot/manual parity, the QuantEngine architecture, the H1/H2/H3 render-dispatcher architecture, bankroll/exposure/StakeReal calculation, CSV-wins result precedence (ADR-015), or any other league's routing. See ADR-004 update, `05_Known_Issues.md` SETTLEMENT-3 and DASHBOARD-6.

---

## Phase 26.41 — H1/H2/H3 Performance Optimisation Programme Concluded

**Implemented:** 2026-07-15

**Goal.** Close the remaining architecture gaps identified by an independent, read-only audit of the completed H1/H2/H3 programme (prior session). Not a new optimisation — a completion of the H3 dispatcher migration Phase 26.40 started but left incomplete in one functional area.

**Audit findings (verified before any change was made).** The audit traced every render function's callers across the entire file and found:

1. **Manual Bets action surface bypassed the dispatcher entirely.** `addManualBetFromFixture()`, `mbHandleRowAnalyze()`, `mbHandleRowSave()`, `mbHandleRowApprove()`, and `mbHandleRowReject()` each called `markDirty()` immediately followed by the legacy `rerenderManualOnly()` wrapper — which unconditionally renders `renderManualScout()`/`renderManualBets()` (tab-manual), `renderPendingQueue()` (tab-pending), and `renderLiveCenter()` (tab-live), regardless of which tab is actually active. Since `markDirty()` already renders the active tab via `renderActiveTabIfStale()`, this caused a genuine duplicate render whenever `tab-manual` was active, and always rendered two other tabs' DOM the user could not see. Measured cost: **~67ms of confirmed invisible-tab work per action — ≈27% of `mbHandleRowApprove()`'s ~252ms total** on the real production account.
2. **Two smaller instances of the same pattern in Bankroll movement handlers**, left over from Phase 26.40's own Issue B fix: `addMovement()` and the delete-movement handler both called `markDirty()` (correctly added in Phase 26.40) followed by a direct, now-redundant `renderBankrollPage()` call that predated that fix and was never removed alongside it.
3. **Three wrapper functions with zero live callers**, confirmed by a full-file caller search: `rerenderSummaryOnly()` (not previously flagged), `rerenderPendingOnly()` and `rerenderLiveOnly()` (both flagged as dead by Phase 26.40's own handover, retained pending confirmation this phase).

**Part 1 — Manual Bets migration.** All 5 mutation handlers now call `markDirty()` alone — identical to the pattern `.js-bot-approve` has used since Phase 26.33, and to `settleManualBet()`/`settleBotBet()`. `markDirty()`'s own `renderActiveTabIfStale(state.activeTab)` correctly re-renders `tab-manual`'s own content when it's active, and does nothing extra when it isn't; `tab-pending`/`tab-live` pick up the change the moment they're actually opened (`setActiveTab()` always forces a fresh render on activation — no staleness). `mbHandleRowEdit()` and `mbHandleRowCancel()` were deliberately **not** changed: neither mutates `state` (both only toggle `window._mbEditState`, a UI-only edit-mode flag) or calls `markDirty()`, so they were never part of the duplicate-render problem — they continue to call `rerenderManualOnly()`, the same category as `rerenderDayOnly()`/`rerenderHistoryOnly()`'s existing filter-only usage.

**Part 2 — Bankroll duplicate renders.** Verified both buttons are only reachable while `tab-bankroll` is already active (their DOM only exists inside that tab's rendered panel), so `markDirty()`'s active-tab dispatch already covers the redundant `renderBankrollPage()` call in both cases. Removed both.

**Part 3 — Legacy wrapper classification.**

| Wrapper | Classification | Disposition |
|---|---|---|
| `rerenderManualOnly()` | LEGACY (2 UI-only callers: `mbHandleRowEdit`, `mbHandleRowCancel`) | Retained |
| `rerenderDayOnly()` | LEGACY (5 UI-only filter/search callers) | Retained, unchanged |
| `rerenderHistoryOnly()` | LEGACY (9 UI-only filter/sort/view-toggle callers) | Retained, unchanged |
| `rerenderSummaryOnly()` | DEAD (0 callers) | **Removed** |
| `rerenderPendingOnly()` | DEAD (0 callers) | **Removed** |
| `rerenderLiveOnly()` | DEAD (0 callers) | **Removed** |

**Part 4 — Dispatcher re-verification.** Re-swept every direct mutation of the 7 tracked `state` containers across the whole file (unchanged from the original audit's sweep — no new gap found); confirmed every mutation site still correctly calls `markDirty()`/`invalidateDataCache()`. Loaded the modified file in a real browser and confirmed zero page errors and correct removal of the 3 deleted functions (`typeof window.rerenderSummaryOnly === 'undefined'`, etc.).

**Part 5 — Performance validation.** Measured on the real production account (`cloud_state.json`: 93 history rows, 90 manual bets), all actions taken while `tab-day` is active (so Manual Bets/Bankroll/Pending/Live DOM is invisible throughout, matching the audit's worst-case scenario):

| Action | Measured |
|---|---|
| Approve bot pick | 263.3ms |
| Cancel bot pick | 199.0ms |
| Approve manual bet | 211.9ms |
| Reject manual bet | 202.0ms |
| Save manual edit (on tab-manual, its own tab) | 36.0ms |
| Bankroll movement add | 238.3ms |
| Bankroll movement delete | 232.1ms |
| `rerenderAll()` (fresh generation) | 254.5ms |

Manual Bet actions (202–212ms) now fall in the same range as Bot Pick actions (199–263ms) — the explicit goal of this phase, and a ~16% reduction from the audit's ~252ms measurement of `mbHandleRowApprove()` under the same conditions, consistent with removing the confirmed ~67ms/27% invisible-tab overhead.

**Validation.** New 15-check Playwright script (`test_h3_manual_migration.js`): (1) Approve manual bet while `tab-day` active — zero invisible-tab renders; (2) Reject manual bet while `tab-manual` active — `renderManualBets()` runs exactly once, not twice, and `tab-pending`/`tab-live` still don't render; (3) navigating to `tab-pending` afterward shows the fresh, non-stale state; (4) `addManualBetFromFixture()` — zero invisible-tab renders, bet correctly created; (5) `mbHandleRowEdit()`/`mbHandleRowCancel()` — edit mode still works via the intentionally-retained `rerenderManualOnly()`; (6) `addMovement()`/delete-movement — `renderBankrollPage()` runs exactly once, not twice, in both cases. Full existing regression harness (13 files) re-run and passing — 14 files total, zero failures. No user-visible value, calculation, exposure, bankroll, settlement, or persistence behaviour changed.

**ADR-016 note.** Not amended — this phase completes ADR-016's rollout (closing a gap the original migration left in one functional area) rather than changing the architectural decision itself; ADR-016's Consequences section is updated to reflect the completed cleanup (see `09_Architecture_Decisions.md`).

### Files Modified

| File | Change |
|---|---|
| `index.html` | 5 Manual Bets handlers migrated to `markDirty()` alone; 2 Bankroll handlers' redundant `renderBankrollPage()` calls removed; 3 dead wrapper functions deleted (`rerenderSummaryOnly()`, `rerenderPendingOnly()`, `rerenderLiveOnly()`) |
| `docs/09_Architecture_Decisions.md` | ADR-016 Consequences section updated to reflect the completed migration |
| `docs/03_Dashboard.md` | §5 "Superseded partial renderers" rewritten to reflect the current, accurate wrapper inventory |
| `docs/08_Change_Log.md` | This Phase 26.41 entry added |
| `docs/07_Current_Status.md` | Updated for this phase; the H1/H2/H3 programme is now marked complete |

---

## Phase 26.40 — Two Post-Audit Fixes, Then the Rendering Dispatcher (Performance Audit H3)

**Implemented:** 2026-07-15

**Goal.** Two-part task. Part 1: fix two issues surfaced by the Performance Audit's own validation work. Part 2: implement the audit's third and final optimisation (H3), narrowly scoped to the rendering-architecture cost this document's own Phase 26.39 "Next Priorities" note had explicitly flagged as out of that phase's scope.

### Part 1 — Issue A: `pendingCancel()` Left "Aprovar" Unbound for a Same-Session Re-Approval

**Root cause.** `pendingCancel()` re-renders the Daily Picks table (so the cancelled pick reappears there) but never called `bindBotTableControls()` afterward — the freshly-rendered `.js-bot-approve` button had no click handler attached. A user who approved a pick, cancelled it, then tried to re-approve it in the same browser session (without an intervening full `rerenderAll()`, which does call `bindBotTableControls()`) found the button visually present but non-functional.

**Fix.** Added a `bindBotTableControls()` call at the end of `pendingCancel()` — the smallest possible fix, matching the existing pattern every other mutation-then-partial-render path in the file already follows. Also removed `pendingCancel()`'s now-redundant explicit `rerenderPendingOnly()`/`rerenderManualOnly()`/`rerenderDayOnly()` calls, since `markDirty()`'s new active-tab-aware dispatch (Part 2, H3.2) already covers the one tab (`tab-pending`, confirmed the only tab `.js-pending-cancel` ever renders on) those calls existed to refresh.

### Part 1 — Issue B: `addMovement()`/Delete-Movement Never Called `markDirty()`

**Root cause.** Both `addMovement()` and the delete-movement click handler mutated `state.movements` (bankroll deposits/withdrawals) directly, calling only `invalidateDataCache()` and `saveLocalState()`. This was already noted, without being fixed, in Phase 26.39's own Step 3 write-up as "a pre-existing quirk, confirmed harmless here since the new cache invalidation was added independently." It was not actually harmless: without `markDirty()`, `hasPendingCloudChanges` was never set and `_dirtyGeneration` never bumped, so a bankroll movement never scheduled a cloud save and never registered as a real change for anything that depends on `_dirtyGeneration`.

**Fix.** Investigated whether to call `markDirty()` directly or reuse an existing mutation path; reusing `markDirty()` was the safer option — it is already the single, well-tested mutation-notification hub every other state change in the file goes through (invalidates the cache, bumps `_dirtyGeneration`, sets `hasPendingCloudChanges`, updates the cloud status indicator, schedules the debounced cloud save, and — as of this phase's Part 2 — renders the active tab), so reusing it costs nothing and introduces no new code path to maintain. Both `addMovement()` and the delete-movement handler now call `markDirty()` in place of their standalone `invalidateDataCache()` call.

**Validation (both fixes).** New 12-check targeted Playwright script (`test_part1_fixes.js`): Issue A — approve → cancel → re-approve in the same session now works, and the Pending page's Odd Real/Stake Real inputs remain bound after a Cancel/re-render cycle; Issue B — `addMovement()`/delete-movement now correctly set `hasPendingCloudChanges`, bump `_dirtyGeneration`, and are reflected in `getBankrollState()`. All 12 pass.

### Part 2 — H3: The Rendering Dispatcher

**Context.** Phase 26.38 (H1) and Phase 26.39 (H2) fixed the *data*-computation cost of `rerenderAll()` (87.7s → 28.7s → ~1.1–1.2s on the real account). Phase 26.39's own "Next Priorities" note named the remaining cost as purely rendering-architecture: (a) `markDirty()` and the caller's own `rerenderAll()` could both trigger a full render pass for one click, and (b) `rerenderAll()` still rebuilt ~50 render functions' DOM unconditionally regardless of which single tab (of ten) was actually visible.

**H3.1 — Eliminate duplicated render passes.** Investigated every mutation path (`markDirty()`, `rerenderAll()`, `setActiveTab()`, and every direct caller of each). Introduced `renderActiveTabIfStale(tabId)`, a dedup guard built on top of a new `renderActiveTabContent(tabId)`:

```javascript
let _lastRenderedTab = null;
let _lastRenderedAtDataGeneration = -1;

function renderActiveTabContent(tabId) {
  (PAGE_RENDERERS[tabId] || []).forEach(fn => {
    try { fn(); } catch (e) { console.error(fn.name || tabId, e); }
  });
  _lastRenderedTab = tabId;
  _lastRenderedAtDataGeneration = _dataGeneration;
}

function renderActiveTabIfStale(tabId) {
  if (_lastRenderedTab === tabId && _lastRenderedAtDataGeneration === _dataGeneration) return;
  renderActiveTabContent(tabId);
}
```

Deliberately reuses Phase 26.39's `_dataGeneration` counter as the "has anything actually changed" signal rather than a new, fragile standalone boolean — any real mutation bumps it via `invalidateDataCache()`, and any real tab switch changes `tabId`, so the guard can only ever skip a true no-op, never a render that would show stale data. Called consistently from `markDirty()`, `rerenderAll()`, and `setActiveTab()`.

**H3.2 — Render only what is needed.** Step 1: produced a dependency map by tracing every render function's actual DOM target against the static HTML's tab-panel boundaries (not the legacy `rerenderXOnly()` groupings, several of which mixed multiple tabs together — e.g. the old `rerenderSummaryOnly()` also rendered `tab-analytics`/`tab-bankroll`; `rerenderManualOnly()` also rendered `tab-pending`/`tab-live`). Step 2: implemented gating as one coherent dispatcher (`PAGE_RENDERERS`, a `const` tab-id → function-array map) rather than scattering `if (state.activeTab === ...)` checks across ~50 individual render functions:

```javascript
const PAGE_RENDERERS = {
  'tab-summary':     [renderTopDecisionBlock, renderSummaryHeadlineStats, renderAlertsCenter, renderOpenBets, renderSummary, renderBankrollChart, renderMobileHomeDash],
  'tab-day':         [renderFootball, syncQuickMarketButtons, renderPicksKpiRow],
  'tab-history':     [renderClosedRealTable, renderHistoryKpiRow, renderHistoryIntelligence, renderHistoryTimeline, renderHistoryEquity],
  'tab-manual':      [renderManualScout, renderManualBets],
  'tab-pending':     [renderPendingQueue],
  'tab-live':        [renderLiveCenter],
  'tab-analytics':   [renderAnalytics, renderAnalyticsPerformers, renderLeagueAnalytics],
  'tab-versus':      [],   // renderVersus() is GLOBAL — see below
  'tab-strategylab': [renderStrategyLab],
  'tab-bankroll':    [renderBankrollPage],
  'tab-settings':    []
};
```

`rerenderAll()` now calls `renderActiveTabIfStale(state.activeTab)` instead of unconditionally calling every `rerenderXOnly()`/KPI/analytics/bankroll renderer in sequence. `setActiveTab()` also calls `renderActiveTabIfStale(tabId)` on every activation — since a switch to a new `tabId` never matches `_lastRenderedTab`, this always renders on switch, guaranteeing every tab is fully current the instant it becomes active regardless of how long it has been since that tab last rendered. **This is explicitly not lazy-loading:** every tab panel remains fully mounted in the DOM at all times (ADR-005 unchanged); the only thing skipped is redundant re-computation of a page the user cannot currently see.

**Cross-tab dependency found and preserved as a deliberate exception.** `renderVersus()` (tab-versus, "Bot vs Manual") populates `window._opnSimCache`, consumed by Strategy Lab, the Recommendation Engine, Opinion Validation, and the Simulator regardless of which tab is active. Initially gated to `PAGE_RENDERERS['tab-versus']` like every other page, this broke all four dependents (caught by `test_strategylab.js`'s "Compare Against Production" check failing with `Cannot read properties of null (reading 'replay')`). Fixed by emptying `PAGE_RENDERERS['tab-versus']` and instead calling `renderVersus()` unconditionally inside `rerenderAll()`, with a comment explaining why. Its own cost is negligible (~0.18–0.22s on the real account) — a full internal refactor to make the cache lazily computed per-consumer was considered and rejected as unnecessary complexity for a negligible-cost function, and out of this phase's scope.

**Live-input regression found and fixed.** `markDirty()`'s new active-tab-aware render dispatch, when the active tab is `tab-pending` (where the Odd Real/Stake Real inputs live), rebuilt that page's DOM on every keystroke — destroying the input being typed into and leaving the fresh replacement unbound (caught by `test_h2_cache_correctness.js`'s "Odd edit" check). Fixed with two new parameters: `markDirty(skipRender = false)` and, inside `bindBotTableControls()`'s shared `update()` closure, a 4th parameter `skipActiveTabRender`. The `.js-odd-real`/`.js-stake-real` `oninput` handlers now call `update(key, changes, false, true)`, passing `true` through to `markDirty(true)` — the edit still invalidates the cache and schedules the cloud save, it simply doesn't force an immediate re-render of the page the user is actively typing in.

**Step 3 — Timings.** Measured with Playwright against the real production account (`cloud_state.json`: 93 history rows, 90 manual bets, 280 localEdits) at each stage:

| Action | Original (audit baseline) | After H1 (26.38) | After H2 (26.39) | After H3 (26.40) |
|---|---|---|---|---|
| `rerenderAll()` | 87.7s | 28.7s | ~1.1–1.2s | **~0.18s** |
| Approve bot pick | *(part of the 87.7s baseline)* | 35.9s | ~2.3–2.7s | **~0.22s** |
| Cancel bot pick | *(part of the 87.7s baseline)* | 41.9s | ~0.7–0.8s | **~0.20s** |
| Navigate to another tab | *(cost was effectively 0 pre-H3 — a CSS `display` toggle only; only 4 of 10 tabs had a dedicated fresh-render call on activation at all, so navigating to the other 6 could silently show stale content)* | same as Original | same as Original | **10–350ms**, proportional to the destination page's own weight — see below; now *guaranteed* fresh, closing the pre-H3 staleness gap |
| Opening Analytics | not separately measured; full `rerenderAll()` cost on any mutation | same | same | **~819ms** (heaviest single page — 3 functions, largest per-league aggregation) |
| Opening Strategy Lab | not separately measured | same | same | **~10ms** |
| Opening Pending | not separately measured | same | same | **~14ms** |
| Opening History (first visit this generation) | not separately measured | same | same | **~343ms** |
| Re-opening History (no mutation since, dedup path) | not separately measured | same | same | **~2ms** |

**Percentage improvement.** `rerenderAll()`: 87.7s → ~0.18s, a **99.8% reduction** from the original audit baseline (H1: -67.3%; H2: additional -96% off H1; H3: additional ~84% off H2). Approve: 87.7s-class → ~0.22s. Cancel: 87.7s-class → ~0.20s. Combined H1+H2+H3, every one of the 8 named actions now completes in under 1 second on the real, full-scale production account; seven of the eight complete in under 350ms.

**Remaining measurable bottleneck.** Opening Analytics (~819ms) is now the single heaviest action measured — proportional to that page's own three render functions (`renderAnalytics`, `renderAnalyticsPerformers`, `renderLeagueAnalytics`) running their own per-league/per-market aggregations over the full history, not to any cross-tab or duplicate-render cost. This is expected, page-proportional cost, not a regression or an oversight — no further action taken, per this task's explicit scope ("Recommendation for any future optimisation — do not implement it," see below).

**Validation.** New 20-check targeted Playwright script (`test_h3_dispatcher.js`): (1) `renderActiveTabContent()` runs only the active tab's own group plus the deliberately-global `renderVersus()`; (2)–(3) navigating to `tab-manual`/`tab-history` after an external state mutation (no explicit render in between) shows fresh, not stale, content; (4) opening every other tab throws no error; (5) a single Approve click renders `tab-day`'s own content exactly once, not twice. Full existing regression harness re-run and green: 13 Playwright suites (`test_approve_stake_default.js`, `test_calibration_v2.js`, `test_csv_wins_precedence.js`, `test_h2_cache_correctness.js`, `test_h3_dispatcher.js`, `test_opinion_validation.js`, `test_part1_fixes.js`, `test_pending_stake_rec.js`, `test_recommendations.js`, `test_sim_perf.js`, `test_simulator.js`, `test_stakereal_zero_guard.js`, `test_strategylab.js`), all fully passing — covering the Manual Bet lifecycle, bot pick approval/cancel, bankroll, exposure, mobile card rendering, cloud load/save simulation, and every analytics module (Strategy Lab, Recommendation Engine, Opinion Validation, Simulator). No user-visible value, calculation, exposure, bankroll, settlement, or persistence behaviour changed anywhere in this phase — confirmed both by the regression suite and by direct comparison of every KPI/exposure/bankroll figure before and after.

**Recommendation for future optimisation (not implemented, out of this phase's scope).** If Analytics' ~819ms ever becomes a user-facing concern (it did not meet this audit's threshold for action), the next investigation would be a data-layer profile specifically of `renderAnalyticsPerformers()`/`renderLeagueAnalytics()`'s per-league grouping — likely a candidate for the same memoization pattern Phase 26.39 already applied elsewhere, since a per-league breakdown is itself a pure function of already-cached `state` for one generation. No other rendering-architecture gap was found during this phase's dependency audit.

**Observation (not a defect, not fixed — outside this phase's scope).** `rerenderPendingOnly()` and `rerenderLiveOnly()` (in `index.html`) lost their only caller when `pendingCancel()`'s redundant explicit render calls were removed in Part 1 (Issue A); both remain defined but are now unused dead code. Left in place rather than deleted, to keep this phase's change minimal — see `03_Dashboard.md` §5 "Superseded partial renderers" and `07_Current_Status.md` Next Priorities.

### Files Modified

| File | Change |
|---|---|
| `index.html` | `pendingCancel()`: added `bindBotTableControls()`, removed 3 redundant explicit render calls (Issue A). `addMovement()` and the delete-movement handler: `invalidateDataCache()` replaced with `markDirty()` (Issue B). New `PAGE_RENDERERS` map, `renderActiveTabContent()`, `renderActiveTabIfStale()`, `_lastRenderedTab`/`_lastRenderedAtDataGeneration`. `rerenderAll()` rewritten to dispatch via the active-tab guard plus the `renderVersus()` GLOBAL exception. `markDirty()` gained a `skipRender` parameter. `bindBotTableControls()`'s inner `update()` closure gained a `skipActiveTabRender` parameter, used by the `.js-odd-real`/`.js-stake-real` handlers. `setActiveTab()`'s old 5-tab if/else chain replaced with a single `renderActiveTabIfStale(tabId)` call plus `bindBotTableControls()`/`bindManualControls()` |
| `docs/09_Architecture_Decisions.md` | New ADR-016 — the active-tab-gated rendering decision |
| `docs/03_Dashboard.md` | §2 rendering pipeline diagram and §5 "Rendering Architecture" rewritten to describe the dispatcher, `PAGE_RENDERERS`, the `renderVersus()` exception, and the now-superseded partial renderers |
| `docs/08_Change_Log.md` | This Phase 26.40 entry added |
| `docs/07_Current_Status.md` | Updated for this phase; "Next Priorities" performance item resolved and replaced with a dead-code cleanup note |

---

## Phase 26.39 — Data-Layer Memoization Cache (Performance Audit H2)

**Implemented:** 2026-07-15

**Goal.** Implement only the second optimisation identified by the completed Performance Audit, narrowly scoped to its confirmed next bottleneck: after Phase 26.38 (H1), `renderPendingQueue()` — the Pending page's own legitimate render — remained at ~15–20s on the real account, because its per-row `computeRecommendedStake()` call (one per pending bot pick) cascades into `getStakeContext() → getRiskMetrics() → getMetrics()`, and none of that chain was cached: every one of the ~27 pending rows re-triggered the same ~9 full history/manual-bet array rebuilds from scratch.

**Step 1 — Dependency audit.** Traced the call graph for all 9 named functions (`getHistoryRowsMerged`, `getDailyRowsMerged`, `getAllBotRowsMergedUnique`, `getManualRowsMerged`, `getResolvedManualBets`, `getRiskMetrics`, `getMetrics`, `getStakeContext`, `computeRecommendedStake`) by reading each definition. Confirmed all 9 ultimately derive from exactly 7 state containers (`footballHistory`, `footballDaily`, `manualBets`, `manualBetsRemote`, `localEdits`, `movements`, `bankrollInicial`/`bankrollInicialSet`) plus `sessionStartDate` (fixed for a session) — one tightly-coupled cluster, not several independent ones. Confirmed all 8 (excluding `computeRecommendedStake`, which additionally takes an external `row` parameter) are pure functions of `state` for a fixed generation — none read `Date.now()`/`todayIso()` directly. By contrast, `getPendingRows()`/`getPendingCount()` (not in the named list) additionally gate on kickoff-vs-now, so they are deliberately excluded from caching.

**Step 2 — Cache design.** One shared cache object (`_dataCache`) plus one monotonically-increasing counter (`_dataGeneration`), not one cache per function and not one cache per page. `memoizeDataFn(name, fn)` wraps a function so a call is served from `_dataCache[name]` when `entry.gen === _dataGeneration`, otherwise recomputes and stores the new value tagged with the current generation. `invalidateDataCache()` is `_dataGeneration++` — O(1), safe to call redundantly. A single coarse cluster-wide invalidation was chosen deliberately over one cache per function: given the dependency audit found near-total overlap in the underlying state containers, fine-grained "invalidate only the affected cache" would still need to invalidate nearly everything on nearly every mutation, while adding real risk of missing one — the exact failure class (stale data shown to the user) this project's Known Issues history has already hit more than once (DASHBOARD-4, DASHBOARD-5, LIVE-1, SYNC-1), for unrelated reasons.

**Step 3 — Invalidation strategy.** Grepped every assignment to the 7 tracked state containers (~35 raw lines, resolving to ~20 distinct functions). Found the existing `markDirty()` function is already called by the large majority of local-edit mutation paths (bot pick approve/edit, `pendingCancel()`, manual bet approve/reject/analyze/save/create/settle) — added `invalidateDataCache()` as its first line, covering all of them in one change. Found and explicitly instrumented the ~13 mutation paths that do **not** go through `markDirty()` (confirmed by reading each, not assumed): `loadData()` (CSV reload — boot, 60s interval, post-settlement), `_doLoadCloudState()` (cloud load), `_reloadManualBetsFromCloud()` (cloud reload after settlement), `importManualJsonFromFile()`, `addMovement()` and the delete-movement handler (bankroll movements never called `markDirty()` — a pre-existing quirk, confirmed harmless here since the new cache invalidation was added independently rather than relying on it), `loadLocalState()` (boot, defensive), `resetLocalControls()`/`resetFinancialConfig()`/`clearManualLocal()` (Settings resets), `executeSeasonClose()`, and the two "set initial bankroll" input `blur` handlers.

**Step 4 — Implementation.** Converted the 8 pure functions from `function name() {...}` declarations to `const name = memoizeDataFn('name', function () {...});` — a mechanical wrapping with zero change to any function body. `computeRecommendedStake()` itself was not touched at all; it benefits automatically because its own expensive dependency (`getStakeContext()`) is now cached. Consumers across the file (~80 call sites) needed no change — the wrapped functions keep the same name and signature.

### Files Modified

| File | Change |
|---|---|
| `index.html` | New cache infrastructure (`_dataGeneration`, `_dataCache`, `invalidateDataCache()`, `memoizeDataFn()`) added after the `state` declaration; 8 functions converted to memoized form; 13 explicit `invalidateDataCache()` calls added at non-`markDirty()` mutation points; `markDirty()` itself gained one line |
| `docs/08_Change_Log.md` | This Phase 26.39 entry added |
| `docs/07_Current_Status.md` | Updated for this phase; "Next Priorities" updated with the new residual cost |
| `docs/handovers/handover-2026-07-15-datalayer-cache-perf.md` | New handover |

`docs/03_Dashboard.md` — **no change required.** Grepped for every one of the 9 function names plus `_dataGeneration`/`invalidateDataCache` — none are described in that document (it documents page *behaviour*, which this phase does not change). `05_Known_Issues.md`, `09_Architecture_Decisions.md`, `06_Roadmap.md`, `01_Architecture.md`, `04_Backend.md`, `PROJECT_MAP.md` — no change made (out of this task's explicit documentation scope).

### Architectural Decisions

None formally recorded (no ADR added, per this task's instruction — "unless the cache architecture introduces a genuine architectural decision"). The single-shared-cache-with-one-generation-counter design is a genuine, deliberate structural choice with real trade-offs (see Step 2 reasoning above) and does constrain future work in the sense that any new function added to this cluster should reuse `memoizeDataFn()`/`invalidateDataCache()` rather than introducing a second cache mechanism — but it is additive to the existing data layer, doesn't change any external behaviour, persistence format, or ADR, and was judged not to rise to the level of a new ADR. Flagged here for visibility in case a future session judges otherwise.

### Validation

- **Syntax:** `node --check` on both extracted `<script>` blocks — clean, at every stage of implementation.
- **Correctness (Playwright, targeted script, scratchpad, not committed — `pwtest/test_h2_cache_correctness.js`, 10 checks):** a memoized function returns the identical object reference on a second call with no mutation (proves the cache is actually used); `getRiskMetrics()`/`getPendingRows()`-adjacent values update correctly after Approve, Cancel, a Stake Real edit, an Odd Real edit, manual bet creation, manual bet deletion, a simulated settlement (CSV result written), and a simulated cloud reload (`manualBets`/`movements` replaced) — all 10 pass.
- **Full existing 11-suite Playwright regression harness** (all 10 standing suites plus the new cache-correctness suite): all pass. Fixing this required updating the pre-existing test scripts' seeding code — every one of them seeds `state.*` by direct assignment (bypassing every real mutation function, which all now invalidate), so each needed one `invalidateDataCache()` call added after its seed block to keep working correctly with the new cache; this is a test-harness-only change (no test file is part of the committed repository) and does not reflect any change to application behaviour.
- **`python -m pytest tests/`:** 186/186 passed, unchanged — no Python file touched.
- **`git diff --stat`:** confirms only `index.html` changed for the code portion of this phase.

### Impact

`renderPendingQueue()` (H1's largest remaining cost) dropped from ~18.8s to ~0.11s (-99.4%) on the real account. `rerenderAll()` — which fires on every Approve/Cancel/edit — dropped from ~28.7s (post-H1) to ~1.1–1.2s (-96%), for a combined reduction from the original 87.7s audit baseline of over 98%. No user-visible value changed: Pending ordering/filtering, Stake recommendations, StakeReal, Bankroll, Exposure, History, Strategy Lab, Recommendation Engine, Opinion Validation, and Simulator are all confirmed unaffected by the full regression suite.

---

## Phase 26.38 — Removed Unnecessary `getPendingRows()` Calls From Count-Only Callers

**Implemented:** 2026-07-15

**Goal.** Implement only the first, highest-impact optimisation identified by the completed Performance Audit (prior session), narrowly scoped: remove every call to `getPendingRows()` where the caller only needs a count, without touching `getPendingRows()` itself, without introducing caching, without changing rendering architecture, and without any unrelated cleanup.

**Root cause (confirmed).** The audit measured `rerenderAll()` at **87.7 seconds** on the real production account and traced 97% of that cost to four functions: `renderAlertsCenter()` (23.7s), `renderSummaryHeadlineStats()` (18.9s), `renderTopDecisionBlock()` (17.5s), and `renderPendingQueue()` (15.2s). The first three do not render the Pending page at all — they call `getPendingRows()` (via `computeAlerts()`, or directly) purely to read `.length`. Since Phase 26.36, `getPendingRows()`'s bot-row mapping calls `computeRecommendedStake()` for every pending bot pick, which cascades through `getStakeContext() → getRiskMetrics() → getMetrics()` — roughly **9 independent full rebuilds of the entire history and manual-bet arrays per pending row**. With 271 approved bot picks in the real account's `localEdits`, this made every count-only call as expensive as the legitimate, data-needing call in `renderPendingQueue()`.

**Fix.** Added `getPendingCount()` (`index.html`, immediately before `getPendingRows()`): it mirrors `getPendingRows()`'s two filter predicates (manual: `isLocal && status==='approved'` + future kickoff/date; bot: `apostada && unsettled` + future kickoff/date) but stops at `.length` — it never calls `.map()`, never calls `computeRecommendedStake()`, and never builds a row object. `computeAlerts()`, `renderSummaryHeadlineStats()`, and `renderMobileHomeDash()` now call `getPendingCount()` instead of `getPendingRows().length`. **`getPendingRows()` itself was not modified in any way** (confirmed via `git diff` — the only changes are the three one-line call-site swaps and the new, self-contained function). `renderPendingQueue()` — the Pending page's own renderer — still calls `getPendingRows()` exactly as before.

**Correctness verification (before measuring performance).** Confirmed `getPendingCount() === getPendingRows().length` on the real dataset (27 === 27), and re-confirmed after both an Approve and a Cancel mutation (both counts moved together, staying equal). Since the filter predicates are identical and the `.map()` step never changes which rows pass the filter, the two are mathematically guaranteed to agree for any state, not just the one tested.

### Files Modified

| File | Change |
|---|---|
| `index.html` | New `getPendingCount()` helper (~30 lines) added before `getPendingRows()`; `computeAlerts()`, `renderSummaryHeadlineStats()`, `renderMobileHomeDash()` — one-line call-site swap each. `getPendingRows()` and `renderPendingQueue()` unmodified |
| `docs/08_Change_Log.md` | This Phase 26.38 entry added |
| `docs/07_Current_Status.md` | Updated for this phase; "Next Priorities" gained an entry for the remaining `renderPendingQueue()` cost |
| `docs/handovers/handover-2026-07-15-pending-count-perf.md` | New handover |

`docs/03_Dashboard.md` — **no change required.** Grepped for `getPendingRows`/`getPendingCount`/`computeAlerts`/`renderSummaryHeadlineStats` — none of these internals are described in that document (it documents the Pending page's *behaviour*, which is unchanged). `05_Known_Issues.md`, `09_Architecture_Decisions.md`, `06_Roadmap.md`, `01_Architecture.md`, `04_Backend.md`, `PROJECT_MAP.md` — no change required (out of this task's explicit documentation scope; no architectural decision, no roadmap priority shift, no backend/repository-structure change).

### Architectural Decisions

None. A new, minimal, single-purpose counting function alongside an existing one; no new persistence path, no caching layer, no change to any render's data source for actual display.

### Measurements — Before vs After (real production dataset: 93 history rows, 90 manual bets, 271 approved picks)

| Operation | Before (audit) | After (this phase) | Δ | % |
|---|---|---|---|---|
| `rerenderAll()` | 87.7s | 28.7s | -59.0s | **-67.3%** |
| `renderAlertsCenter()` | 23.7s | 1.10s | -22.6s | **-95.4%** |
| `renderSummaryHeadlineStats()` | 18.9s | 0.28s | -18.6s | **-98.5%** |
| `renderTopDecisionBlock()` | 17.5s | 1.09s | -16.4s | **-93.8%** |
| `rerenderSummaryOnly()` (fans out to the three above + `renderAnalytics()`'s 8 sub-panels) | 55.8s | 6.10s | -49.7s | **-89.1%** |
| `renderPendingQueue()` | 15.2s | 18.8s | ~unchanged (run-to-run noise) | *by design — out of scope* |
| `rerenderManualOnly()` (dominated by `renderPendingQueue()`) | 19.8s | 19.7s | ~unchanged | *by design — out of scope* |
| Approve bot pick (click, full pipeline) | *(not isolated in the audit; inferred from `rerenderAll()`)* | 35.9s | — | *see Notes* |
| Cancel bot pick (`pendingCancel()`) | *(not isolated in the audit)* | 41.9s | — | *see Notes* |

**Notes on the Approve/Cancel numbers:** these two actions still route through `renderPendingQueue()` (Cancel calls it twice — once via `rerenderPendingOnly()`, once via `rerenderManualOnly()`'s own call to it), so they remain dominated by the same, deliberately-untouched cost this task was scoped to leave alone. This is expected and consistent with `renderPendingQueue()` now being the largest remaining single cost — see "Next Priorities."

### Validation

- **Syntax:** `node --check` on both extracted `<script>` blocks — clean.
- **Correctness (Playwright, ad hoc script, not committed):** `getPendingCount() === getPendingRows().length` on real data, and after an Approve and a Cancel mutation.
- **Full existing 10-suite Playwright regression harness** (the 9 standing suites plus Phase 26.36/26.37's `test_pending_stake_rec.js`, which exercises Pending sorting/filtering/mobile/desktop/Stake rec./Stake Real extensively): all 10 pass completely, zero console/page errors — confirming Pending page behaviour, ordering, filtering, Stake recommendation, StakeReal, manual bets, Alerts, Decision block, Summary KPIs, Open Exposure, Bankroll, History, Strategy Lab, Recommendation Engine, Opinion Validation, and Simulator are all unaffected.
- **`python -m pytest tests/`:** 186/186 passed, unchanged — no Python file touched.
- **`git diff --stat`:** confirms only `index.html` changed for the code portion of this phase.

### Impact

Approving, cancelling, or editing a bot pick — the most common interactions — no longer pays for a hidden, redundant ~9x full-dataset rebuild inside three functions that never needed more than a number. The measured, real-account improvement (87.7s → 28.7s per `rerenderAll()`) is large but **smaller than the audit's own rough estimate** ("~10–15s" after this fix alone) — see the Comparison Against Audit Findings section returned in this session's report for why, and "Next Priorities" for the recommended next step.

---

## Phase 26.37 — Pending Desktop Header Reverted to "Stake" (Value Unchanged)

**Implemented:** 2026-07-15

**Goal.** Pure UI-wording refinement, immediately following Phase 26.36 in the same investigation thread. Phase 26.36 correctly fixed *what value* the Pending page's bot rows display (`computeRecommendedStake()` instead of the raw model stake), but also renamed the desktop table's single shared column header to "Stake rec." That header sits above **both** row types in one table — bot rows, where "Stake rec." is accurate, and manual rows, where it is not: manual bets have no model/recommended/real distinction, so labelling their own plainly-entered stake as a "recommendation" is semantically wrong. This phase corrects the header wording only.

**Fix.** The desktop `<th>` at `index.html`'s Pending table markup reverted from `<th>Stake rec.</th>` to `<th>Stake</th>`. Nothing else changed: `getPendingRows()`'s `botRows` mapping still sources `.stake` from `computeRecommendedStake(r).value` (the same function call, unchanged since Phase 26.36); `manualRows` still sources `.stake` from `b.stake`. The mobile card's per-row `stakeLabel` (`'Stake rec.'` for bot, `'Stake'` for manual — introduced in Phase 26.36) already had exactly the semantics this phase asks for and needed no change. The inline comment above `botRows`' mapping was extended to explain the desktop-header/mobile-label distinction for future readers.

### Files Modified

| File | Change |
|---|---|
| `index.html` | Pending table's desktop `<th>` reverted `"Stake rec."` → `"Stake"`; explanatory comment above `botRows` mapping extended. No value/logic change |
| `docs/03_Dashboard.md` | Pending page section's desktop-header description corrected to match |
| `docs/08_Change_Log.md` | This Phase 26.37 entry added |
| `docs/07_Current_Status.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-15-pending-stake-rec.md` | Superseded/updated — see Notes |

`05_Known_Issues.md`, `09_Architecture_Decisions.md`, `06_Roadmap.md`, `01_Architecture.md`, `04_Backend.md`, `PROJECT_MAP.md` — **no change required.**

### Architectural Decisions

None — a column-header wording change through the same already-shared `<th>`/`getPendingRows()` mechanism Phase 26.36 used; no new logic, dependency, or persistence path.

### Validation

- **Syntax:** `node --check` on both extracted `<script>` blocks of `index.html` — clean.
- **Playwright, targeted script (19 checks, scratchpad, not committed — `pwtest/test_pending_stake_rec.js`, updated in place to assert the new header text since it verifies current intended behaviour, not a frozen snapshot):** desktop header reads "Stake" and no longer "Stake rec."; bot rows' `.stake` is still exactly `computeRecommendedStake()`'s value (both the "followed recommendation" and "deliberate override" cases); manual row `.stake` is unchanged; unapproved picks still absent from Pending; mobile card still shows "Stake rec.:" for bot and plain "Stake:" for manual; Daily Picks' `_stakeModeloNum` source untouched; `getRiskMetrics().stakeOpen` and bankroll unaffected; `state.manualBets` byte-identical; History renders without error; sorting preserved.
- **Full existing 9-suite Playwright regression harness:** all 9 suites pass completely, zero console/page errors.
- **`python -m pytest tests/`:** 186/186 passed, unchanged.
- **`git diff --stat`:** confirms only `index.html` changed for the code portion of this phase.

### Impact

The Pending page's desktop "Stake" column is now semantically correct for both row types it displays — a single neutral label ("the operational stake associated with this pending bet") rather than a recommendation claim that didn't hold for manual rows. The actual values shown, sorting, filtering, exposure, bankroll, approval flow, and History are all unaffected — this phase changed one header string and one code comment.

---

## Phase 26.36 — Pending Page Shows "Stake rec." Instead of Raw Model Stake for Bot Picks

**Implemented:** 2026-07-15

**Goal.** Pure UX fix, explicitly scoped to display only — no bankroll, settlement, persistence, exposure, StakeReal, or recommendation-algorithm change. A prior session's design review (Task 2 of the StakeReal-zero-guard session) found that the Pending page's "Stake" column shows the raw model stake (`_stakeModeloNum`, the same underlying value as Daily Picks' "Stake mod." column), while "Stake Real" is auto-filled from a *different* figure — `computeRecommendedStake()`'s "Stake rec." (Phase 26.33/26.35). Once a pick is approved, the raw model stake is no longer the operationally relevant comparison; the user wants to see "what we recommended" next to "what was actually staked."

**Investigation before changing anything (per instruction).** Traced every place the Pending table obtains its displayed Stake value: `getPendingRows()` (`index.html`) is the single source, consumed only by `renderPendingQueue()` (desktop table) and `buildPendingCardHtml()` (mobile card) — both purely presentational; no KPI, exposure, or bankroll calculation reads `.stake` from this function (every consumer that isn't one of those two render functions only reads `.length`, confirmed by grep). `getPendingRows()` builds two disjoint row shapes in one array: `manualRows` (`.stake = b.stake`, the manual bet's own entered stake — no model/rec/real split exists for manual bets) and `botRows` (`.stake` was `r._stakeModeloNum`). Only the `botRows` branch needed to change.

**Fix.** `getPendingRows()`'s `botRows` mapping now computes `const recStake = computeRecommendedStake(r).value;` per row and uses `recStake` (formatted via the same `fmt()` helper, same null-safety pattern) as `.stake`, instead of `r._stakeModeloNum`. This is the exact same function call Daily Picks and the Phase 26.33/26.35 approval auto-fill already use — no second implementation, no duplicated formula. The `manualRows` branch is untouched. The desktop table header (`<th>Stake</th>` → `<th>Stake rec.</th>`) and the mobile card's per-row label (a new `stakeLabel` local: `'Stake rec.'` for `_type === 'bot'`, `'Stake'` unchanged for `_type === 'manual'`) were updated to match — the mobile card is actually more precise than the desktop table here, since its label is computed per-row-type rather than shared across one column.

### Files Modified

| File | Change |
|---|---|
| `index.html` | `getPendingRows()`'s `botRows` mapping — `.stake` now sourced from `computeRecommendedStake(r).value` instead of `r._stakeModeloNum` (reused, not duplicated); desktop `<th>Stake</th>` → `<th>Stake rec.</th>`; `buildPendingCardHtml()` gained a per-row `stakeLabel` (`'Stake rec.'` for bot rows, `'Stake'` unchanged for manual rows) |
| `docs/03_Dashboard.md` | Pending page section corrected/extended to describe both the bot-pick and manual-bet halves of `getPendingRows()` (the bot-pick half was previously undocumented — see Additional Observations) and the new Stake rec. source |
| `docs/08_Change_Log.md` | This Phase 26.36 entry added |
| `docs/07_Current_Status.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-15-pending-stake-rec.md` | New handover |

`05_Known_Issues.md`, `09_Architecture_Decisions.md`, `06_Roadmap.md`, `01_Architecture.md`, `04_Backend.md`, `PROJECT_MAP.md` — **no change required.** This phase fixed no open issue (the underlying UX gap was never filed as a Known Issue — it was a design-review finding, not a confirmed bug), introduced no architectural decision (a display-source swap through an already-shared function, not a new persistence path or structural change), and shifted no roadmap priority.

### Architectural Decisions

None. `getPendingRows()` already computed derived display fields from merged row data; this changes which already-existing function supplies one of those fields. `computeRecommendedStake()` itself is untouched, and no new call pattern or dependency was introduced — Daily Picks and the approval handler already called this same function per-row.

### Validation

- **Syntax:** `node --check` on both extracted `<script>` blocks of `index.html` — clean.
- **Playwright, targeted script (19 checks, scratchpad, not committed — `pwtest/test_pending_stake_rec.js`):** desktop header renamed to "Stake rec." (old plain "Stake" header absent); a bot pick that followed the recommendation exactly shows Stake rec. === Stake Real; a bot pick whose real stake was deliberately overridden shows Stake rec. ≠ Stake Real, with Stake Real reflecting the user's real value untouched; an unapproved bot pick still does not appear on Pending; the manual bet row's `stake` is completely unchanged (still its own entered value, not run through `computeRecommendedStake()`); the desktop table's rendered cell text matches the underlying Stake rec. value; the mobile card shows "Stake rec.:" for bot rows and the unchanged plain "Stake:" for the manual row; Daily Picks' underlying `_stakeModeloNum` source is untouched; `getRiskMetrics().stakeOpen` and bankroll `totalAccountValue` are unaffected by the display change; `state.manualBets` is byte-identical; the History page renders without error; Pending rows remain sorted by date ascending.
- **Full existing 9-suite Playwright regression harness** (`test.js`, Opinion Validation, Recommendations, Simulator, Strategy Lab, Calibration v2, Phase 26.33's approval-default test, Phase 26.34's CSV-wins-precedence test, Phase 26.35's StakeReal-zero-guard test): all 9 suites pass completely, zero console/page errors.
- **`python -m pytest tests/`:** 186/186 passed, unchanged — no Python file was touched.
- **`git diff --stat`:** confirms only `index.html` changed for the code portion of this phase.

### Impact

The Pending page's "Stake rec." column for bot picks now shows exactly the same figure the approval auto-fill used (or would use), directly adjacent to "Stake Real." Equal values confirm the recommendation was followed; a difference is now an intentional, legible signal that the user adjusted the stake — rather than an always-present, confusing mismatch against a raw model figure that was never the operational target after approval. Manual bet rows, Daily Picks, exposure, bankroll, settlement, persistence, and StakeReal behaviour are all unaffected.

---

## Phase 26.35 — Fixed StakeReal Auto-Fill Guard to Treat Zero/Invalid Values as "Not Set"

**Implemented:** 2026-07-15

**Goal.** A read-only investigation (this session, prior turn) traced why the Phase 26.33 StakeReal auto-fill worked for some bot picks but not others — e.g. a real approved pick ("Mjallby AIF vs Vasteras SK FK") showed `StakeReal = €0.00` and did not contribute to Open Exposure, while a comparable pick approved the same way worked correctly. Fix the root cause without touching `computeRecommendedStake()`, exposure calculation, or bankroll calculation.

**Root cause.** The Phase 26.33 guard was `const existingStakeReal = cleanString(...stakeReal ?? ''); if (!existingStakeReal) { …auto-fill… }` — a JavaScript string-truthiness check. `"0"` is a non-empty string, so `!"0"` is `false`: a stored `stakeReal` of exactly `"0"` was treated identically to a real, deliberately-typed stake, and the guard silently skipped the default forever. Confirmed against the live `cloud_state.json`: the affected pick's `localEdits` entry was `{ apostada: true, stakeReal: "0" }`. `computeRecommendedStake()` cannot legitimately produce this value itself — its output is hard-floored by `clamp(x, 1, maxCap)` (`maxCap = Math.max(2, bankroll*0.04) ≥ 2`), so it always returns either `null` (non-finite input) or a number `≥ 1`. The only code path capable of writing a literal `"0"` is the free-form `.js-stake-real` number input on the Pending page (`min="0"`, no floor validation), and `pendingCancel()` (the "Cancelar" handler) deliberately preserves `stakeReal`/`oddReal` across a cancel — so a stray `"0"` typed once, then cancelled and re-approved, would silently re-trigger the same suppression indefinitely. `getRiskMetrics()`'s exposure sum (`sum(...).filter(v => v !== null)`) does not filter out `0`, so the affected pick was correctly counted as open but contributed exactly €0.00 — exposure was faithfully summing bad input data, not miscalculating.

**Fix.** The guard now parses the existing value with the same `num()` helper used everywhere else in the file, and auto-fills whenever the parsed value is not a meaningful positive stake:
```js
const existingStakeRealNum = num(state.localEdits[key]?.stakeReal);
if (existingStakeRealNum === null || existingStakeRealNum <= 0) {
  // …unchanged: look up row, compute recommended, auto-fill…
}
```
`num()` already returns `null` for empty string, `undefined`, and any non-numeric/invalid string (it parses via `Number()` and checks `Number.isFinite()`), and the `<= 0` check additionally catches zero and negative values. A genuine positive value the user typed (or a prior auto-fill) is left completely untouched, exactly as before. Single change point, same file/function/line range as Phase 26.33. `computeRecommendedStake()`, `getRiskMetrics()`, and every bankroll/ROI function are byte-identical to before this phase.

### Files Modified

| File | Change |
|---|---|
| `index.html` | `.js-bot-approve` click handler (`bindBotTableControls()`) — guard changed from string-truthiness to a parsed-numeric `null`/`<=0` check (9 lines changed, one function, same location as Phase 26.33) |
| `docs/08_Change_Log.md` | This Phase 26.35 entry added |
| `docs/05_Known_Issues.md` | New `DASHBOARD-5` resolved entry |
| `docs/07_Current_Status.md` | Updated for this phase |

`03_Dashboard.md`, `09_Architecture_Decisions.md`, `06_Roadmap.md`, `01_Architecture.md`, `04_Backend.md`, `PROJECT_MAP.md` — **no change required.** `03_Dashboard.md`'s existing Phase 26.33 note ("defaults an empty `stakeReal`...") already describes the intended behaviour correctly; this phase only corrects which stored values count as "empty" for that purpose, which doesn't change the documented behaviour description itself. No architectural decision was introduced (see Architectural Decisions below), no roadmap priority shifted, and no backend/repository-structure file was touched.

### Architectural Decisions

None. This is a bug fix to the exact non-ADR mechanism Phase 26.33 introduced (a workflow default written through the pre-existing `localEdits[pickKey].stakeReal` field and edit pipeline) — it corrects which stored values are treated as "already set," it does not introduce a new persistence path, change `computeRecommendedStake()`/Kelly/bankroll logic, or touch settlement. Nothing here constrains future implementation choices the way an ADR would, consistent with Phase 26.33's own ADR assessment.

### Validation

- **Syntax:** `node --check` on both extracted `<script>` blocks of `index.html` — clean.
- **Playwright, targeted script (23 checks, scratchpad, not committed — `pwtest/test_stakereal_zero_guard.js`), driving the real bound click handler in a real browser:** first approval (no prior edit) auto-fills to "Stake rec."; an existing positive stake ("7.5") is preserved exactly; a stale `stakeReal: "0"` is now replaced with "Stake rec." (the fix); an empty string, a non-numeric string (`"abc"`), and a negative value (`"-3"`) are all replaced identically; a full Cancel→re-approve cycle (approve → simulate a stray "0" edit → Cancelar, which correctly still preserves the "0" per `pendingCancel()`'s unrelated, unchanged behaviour → re-approve) now replaces the stale zero instead of perpetuating it; `getRiskMetrics().stakeOpen` sums every approved pick's corrected real stake plus an untouched manual bet exactly; bankroll `totalAccountValue` is unaffected (no settlement occurred); the Pending page (`getPendingRows()`) reflects the corrected value; the History page renders without error; `state.manualBets` is byte-identical before/after every bot-pick approval; `localStorage[STORAGE_KEYS.picks]` persists the corrected value and `hasPendingCloudChanges` is correctly flagged (cloud-save trigger path unchanged); the identical fix was verified again from the mobile card render path (`buildPicksCardHtml()`/`isMobileDashboard()`), confirming both approval surfaces share the one corrected code path.
- **Full existing 8-suite Playwright regression harness** (`test.js`, Opinion Validation, Recommendations, Simulator, Strategy Lab, Calibration v2, Phase 26.33's approval-default test, Phase 26.34's CSV-wins-precedence test): all 8 suites pass completely, zero console/page errors.
- **`python -m pytest tests/`:** 186/186 passed, unchanged — no Python file was touched.
- **`git diff --stat`:** confirms only `index.html` changed (9 lines) for the code portion of this phase.

### Impact

A bot pick whose `stakeReal` is empty, undefined, invalid, zero, or negative at the moment of approval now always receives the "Stake rec." default, matching the behaviour Phase 26.33 originally intended. A genuinely-entered positive stake is still never overwritten. This also fixes the case where a pick is approved, has its `StakeReal` accidentally cleared/zeroed on the Pending page, is cancelled, and is later re-approved — the stale zero no longer survives that cycle. No data migration was performed: any pick currently sitting at a stale `stakeReal: "0"` in `cloud_state.json` will self-correct the next time it goes through Cancelar → Aprovar (or any other action that re-runs the guard); it is not retroactively rewritten by this change alone.

---

## Phase 26.34 — Automated Settlement Always Wins Over a Manual Result Override

**Implemented:** 2026-07-15

**Goal.** A reported inconsistency on "Huntsville City vs Crown Legacy" (2026-06-21) — dashboard showed `Result = P`, `Profit = €0.00`, but `picks_history.csv` had `Resultado`/`Lucro€`/`LucroReal€`/`Apostada`/`OddReal`/`StakeReal€` all empty. Root-cause first (prior session, read-only), then fix the underlying design flaw once confirmed.

**Root cause (from the prior read-only investigation).** `getRowWithLocalEdits()` computed `resultadoFinal = ['W','L','P'].includes(resultadoManual) ? resultadoManual : resultadoBase` — `localEdits[pickKey].resultadoManual` (set via the History page's result dropdown or "Live Settle" — `settleBotBet()`) **permanently** took precedence over the CSV's own `Resultado`, with no reconciliation once automated settlement later produced a real result. For the Huntsville fixture this was benign — the CSV never got a result at all, so the override was correctly bridging a genuine gap. But a systematic scan of all 12 historical `resultadoManual` uses against the current `picks_history.csv` found **two real conflicts**: "Saint Etienne vs Nice" (2026-05-26, real stake €1 @ 1.7) displayed a stale manual `W` (+€0.70) when automated settlement had since determined `L` (should be −€1.00); "Nice vs Saint Etienne" (2026-05-29, real stake €1 @ 2.0) displayed a stale manual `P` (€0.00) when automated settlement had since determined `W` (should be +€1.00). Both are silently distorting real bankroll/ROI figures right now.

**Investigation before implementing.** Traced every consumer of `resultadoManual` (4 occurrences total: the default initializer, the read/precedence site, and two write sites — the History dropdown and `settleBotBet()`) and every place gating on the resulting `_resultKey`/`_resultadoFinal`. Confirmed the precedence logic exists in exactly one place (`getRowWithLocalEdits()`) plus one secondary consumer with an equivalent gap: `getDailyRowsMerged()`'s cross-file reconciliation (borrowing a result from `picks_history.csv` when a row's own daily-CSV cell is empty) was gated on `enriched._resultKey === 'pending'` — a condition a manual override would already have satisfied away from `'pending'`, silently skipping the reconciliation even when history had a real, possibly-conflicting automated result. Confirmed Strategy Lab, Opinion Validation, the Recommendation Engine, and the Simulator are entirely unaffected: all four consume settled **manual bets** (`state.manualBets`, own `resultado` field, gated on `b.hadAnalysis === true`), a completely disjoint data model from bot picks' `localEdits.resultadoManual` — verified by tracing each feature's data-source function.

**Fix.**
- `getRowWithLocalEdits()`: `resultadoFinal` now prefers a valid CSV `resultadoBase` whenever one exists; `resultadoManual` is consulted only when the CSV cell is empty/invalid.
- `getDailyRowsMerged()`: the cross-file reconciliation condition changed from `enriched._resultKey === 'pending' && found` to `!ownCsvResult && found` (checking the row's own raw CSV cell directly, not the post-override `_resultKey`) — so history's real result now wins even when this row's own file cell is empty and a manual override had already filled the gap.
- **No automatic deletion of stale `resultadoManual` values.** Evaluated and rejected: `getRowWithLocalEdits()` runs on effectively every render; mutating `state.localEdits` from inside it would make a pure "compute merged row" function silently stateful (risking unexpected `markDirty()`/cloud-save cascades from rendering), and would destroy the exact audit trail that made finding the two conflicts above possible. A stale override is simply never read once the CSV has a real result — present in `cloud_state.json["localEdits"]`, inert. See ADR-015.

### Files Modified

| File | Change |
|---|---|
| `index.html` | `getRowWithLocalEdits()` precedence flipped (CSV wins); `getDailyRowsMerged()`'s cross-file reconciliation condition changed to check the row's own raw CSV cell instead of the post-override `_resultKey` |
| `docs/03_Dashboard.md` | `state.localEdits` schema note extended with the new precedence rule |
| `docs/09_Architecture_Decisions.md` | New ADR-015 |
| `docs/05_Known_Issues.md` | New `DASHBOARD-4` resolved entry |
| `docs/08_Change_Log.md` | This Phase 26.34 entry added |
| `docs/07_Current_Status.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-15-csv-wins-precedence.md` | New handover |

### Validation

- **Playwright, targeted script (10 checks, scratchpad, not committed) covering every scenario requested:** CSV empty + `resultadoManual=W` → dashboard shows W; CSV later becomes L → dashboard now shows L; bankroll/profit and the History/ROI aggregation row (`getFilteredRealClosedRows()`) both update to reflect L; Strategy Lab's manual-bet pool and the Recommendation Engine/Simulator's `window._opnSimCache` build normally and are demonstrably sourced only from manual bets (unaffected); a fixture with **only** a manual settlement (CSV never resolves, ever) still shows its manual result exactly as before — no regression to the bridge behaviour.
- **Verified against real production data** (current `cloud_state.json` + `picks_history.csv` loaded into the real app): "Saint Etienne vs Nice" now resolves to `L`/−€1.00 (was `W`/+€0.70); "Nice vs Saint Etienne" now resolves to `W`/+€1.00 (was `P`/€0.00); "Huntsville City vs Crown Legacy" still correctly resolves to `P` (CSV genuinely still empty) — confirming the fix corrects exactly the two real historical misstatements while leaving the legitimate bridge case untouched.
- **Full existing 7-suite Playwright regression harness** (the 6 standing suites plus Phase 26.33's approval-default test): all pass completely, zero console/page errors.
- **`python -m pytest tests/`:** 186/186 passed, unchanged — no Python file was modified.
- `git diff --stat`: only `index.html` changed (16 lines).

### Impact

Automated settlement is now unconditionally the final source of truth for a bot pick's result once it exists, in both `picks_history.csv` and the daily-CSV cross-file reconciliation. The two previously-misstated historical bets now show their correct, real result and profit. `resultadoManual` continues to work exactly as before for any fixture whose automated settlement never resolves — no migration was performed or required.

---

## Phase 26.33 — Default StakeReal to "Stake rec." on Bot Pick Approval

**Implemented:** 2026-07-15

**Goal.** Requested behaviour change: when a bot pick is approved ("Aprovar" on the Daily Picks page), if the user hasn't entered a `StakeReal` yet, automatically default it to the recommended stake — so a user who always follows the model's recommendation doesn't have to re-type the same number by hand. A user who edits `StakeReal` before approving must always keep their own value.

**Investigation.** Confirmed there is exactly one approval code path for bot picks: the `.js-bot-approve` button, rendered in both the desktop table (`buildBotRowHtml()`) and the mobile cards (`buildPicksCardHtml()`), both always sourced from `getDailyRowsMerged()` and bound by the single `bindBotTableControls()` handler — no duplicate or parallel approval path exists (the similarly-named `.js-approve-manual` button belongs to manual bets and is a separate, untouched code path).

The pick table actually surfaces **two** distinct "recommended stake" figures side by side, and picking the wrong one would have been a real financial-behaviour mistake: **"Stake mod."** (`r._stakeModeloNum`, the raw `Stake€` column — the unmodified Kelly output from `src/calculations.py`) and **"Stake rec."** (`computeRecommendedStake(row).value` — a client-side-only layer on top of Stake mod. that applies a performance-based dynamic multiplier, edge/score/odds adjustments, and an exposure-based cap, then rounds to the nearest €0.50). Confirmed with the user before implementing: the intended source is **"Stake rec."**, the value the pick's own "Stake rec." column already displays — not the raw Kelly figure.

**Fix.** The `.js-bot-approve` click handler in `bindBotTableControls()` now builds its `update()` payload as `{ apostada: true, ...maybe stakeReal }`: it reads the pick's *current* `localEdits[key].stakeReal` first, and only when that's empty does it look up the row via `getDailyRowsMerged().find(r => r._pickKey === key)`, compute `computeRecommendedStake(row).value`, and include it as `stakeReal` (as a string, matching the existing `stakeReal` storage format everywhere else). Both branches still go through the exact same `update()` → `markDirty()` → `saveLocalState()` → `rerenderAll()` pipeline every other local edit already uses — no new persistence path, no new storage key, no CSV column. `computeRecommendedStake()` itself, Kelly, bankroll logic, and settlement are untouched; this only ever writes into the pre-existing `localEdits[pickKey].stakeReal` field, exactly as if the user had typed that number in themselves.

### Files Modified

| File | Change |
|---|---|
| `index.html` | `.js-bot-approve` click handler (`bindBotTableControls()`) now defaults `stakeReal` to `computeRecommendedStake(row).value` when empty at approval time |
| `docs/03_Dashboard.md` | Daily Picks section and `state.localEdits` schema note updated to describe the new default-on-approval behaviour |
| `docs/08_Change_Log.md` | This Phase 26.33 entry added |
| `docs/07_Current_Status.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-15-approve-stake-default.md` | New handover |

### Validation

- **Playwright, targeted script (9 checks, scratchpad, not committed, run against the real `index.html` in a real browser via `bindBotTableControls()`'s actual bound click handler — not a re-implementation):** approving a pick with no `StakeReal` sets it to exactly the displayed "Stake rec." value; approving a pick with an existing `StakeReal` ("7.5") preserves it byte-for-byte; a pick approved in a prior session (pre-existing `stakeReal`) is completely untouched by any of this; `state.manualBets` is byte-identical before/after both bot-pick approvals; `getRiskMetrics().stakeOpen` and the Home page's "Exposição aberta" KPI both immediately reflect the sum of all newly- and previously-approved real stakes plus the untouched manual bet.
- **Full existing 6-suite Playwright regression harness:** all 6 suites (`test.js`, Opinion Validation, Recommendations, Simulator, Strategy Lab, Calibration) re-run in full, all passing, zero console/page errors.
- **`python -m pytest tests/`:** 186/186 passed, unchanged — no Python file was modified.
- `git diff --stat` confirms only `index.html` changed (13 lines) for the code portion of this phase.

### Impact

A user who approves a bot pick without touching "Stake Real" now has it default to the same "Stake rec." figure already shown on that row, and Open Exposure/bankroll risk metrics reflect it immediately. A user who prefers a different stake can still type it in before approving, and that value is never overwritten. No migration was performed or required — previously-approved picks and manual bets are entirely unaffected.

---

## Phase 26.32 — Persist Fixture Metadata on Manual Bets for Consistent Settlement Eligibility

**Implemented:** 2026-07-12

**Goal.** A reported inconsistency: for the same fixture, with both a bot pick and a manual bet on the same market, "Executar Resolução" settled the manual bet immediately but left the bot pick `LIVE`. The bot pick settled correctly on a later run, unattended. Investigate the root cause before changing anything.

**Investigation.** Traced the complete settlement flow: `runSettlement()` → `POST /run-settlement` → `run_settlement_remote()`, which processes bot picks and manual bets **in the same synchronous request**, through the **identical** `update_dataframe()` function, sharing one provider-response cache (`shared_state`). This ruled out a race condition, a caching inconsistency between requests, or a duplicate settlement path — both bet types are already handled atomically by one shared engine (ADR-002/ADR-009).

The actual divergence: `update_dataframe()`'s `KICKOFF_TOO_EARLY` gate (`now < KickoffUTC + RESULT_READY_DELAY`, 2h15m) only executes `if kickoff_str:` — i.e. only when the row has a `KickoffUTC` value at all. Bot picks always do (propagated end-to-end since Phase 26.7–26.9, confirmed in `src/pick_generation.py::build_base_row()`). Manual bets never did: `addManualBetFromFixture()` never set a `kickoffUTC` field on the bet object — confirmed by tracing every manual-bet creation path and the full git history of `kickoffUTC:` assignments in `index.html`. **A documentation claim (Phase 26.7–26.9's own Change Log entry) that this field was "propagated through... manual bet objects" was inaccurate** — only a transient, render-time-only placeholder existed for display formatting, never a persisted, settlement-relevant field (corrected in that phase's entry above).

A further scoping check (before implementing) found that the originally-proposed field list — `fixtureId`, `kickoffUTC`, `league`, `leagueId`, `season` — included three fields (`fixtureId`, `leagueId` as a settlement input, `season`) that bot picks themselves don't persist either: `HISTORY_COLUMNS` has no `FixtureId`/`LeagueId`/`Season` columns, and `update_results.py` never reads any of the three from a row — `season` is derived fresh from `Data` + a league-registry lookup at settlement time, identically for both bet types already. `fixtureId` additionally isn't available anywhere in the client-side data model at all (`fixtures_today.csv`'s schema never included it). Scope was narrowed to what bot picks actually provide and what's genuinely available: `kickoffUTC`, `homeTeam`, `awayTeam`, plus `leagueId` as a cheap, harmless, forward-looking enrichment (derived from the already-fetched `config.json.api_football.league_ids`, no new network call) even though nothing currently consumes it.

**Fix.** `mbHandleCreate()` (the Scout "Criar" flow) now looks up the matching fixture via a new shared `findFixtureRecord()` helper (extracted from the existing `findFixtureKickoff()`, which now delegates to it — no duplicated matching logic) and resolves `leagueId` from the already-cached `config.json`. These are passed into `addManualBetFromFixture()`, which persists `kickoffUTC`, `homeTeam`, `awayTeam`, and `leagueId` on the bet object at creation time — immutable metadata, never re-derived from `state.fixtures` later (that list is a rolling window and the fixture may no longer be in it by settlement time). `manual_bets_to_settlement_df()` already read `bet.get('kickoffUTC')`; it had simply never been given real data. **No change was made to the settlement engine, `RESULT_READY_DELAY`, matching logic, or persistence architecture** (`sync_server.py`'s `/save` and `_dedupe_manual_bets()` are schema-agnostic — confirmed they never strip unrecognized fields).

**Manual bets without a fixture.** The free-form "Apostas Manuais" text-entry form (`addManualBet()`) is untouched — it has no fixture to source metadata from, and per explicit instruction this was preserved as-is rather than worked around. This is a documented, accepted limitation: a free-form manual bet still has no kickoff-eligibility protection, exactly as before this phase.

### Files Modified

| File | Change |
|---|---|
| `index.html` | New `findFixtureRecord()` helper (`findFixtureKickoff()` refactored to use it); `loadModelConfig()` extended to expose `api_football.league_ids`; `mbHandleCreate()` made async, resolves fixture + `leagueId`; `addManualBetFromFixture()` accepts and persists `kickoffUTC`/`homeTeam`/`awayTeam`/`leagueId` |
| `docs/04_Backend.md` | `KICKOFF_TOO_EARLY` step and manual-bet-settlement bridge notes updated |
| `docs/05_Known_Issues.md` | New `SETTLEMENT-2` resolved entry |
| `docs/08_Change_Log.md` | Phase 26.7–26.9 entry annotated (inaccurate claim corrected); this Phase 26.32 entry added |
| `docs/07_Current_Status.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-12-manual-bet-fixture-metadata.md` | New handover |

### Validation

- **Python, direct proof:** ran the real, completely unmodified `update_dataframe()` against three synthetic manual-bet rows — one with a kickoff 30 minutes ago (within the 2h15m delay), one with a kickoff 3 hours ago (past it), one with no `kickoffUTC` at all (simulating a pre-fix bet). Result: the recent-kickoff row was correctly ignored with reason `KICKOFF_TOO_EARLY` (previously it would have proceeded to a live API check immediately); the old-kickoff and no-kickoff rows proceeded past the precheck exactly as before. This proves the fix closes the gap without any settlement-engine change.
- **JavaScript, targeted script (15 checks, scratchpad, not committed):** `findFixtureRecord()`/`findFixtureKickoff()` both work correctly after the refactor; `loadModelConfig()` correctly exposes real `config.json` league IDs; a full Scout "Criar" click persists all four fields with correct values; `fixtureId`/`season` are confirmed absent (scope discipline); the free-form form still creates bets with no metadata fields at all; a pre-existing bet with none of the new fields still loads and renders without error (no migration needed); zero new console errors.
- **Full existing 6-suite Playwright regression harness and `python -m pytest tests/`:** both re-run in full, all passing, unaffected by this change (no Python file was modified; the JS change is additive and isolated to manual bet creation).

### Impact

A bot pick and a manual bet for the same fixture now become eligible for settlement at exactly the same moment. No data migration was performed; existing manual bets (with or without the new fields) continue to work exactly as they did before this phase.

---

## Phase 26.31 — Correct Rejected Bet Lifecycle Visibility (Fix the Right Page)

**Implemented:** 2026-07-11

**Goal.** Phase 26.28 fixed a real bug (a settled rejected bet stayed visible in "Histórico → Rejeitadas" forever) by narrowing `getRejectedManualBets()` to unsettled-only bets. This phase's investigation established that fix targeted the wrong page: "Rejeitadas" was always intended as the permanent archive of rejected bets, settled or not. The actual duplicate-visibility complaint was that the *operational* "Apostas Manuais" list never stopped showing a rejected bet once it settled — since a rejected bet's `status` stays `'rejected'` forever (ADR-012) and that list's filter never checked settlement state at all.

**Investigation — visibility matrix (before this phase).**

| State | Apostas Manuais | Histórico Rejeitadas | Histórico Resolvidas | Strategy Lab | Opinion Val./Rec. Engine/Simulator |
|---|---|---|---|---|---|
| Rejected + Pending | YES | YES | NO | NO | NO |
| Rejected + Settled | **YES (bug)** | **NO (Phase 26.28)** | NO | YES | NO |

**Visibility matrix (after this phase).**

| State | Apostas Manuais | Histórico Rejeitadas | Histórico Resolvidas | Strategy Lab | Opinion Val./Rec. Engine/Simulator |
|---|---|---|---|---|---|
| Rejected + Pending | YES | YES | NO | NO | NO |
| Rejected + Settled | **NO (fixed)** | **YES (reverted)** | NO | YES | NO |

**Fix.**
- `getRejectedManualBets()` reverted to `status === 'rejected'` (no settlement check) — "Rejeitadas" is once again the permanent archive.
- `renderManualBets()`'s row filter (the operational "Apostas Manuais" list) gained one additional exclusion: a `status === 'rejected'` bet with `_lucro !== null` (settled) is now hidden — it no longer needs attention on the page a user actively triages from.
- Both `getRejectedManualBets()`'s and `getRejectedHistoryRows()`'s doc comments updated to describe the corrected, permanent-archive behaviour.

**Scope discipline.** No change to the settlement engine, `cloud_state.json`, CSV schema, bankroll/ROI calculation, `status` values, `QuantEngine`, the Recommendation Engine, Strategy Lab, Opinion Validation, or the Simulator — confirmed by full regression re-run.

### Files Modified

| File | Change |
|---|---|
| `index.html` | `getRejectedManualBets()` reverted (removed the settlement check); `renderManualBets()`'s filter gained the settled-rejected exclusion; both functions' doc comments updated |
| `docs/03_Dashboard.md` | Manual Bets §7 (Rejection step, both wordings) and §9 (Resolvidas/Rejeitadas toggle) updated; ASCII lifecycle diagram corrected |
| `docs/05_Known_Issues.md` | New `DASHBOARD-3` resolved entry documenting the correction; `DASHBOARD-2` annotated to point to it |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-11-rejected-bets-lifecycle-fix.md` | New handover |

### Validation

- **Targeted regression script (new, 24 checks, scratchpad-only, not committed):** seeded rejected+unsettled, rejected+settled, approved+settled, and plain-pending bets; verified `getRejectedManualBets()` now returns both rejected bets (unsettled and settled); `getResolvedManualBets()` and `getStrategyLabPool()` unchanged; the "Apostas Manuais" DOM list shows the unsettled rejected bet but not the settled one; the "Rejeitadas" DOM table shows both; "Resolvidas" shows neither; a settled rejected bet appears in exactly one operational/archive place (Rejeitadas only); all 4 requested lifecycle scenarios (Scout→Reject visible in both pages; Reject→settle disappears from Apostas Manuais but stays in Rejeitadas+analytics; Remove→Scout card reappears; Approved→Live→Settled unchanged) pass.
- **Full existing 6-suite Playwright regression harness:** all 6 suites now pass completely, including `test.js` — its 5 previously-"failing" checks (flagged as expected in Phase 26.28's own handover) were written for the original pre-26.28 behaviour and now pass again, confirming this revert is correct. `test_opinion_validation.js`, `test_calibration_v2.js`, `test_recommendations.js`, `test_simulator.js`, `test_strategylab.js` all pass unchanged.
- **Console/page errors:** zero new errors; only the pre-existing, harness-induced `Failed to fetch` noise from deliberately blocked network calls (confirmed baseline in prior sessions).

### Impact

"Apostas Manuais" is now a true operational list — it only shows bets that still need attention, dropping a rejected bet the moment it's settled. "Histórico → Rejeitadas" is now a true permanent archive — a rejected bet stays there forever regardless of settlement, matching how "Resolvidas" already behaves for non-rejected bets. No duplicate visibility exists anywhere: a settled rejected bet appears in exactly one operational/historical view (Rejeitadas) plus whichever analytical modules were already designed to include it.

---

## Phase 26.30 — Close the Lambda-Boost Duplication Gap (QuantEngine Audit Follow-Up)

**Implemented:** 2026-07-11

**Goal.** A dedicated post-migration architecture audit of Phase 26.29's QuantEngine work found exactly one genuine defect: the per-league lambda-boost application (`lam = clamp(lam * boost, lo, hi)`) existed as identical but independently-maintained inline arithmetic in both `src/pick_generation.py::process_league_fixtures()` and `analyzeFixture()` (`index.html`) — outside `src/calculations.py`, outside `QuantEngine`, and outside the golden-vector conformance suite. This was exactly the class of silent-drift risk ADR-014 exists to close, just not yet closed for this one small piece.

**What was built.**
- `src/calculations.py::apply_lambda_boost(lam_home, lam_away, boost) -> (lam_home, lam_away, lam_total)` — a pure function containing the complete previous inline behaviour (no-op for a falsy/1.0 boost; otherwise multiply-then-clamp each lambda to its existing bounds, recompute the total).
- `src/pick_generation.py::process_league_fixtures()` now calls `apply_lambda_boost()` instead of inlining the clamp-and-multiply.
- `QuantEngine.applyLambdaBoost()` mirrors it exactly in JavaScript, exported from the module.
- `analyzeFixture()` now calls `QuantEngine.applyLambdaBoost(lamH, lamA, boost)` via destructuring assignment instead of inlining the same three lines.
- 8 new golden vectors (typical boost, no-op boost, falsy boost, upper-clamp trigger, sub-1.0 dampening boost) generated directly from the real Python function, added to `tests/golden_vectors.json`. Both `tests/test_quant_engine_golden.py` and `tests/test_quant_engine_golden.js` extended to validate them.

### Files Modified

| File | Change |
|---|---|
| `src/calculations.py` | Added `apply_lambda_boost()` |
| `src/pick_generation.py` | Calls the named function instead of inlining |
| `index.html` | Added `QuantEngine.applyLambdaBoost()`; `analyzeFixture()` calls it instead of inlining |
| `tests/golden_vectors.json` | +8 vectors for `apply_lambda_boost` |
| `tests/test_quant_engine_golden.py`, `tests/test_quant_engine_golden.js` | Extended to cover the new function |
| `docs/09_Architecture_Decisions.md` | ADR-014 updated — Decision and Consequences note the closed gap |
| `docs/01_Architecture.md` | Shared Quantitative Engine section and Pick Generation Flow trace updated |
| `docs/04_Backend.md` | Canonical function list and vector count updated |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-11-quant-engine-boost-fix.md` | New handover |

### Validation

- **Python:** `python -m pytest tests/` — 186/186 passed (was 178; +8 new golden vectors).
- **JavaScript:** `node tests/test_quant_engine_golden.js` — 285/285 assertions passed (was 261; +24, 8 vectors × 3 fields).
- **Byte-identical proof:** the pre-extraction inline formula and the new `apply_lambda_boost()` function produce identical output across 8 representative cases including both clamp branches.
- **Full existing 6-suite Playwright regression harness:** re-run in full — `test_opinion_validation.js`, `test_calibration_v2.js`, `test_recommendations.js`, `test_simulator.js`, `test_strategylab.js` all pass unchanged; `test.js` shows the same 5 pre-existing expected failures from Phase 26.28 (unrelated).
- **Targeted Scout end-to-end re-test:** the 17-check scratchpad test from Phase 26.29 (network fully blocked, exercising the lambda-boost fallback path) re-run and passing, confirming `QuantEngine.applyLambdaBoost()` works correctly end-to-end in the real dashboard.
- **Repeat targeted audit:** confirmed zero remaining inline `lam * boost` clamp arithmetic anywhere in `src/pick_generation.py` or `index.html` outside `src/calculations.py`/`QuantEngine`. The only remaining occurrence of this pattern anywhere in the repository is in `fetch_oddsapi_fixtures.py` — the pre-existing, already-flagged, explicitly out-of-scope Phase-1 fixture-shortlisting script (never part of "the Bot" or "the Scout" as this migration was scoped).

### Impact

**No further quantitative duplication remains inside the production Bot + Scout architecture.** Every formula either lives solely in `src/calculations.py`/`QuantEngine` or is verified identical between the two by the golden-vector conformance suite (now 16 functions, 142 Python / 285 JS assertions). Bot output, Scout output, and every dashboard analytical module are confirmed unchanged.

---

## Phase 26.29 — Shared Quantitative Engine (Python Canonical + Verified JS Mirror)

**Implemented:** 2026-07-11

**Goal.** Determine whether an existing, disconnected "Edge Engine" could be integrated into production (per a prior architectural audit's claim), and — after investigation found that claim did not match the codebase (the production pipeline's own edge computation was already fully integrated; see the standalone investigation earlier this session) — design and implement a genuinely shared Quantitative Engine consumed by both the Python bot and the JavaScript Manual Bet Scout, so both always compute probability/edge/confidence/Kelly/fair-odds from one verified source instead of two independently-maintained copies.

**Current-state inventory (before any code change).** A complete inventory of every quantitative calculation in both languages found: `compute_lambdas`, `poisson_cdf`/`prob_over25`, `btts_prob_diagnostics`/`prob_btts_yes_adjusted`, `kelly_fraction`, and the four `clamp_*` bounds were **duplicated** — a JS `mb*`-prefixed set in `index.html`, explicitly flagged in its own comment as `// Ported from src/calculations.py — do NOT change formulas`. Confidence (`confidence_factor`, embedded inline in `apply_stakes()`) existed only in Python; `FairOdds`/`EV` existed only in JS (`analyzeFixture()`); `MB_HISTORY_CFG` was a hardcoded JS mirror of `config.json`'s `history` block, manually synced. Score and Opinion were confirmed JS-only, correctly outside any engine already.

**Architecture decision.** A literal single-runtime shared engine is not achievable without violating ADR-005 (no build step/framework in `index.html`), adding unnecessary Railway round-trips, or introducing a large new runtime dependency (e.g. Pyodide). Presented three alternatives plus the requested approach to the user before implementing; approved: **Python remains canonical, JavaScript keeps a verified native mirror, and a golden-vector conformance test suite is the permanent guarantee of behavioural equivalence** — converting "one authoritative implementation" from an unenforceable textual property into a tested behavioural one. See ADR-014 for the full reasoning.

**What was built.**
- `src/calculations.py`: three new named, canonical functions — `confidence_factor(edge, scale=0.10)` (extracted from `apply_stakes()`'s inline formula, byte-identical, verified via before/after comparison), `fair_odds(prob_model)`, `expected_value(prob_model, odd, stake)`.
- `src/market_rules.py::apply_stakes()`: now calls `confidence_factor()` instead of an inline pandas expression — same formula, now named and independently testable.
- `index.html`: a new isolated `QuantEngine` module (delimited by `QUANT_ENGINE_START`/`QUANT_ENGINE_END` markers for test extraction) — pure functions only, no DOM/`state`/network reference — exposing `poissonCdf`, `probOver25`, `probBttsDiagnostics` (now returns the full diagnostic breakdown, matching Python — previously the JS version only returned the final probability), `probBttsAdjusted`, `kellyFraction`, the four `clamp*` functions, `confidenceFactor` (new), `fairOdds`, `expectedValue`, `weightedMean`, `computeLambdas` (now takes `cfg` as a parameter instead of reading a module-level default), and a convenience composite `analyzeMarket()`.
- A **rounding fidelity fix** found only by running the conformance suite: Python's `btts_prob_diagnostics()` rounds several returned fields (`raw_poisson`, `after_base_adj`, `total_penalty`, `final_prob_unclamped` to 6dp; `lam_ratio`/`lam_gap`/`lam_product` to 4dp) — and the *rounded* `final_prob_unclamped` is what feeds the rest of Python's pipeline (clamp, edge, Kelly). The JS mirror initially returned unrounded values; added a `roundN()` helper to match Python's rounding exactly (JS's round-half-away-from-zero vs. Python's round-half-to-even differ only on an exact decimal tie, which transcendental function outputs essentially never produce).
- `loadModelConfig()`: fetches `config.json` once per session (GitHub raw-content URL, same mechanism as picks CSVs — not a Railway round-trip), cached, with a frozen-defaults fallback if the fetch fails — replacing the hardcoded `MB_HISTORY_CFG` mirror.
- `analyzeFixture()`: rewritten to call `QuantEngine.*` for every quantitative value, with a new `classifyManualOpinion()` helper cleanly separating the Score/Opinion decision layer from the quantitative section above it. Output shape is unchanged plus two new additive fields (`Confidence`, `diagnostics`) — every existing key any caller reads is preserved.
- `tests/golden_vectors.json`: 134 input→output pairs computed once directly from the real `src/calculations.py` functions, covering every branch (BTTS penalty thresholds, lambda fallback vs. team-specific, Kelly boundary conditions, clamp edges).
- `tests/test_quant_engine_golden.py` (Python, pytest) and `tests/test_quant_engine_golden.js` (Node, zero dependencies — extracts and evaluates `QuantEngine` directly out of `index.html`) replay the same vectors against each implementation.
- `tests/test_quant_engine.py`: 15 unit tests for the three new Python functions, including a direct comparison against the pre-extraction inline formula.

### Files Modified

| File | Change |
|---|---|
| `src/calculations.py` | Added `confidence_factor()`, `fair_odds()`, `expected_value()` |
| `src/market_rules.py` | `apply_stakes()` now calls `confidence_factor()` instead of an inline expression |
| `index.html` | New `QuantEngine` module; `analyzeFixture()` rewritten to consume it; new `classifyManualOpinion()`; new `loadModelConfig()`; `MB_HISTORY_CFG` replaced by `MB_HISTORY_CFG_FALLBACK` |
| `tests/golden_vectors.json` | New — frozen conformance vectors |
| `tests/test_quant_engine_golden.py`, `tests/test_quant_engine_golden.js` | New — cross-language conformance suites |
| `tests/test_quant_engine.py` | New — unit tests for the three new Python functions |
| `docs/01_Architecture.md` | New "Shared Quantitative Engine" component section; Pick Generation Flow updated; new architectural rule |
| `docs/03_Dashboard.md` | Scout's analysis step (§7 Step 2) rewritten to describe QuantEngine consumption |
| `docs/04_Backend.md` | New §15 "Shared Quantitative Engine"; `apply_stakes()` pseudocode updated to show `confidence_factor` |
| `docs/09_Architecture_Decisions.md` | New ADR-014 |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase |
| `docs/PROJECT_MAP.md` | `calculations.py`/`tests/` entries updated |
| `docs/handovers/handover-2026-07-11-quant-engine.md` | New handover |

### Validation

- **Python:** `python -m pytest tests/` — 178/178 passed (29 season model + 15 new unit tests + 134 new golden vectors).
- **JavaScript:** `node tests/test_quant_engine_golden.js` — 261/261 assertions passed across 15 functions.
- **End-to-end bot behaviour:** `apply_stakes()` run on identical synthetic input before (git `HEAD`, dynamically loaded in isolation) and after the refactor — `Stake€`/`StakeFrac` outputs byte-identical.
- **Full existing 6-suite Playwright regression harness:** `test_opinion_validation.js` (19/19), `test_calibration_v2.js` (11/11), `test_recommendations.js` (22/22), `test_simulator.js` (26/26), `test_strategylab.js` (32/32 — including explicit checks that the pool still includes rejected bets and the production baseline still excludes them) all pass unchanged. `test.js` shows the same 5 pre-existing expected failures from Phase 26.28 (unrelated, already documented there) — nothing new regressed.
- **New end-to-end Scout tests (scratchpad, not committed):** 17 checks exercising `analyzeFixture()`'s full path with network fully blocked (proving the `config.json`/history fetch failures fall back gracefully, exactly as before) for both O2.5 and BTTS markets; 9 checks exercising the happy-path `config.json` fetch against the real file, confirming correct parsing, mapping, and caching.
- **Syntax:** `node --check` clean on both extracted `<script>` blocks throughout.

### Impact

Bot pick generation, settlement, CSV output, and every dashboard analytical module (Strategy Lab, Opinion Validation, Recommendation Engine, Simulator) are unchanged. The Scout now reads the exact same formulas and the exact same `config.json` values as the bot, with a permanent, low-maintenance automated guard (261+134 assertions, zero new runtime dependencies) against the two ever silently diverging again — closing the gap a prior session's own code comment had already flagged as a manually-policed risk.

---

## Phase 26.28 — Hide Settled Rejected Bets From History → Rejeitadas

**Implemented:** 2026-07-11

**Goal.** A rejected manual bet stayed visible in the History page's "Rejeitadas" view forever, even after settlement gave it a real result — at the same time, the same bet correctly began appearing in Strategy Lab, Opinion Validation, and other analytics once settled (by design, per ADR-012). This created the appearance of the same analytical record being visible in two places at once. The expected behaviour: a rejected bet has two phases — (1) rejected + unsettled → visible in Rejeitadas; (2) rejected + settled → automatically disappears from Rejeitadas, remains fully available everywhere analytical (Strategy Lab, Opinion Validation, Recommendation Engine, Simulator, Bot vs Manual). This is not a data-loss fix — the bet is never deleted, only a presentation filter changes.

**Investigation (full trace before any change).**
- **Storage:** `cloud_state.json` → `manualBets` array (ADR-001/ADR-008) — unaffected.
- **Settlement writes:** the backend's `apply_df_results_to_manual_bets()` populates `resultado`, `placar`, `lucro`/`Lucro€`, `settledAt` on the bet object; `status` is left at `'rejected'` if it was already `'rejected'` (ADR-012) — confirmed via source inspection, not assumed.
- **Every filter site traced:** `getResolvedManualBets()` (`b._lucro !== null && b.status !== 'rejected'`) — used by Manual Bets financials, History "Resolvidas", Bot vs Manual, Opinion Validation, Recommendation Engine, Simulator — already correctly excludes all rejected bets regardless of settlement, untouched by this phase. `getRejectedManualBets()` — the only broken one, and the only function History "Rejeitadas" consumes (via `getRejectedHistoryRows()`, its sole caller). `getStrategyLabPool()` — reads `state.manualBets` directly, filtered only by `hadAnalysis && botOpinion && resultado∈{W,L,P}` — deliberately includes rejected bets by design (a documented, pre-existing decision, unrelated to this bug), untouched.
- **Root cause confirmed:** `getRejectedManualBets()` filtered only on `status === 'rejected'`, with zero check on settlement state, so a settled rejected bet never dropped out of the one view meant to show "awaiting outcome" rejected bets.
- **Quality review (post-fix):** searched the codebase for an existing "is settled"/"is resolved"/"is open bet" helper before finalising the fix. None exists anywhere in `index.html` — the established convention is the raw inline check `_lucro === null`/`!== null` (already used 5+ times, including inside the sibling function `getResolvedManualBets()`) or `_resultKey === 'pending'` (used 6+ times). Per that convention, no new helper was introduced for this single call site.

**Fix.** One predicate change:
```js
function getRejectedManualBets() {
  return getManualRowsMerged().filter(b => b.status === 'rejected' && b._lucro === null);
}
```
Plus updated doc comments on `getRejectedManualBets()` and `getRejectedHistoryRows()` that had explicitly documented the old ("shows settled or not") behaviour as intentional.

### Files Modified

| File | Change |
|---|---|
| `index.html` | `getRejectedManualBets()` predicate narrowed to unsettled-only (`&& b._lucro === null`); two doc comments updated |
| `docs/03_Dashboard.md` | 4 passages updated (Manual Bets §, Step 5 lifecycle narrative, ASCII lifecycle diagram, §9 Resolvidas/Rejeitadas toggle) that previously documented the old behaviour as intentional |
| `docs/05_Known_Issues.md` | New resolved-issue entry, `DASHBOARD-2` |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-11-rejected-bets-fix.md` | New handover for this phase |

### Validation

- **Quality review search.** Grepped for `function is[A-Z]`, `function has[A-Z]`, `function.*settl`, `const isSettled/isResolved/isPending/isOpen` across `index.html` — no dedicated settlement-state helper exists anywhere; `_lucro === null`/`!== null` and `_resultKey === 'pending'` are the only established conventions, both used repeatedly already. Confirms the fix correctly follows existing convention rather than needing a new or reused abstraction.
- **Syntax.** `node --check` on both extracted `<script>` blocks — zero errors.
- **Targeted regression script (new, 19 checks, scratchpad-only, not committed):** seeded 4 manual bets (rejected+unsettled, rejected+settled, approved+settled, plain pending) and verified: `getRejectedManualBets()` returns exactly the unsettled rejected bet; `getResolvedManualBets()` unchanged (still excludes all rejected bets, settled or not); `getStrategyLabPool('all')` still includes the settled rejected bet; the Rejeitadas DOM table shows only the unsettled rejected bet; the Resolvidas DOM table shows neither rejected bet; zero duplicate visibility across History tables; the Pending→Rejected→(settled)→disappears-from-Rejeitadas-but-stays-in-state transition; the unrelated Remove transition still works. All 19 checks passed both before and after the "quality review" step (no code changed between the two runs, since no helper was reused).
- **Full existing 6-suite Playwright harness re-run:** `test_opinion_validation.js` (19/19), `test_calibration_v2.js` (11/11), `test_recommendations.js` (22/22), `test_simulator.js` (26/26), `test_strategylab.js` (32/32 — including the explicit "Strategy Lab pool INCLUDES the rejected BUY bet" and "Production baseline excludes the rejected bet" checks) all pass unchanged. The pre-existing `test.js` shows 5 **expected** post-fix "failures" that assert the old (buggy) behaviour (e.g. "Rejected bet appears in `getRejectedManualBets()` with its settlement result") — the direct, intended consequence of this fix, not a regression; that scratchpad test file is not committed to the repository and was not edited.
- **Console/page errors.** Zero real errors in any run; the only console output observed anywhere was the pre-existing `Failed to fetch` noise from the test harness's deliberate network-blocking (confirmed identical on the unmodified suite, i.e. baseline, not caused by this fix).

### Impact

History → Rejeitadas now shows exactly what its name implies: rejected bets still awaiting an outcome. Once settled, a rejected bet is no longer duplicated across "Rejeitadas" and the analytical modules that are supposed to include it — it appears exactly once, in the modules designed to use it (Strategy Lab, Opinion Validation, Recommendation Engine, Simulator, Bot vs Manual), and nowhere in the two History tables. No data was deleted or altered; this is a presentation-only fix.

---

## Phase 26.27 — Remove Legacy NBA Subsystem

**Implemented:** 2026-07-11

**Goal.** A prior session's read-only audit (documented in that session's conversation, not a separate file) established that the repository contained a fully self-contained, parallel NBA pick-generation pipeline that shared zero code with the football system — no `sport` abstraction exists anywhere in `src/`, and every NBA script had its own config, own state file, own Telegram sender, and own data file. The audit found the NBA automation had run near-hourly from 2026-03-01 to 2026-04-30 (driven by something outside this repository, since `.github/workflows/bot.yml` never contained NBA scheduling at any point in its history) and had been dormant for 10+ weeks. This phase executes the approved removal: delete every NBA-exclusive artifact and the three dead NBA keys sitting inertly inside the shared `config.json`, with zero change to football behaviour.

**Archival safeguard.** Before any deletion, an annotated git tag `legacy-nba-final` was created at the pre-removal commit (`77dc981e`) as a permanent, unmodified snapshot — the NBA subsystem remains fully recoverable from that tag if ever needed again.

**What was deleted.**
- `fetch_fixtures_nba.py`, `run_job_nba.py`'s orchestrated fixture fetcher (100 lines)
- `fetch_oddsapi_fixtures_nba.py` — an earlier, superseded duplicate fixture fetcher, dead since the day after `fetch_fixtures_nba.py` was created (131 lines)
- `gerar_picks_nba.py` — the NBA pick-generation model, its own Telegram sender, its own dedup state (518 lines)
- `run_job_nba.py` — the orchestrator that ran the two scripts above (15 lines)
- `prepare_nba_small.py` — an orphaned, one-off local data-prep script hardcoded to a path that only ever existed on the original developer's machine (34 lines)
- `config_nba.json` — NBA model parameters, read exclusively by `gerar_picks_nba.py` (29 lines)
- `picks_nba_over.csv` — stale NBA pick output, last updated 2026-04-30 (5 rows)
- `data_raw/nba.csv` — historical NBA box-score data, read exclusively by `gerar_picks_nba.py` (13,561 rows / 496 KB)

**What was edited.** `config.json`: removed `bankroll.nba_over`, the `rules.nba_over` sub-block, and the top-level `nba` block (window/sigma_total). These three keys were verified dead in the prior audit by tracing every `config.json` accessor in `src/runtime.py` and `src/market_rules.py` — none ever look up an `nba`-prefixed key. Confirmed again this session by direct comparison (see Validation).

**Scope discipline.** No football file was modified. `main.py`, `update_results.py`, `sync_server.py`, `run_main.py`, `run_topup.py`, and every `src/*.py` module are byte-for-byte identical to the `legacy-nba-final` tag (`git diff legacy-nba-final -- <file>` returns zero lines for each). Only `config.json` changed, and only by removing the three dead keys.

### Files Modified

| File | Change |
|---|---|
| `fetch_fixtures_nba.py`, `fetch_oddsapi_fixtures_nba.py`, `gerar_picks_nba.py`, `run_job_nba.py`, `prepare_nba_small.py`, `config_nba.json`, `picks_nba_over.csv`, `data_raw/nba.csv` | Deleted |
| `config.json` | Removed `bankroll.nba_over`, `rules.nba_over`, top-level `nba` block — nothing else changed |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-11-nba-removal.md` | New handover for this phase |
| `README.md`, `CLAUDE.md`, `docs/PROJECT_MAP.md` | Verified — no change required (see Documentation Updated in the handover for why) |

### Validation

- **Search.** Full repository search (content + filenames, tracked and untracked, excluding `.venv/`) for `NBA`, `nba`, `basketball`, `basketball_nba`, `picks_nba`, `fixtures_today_nba`, `sent_state_nba`, `config_nba`, `prepare_nba`, `run_job_nba`, `fetch_fixtures_nba`, `generate_nba`, `hoops` — zero genuine matches. The only hits were case-insensitive substring false positives inside unrelated `index.html` identifiers (`actionBadge`, `decisionBadge`, `btnBase`), confirmed by inspecting every match directly.
- **Syntax.** `python -m py_compile` on every tracked `.py` file — zero errors.
- **Test suite.** `pytest tests/` — 29/29 passed (`test_season_model.py`), unaffected by this change.
- **Imports.** `import main`, `run_main`, `run_topup`, `update_results`, `sync_server`, and every module in `src/` — all import cleanly with zero errors.
- **Configuration equivalence.** Loaded `config.json` from both the working tree (post-edit) and the `legacy-nba-final` tag (pre-edit) and called `src.runtime.build_runtime_settings()` / `build_bankroll_settings()` on both. Every football-consumed derived field (`bankroll25`, `rules25`, `bankroll_btts`, `rules_btts`, and the full runtime-settings dict) is identical before and after — the only difference is the raw echoed config no longer contains the now-removed `nba_over` sub-keys, which is the intended effect.
- **Settlement path.** `update_results.py` never reads `config.json` at all, and is byte-for-byte identical to the `legacy-nba-final` tag (`git diff` returns zero lines) — settlement is provably unaffected without needing to exercise it against live provider APIs.
- **Pick generation.** `main.py` is likewise byte-for-byte identical to the tag. Combined with the config-equivalence check above, pick generation's inputs and code are both unchanged. The live pipeline was deliberately not executed as a validation step — it would consume metered API-Football/football-data.org quota and could trigger real Telegram notifications for a change that provably touches none of its logic.
- **Dashboard.** `index.html` has zero diff against the `legacy-nba-final` tag. Both `<script>` blocks (main app, ~672 KB, and a small secondary block) pass `node --check` with no syntax errors.
- **Documentation links.** No document in `docs/`, `CLAUDE.md`, or `README.md` ever referenced any of the deleted files (confirmed in the prior audit and re-confirmed this session), so no link can be broken by their removal.
- **Incidental artifact cleanup.** Running the Python validation commands above regenerated several tracked `__pycache__/*.pyc` bytecode files as a side effect; these were restored (`git checkout --`) before committing so the commit contains only the intended NBA-removal changes.

### Impact

The repository is now exclusively a football betting system. No shared code existed between the two pipelines, so this removal carried none of the risk a genuine shared-infrastructure untangling would have — every deleted file's only callers were other NBA files, and the three removed config keys were provably unread by any football code path both before this session's audit and reconfirmed here.

---

## Phase 26.26 — Repository Hygiene Cleanup

**Implemented:** 2026-07-11

**Goal.** Resolve a set of unexplained working-tree changes and untracked files that had been carried across three consecutive sessions without action (first flagged in the 2026-07-10 handover, repeated in 2026-07-11): two uncommitted root-file deletions, an untracked `.claude/` directory, an untracked `CLAUDE.md`, and four untracked diagnostic `audit_output*.txt` files. Every item was investigated via `git log`/`git show`/file content before any change was made — no assumption was made about intent, and one genuinely ambiguous decision (whether to restore a root `README.md`) was confirmed with the user before acting.

**Findings.**
- `PROJECT_RULES.md` (single commit, 2026-05-21) predates the `docs/` system (first committed 2026-07-01) by over a month. Its content — no-framework rule, page list, UI direction — is superseded by `00_Project_Context.md`, ADR-005, and `03_Dashboard.md`; its page list (`Home/Picks/...`) no longer matches the current dashboard (`Daily Picks/Live Center/Pending/...`), confirming it was stale, not just redundant.
- Root `README.md` (single commit, 2026-05-01) had only ever contained the placeholder `"# force deploy"` — never real documentation. Confirmed with the user: replace with a real, concise landing-page README rather than restore the placeholder or leave the repository without one.
- `.claude/settings.json` and `.claude/settings.local.json` had never been committed. `settings.local.json` is machine-specific by Claude Code's own naming convention and must not be shared; `settings.json` is a low-risk, shared project permission safe to commit.
- `CLAUDE.md` had never been committed, despite `docs/PROJECT_MAP.md`, `08_Change_Log.md` ("Doc System" row), and `07_Current_Status.md` all describing it as an established, permanent part of the repository since 2026-06-29. This was the one confirmed documentation/repository inconsistency — the docs weren't wrong about what should exist, just ahead of what had actually been committed.
- The four `audit_output*.txt` files matched, byte-for-byte in content and structure, the "temporary, read-only audit harness" described in ADR-011 / Phase 26.18 (the API-Football subscription-lapse investigation). That issue has been resolved and fully documented since 2026-07-07; the files were leftover diagnostic instrumentation with no ongoing reference value.

**Actions taken (all approved by the user before execution).**
1. Committed the deletion of `PROJECT_RULES.md`.
2. Replaced the root `README.md` placeholder with a concise landing page: project description, architecture summary, repository structure, and pointers to `docs/README.md` and `CLAUDE.md`.
3. Committed `CLAUDE.md` and `.claude/settings.json` for the first time.
4. Deleted the four `audit_output*.txt` files.
5. Added `.claude/settings.local.json` and `audit_output*.txt` to `.gitignore` to prevent both patterns from recurring uncommitted/unexplained.

**No code, business logic, or runtime behaviour changed.** This phase touched only repository metadata, root-level documentation, and tooling configuration.

### Files Modified

| File | Change |
|---|---|
| `PROJECT_RULES.md` | Deleted (superseded by `docs/`) |
| `README.md` | Replaced placeholder content with a real landing page |
| `CLAUDE.md` | Committed for the first time (content unchanged — already matched the documented workflow) |
| `.claude/settings.json` | Committed for the first time |
| `.gitignore` | Added `.claude/settings.local.json` and `audit_output*.txt` |
| `audit_output.txt`, `audit_output_v3.txt`, `audit_output_v4.txt`, `audit_output_v5.txt` | Deleted (never committed; obsolete diagnostic output from the already-resolved Phase 26.18 investigation) |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-11-repo-cleanup.md` | New handover for this phase |

### Validation

- `git log --all`, `git show`, and full-content review performed on every item before any recommendation was made — no action taken on assumption.
- Confirmed no remaining reference to `PROJECT_RULES.md` anywhere outside historical (point-in-time) handover records.
- Confirmed `.claude/settings.local.json` and `audit_output*.txt` are excluded by `git status --ignored` after the `.gitignore` update.
- Confirmed `git status` is clean except for the intentional staged changes described above.

### Impact

The repository working tree now matches what the documentation has described for up to three sessions. No further "unexplained leftover" carries forward into the next session.

---

## Phase 26.25 — Full Dashboard Localization to European Portuguese (PT-PT)

**Implemented:** 2026-07-11

**Goal.** `03_Dashboard.md` §1 and `DEVELOPMENT_GUIDELINES.md` have long stated the rule "keep all UI text in PT-PT, do not mix languages" — but the rule had drifted from reality. The Season Archive/Close Season wizard was entirely in English, and the four Opinion analytics features added in Phases 26.20–26.24 (Opinion Validation, Opinion Engine Recommendations, Recommendation Simulator, Strategy Lab) had shipped with English copy throughout, alongside assorted older English labels scattered across the Bot vs Manual and Analytics tabs (table headers, KPI card titles, insight sentences, alerts). This phase closes that gap: every visible string in `index.html` was translated to natural PT-PT, and nothing else changed.

**Scope discipline.** Pure text/localization pass. No calculation, threshold, condition, algorithm, data flow, persistence, API, or HTML structural change (beyond width/wrapping adjustments implied by longer Portuguese phrases in a handful of labels). No variable, function, or object-key was renamed.

**The one structural addition — `ptLabel()`.** Several rule engines (Opinion Validation's calibration/confidence tiers, Opinion Engine Recommendations' severity levels, the League Analytics tier/action badges, the Analytics tab's confidence/knowledge-score badges) store and compare English constants directly — e.g. `calibMeta.label === 'Broken'`, `SEV_ORDER[r.severity]`, `confidence.label === 'Very Low'` — and also render that same string as the visible badge text. Renaming those constants to Portuguese would have meant finding and updating every comparison across four features without being able to verify each one exhaustively, for no functional benefit. Instead, a single shared lookup, `ptLabel(label)` (backed by `PT_LABEL_MAP`, `index.html` near `escapeHtml()`), maps the English constant to its PT-PT display form only at the point of rendering — every `===` comparison, object key, and `SEV_ORDER`/`confMap`/`LEAGUE_ACTION_CODE_LABEL`-style lookup continues to compare the original English string, untouched. `ptLabel()` is called 47 times across the file; anything not in `PT_LABEL_MAP` passes through unchanged (safe no-op for whitelisted terms like `STRONG BUY`/`AVOID`).

**What was translated.** Sidebar navigation, page titles/subtitles, the Strategy Builder card, Settings page; the Season Archive viewer and 4-step Close Season wizard (`renderArchiveDetail()`, `csmRenderStep1()`–`csmGoStep4()`, `csmExecute()`, `validateArchive()`'s error reasons); the Opinion Validation, Opinion Engine Recommendations, Recommendation Simulator, and Strategy Lab sections in full (headers, table columns, insight/recommendation sentences, evidence labels, empty states); the pre-existing Bot vs Manual analytics (League Performance, Drawdown, Score Bands/Calibration/Insights, Edge Realization, Model Quality Score/Trust/Executive Summary, Action Engine) and Analytics tab (League/Market Validation, Knowledge Score, Findings/Lessons, Confidence Score/Alerts); assorted alert/confirm dialogs and empty-state messages throughout.

**Whitelisted, intentionally untranslated:** `ROI`, `Edge`, `Scout`, `Bot`, `Strategy Lab`, `JSON`, `CSV`, `API`, `GitHub`, `Railway`, `Cloudflare`, `R2`, `BTTS`, `Over 2.5`, `STRONG BUY`/`BUY`/`NEUTRAL`/`AVOID`, and a handful of universally-understood table-header abbreviations (`W-L-P`, `WR`, `P/L €`, `Kickoff`, `Man n`/`Bot n`).

### Files Modified

| File | Change |
|---|---|
| `index.html` | ~800 lines touched across the whole file — see above; new `PT_LABEL_MAP`/`ptLabel()` helper added near `escapeHtml()` |
| `docs/03_Dashboard.md`, `docs/DEVELOPMENT_GUIDELINES.md` | No change — both already stated the PT-PT rule correctly; this phase brought the implementation into compliance with an existing, previously-unenforced statement |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase; `07_Current_Status.md` also backfilled missing "Completed Areas" entries for Phases 26.20–26.24, which had never been added |
| `docs/handovers/handover-2026-07-11.md` | New handover for this phase |

### Validation

- `node --check` on the extracted `<script>` block after every batch of edits — zero syntax errors throughout.
- Full-page `innerText` extraction (Playwright) across all 11 tabs with seeded manual-bet data, iteratively grepped for English words/phrases outside the whitelist until clean — several rounds surfaced genuine misses (duplicate English labels sitting inside already-PT section cards, a whole missed `U`–`Y`/`ACTION ENGINE` static-header cluster, `League`/`Market Validation` headers, streak/equity/confidence-score labels) that were fixed and re-verified.
- All 6 existing Playwright regression suites re-run to completion and passing after every significant batch of changes, and once more at the end: `test.js` (Manual Bet lifecycle, 14 checks), `test_opinion_validation.js` (19 checks), `test_calibration_v2.js` (11 checks), `test_recommendations.js` (22 checks), `test_simulator.js` (26 checks), `test_strategylab.js` (34 checks) — 130+ checks total, zero failures, zero console/page errors. Test *assertions that checked literal English UI copy* were updated in the scratchpad copy of these suites to expect the new PT-PT strings (e.g. `'excellent'` → `'excelente'`); no test's underlying *logic/invariant* assertion changed.
- Playwright screenshots captured for all 11 tabs for a final visual spot-check.
- `git diff --stat` confirmed only `index.html` changed in the commit; `update_results.py`/`sync_server.py` untouched, so no Python validation was needed.

### Impact

The dashboard's UI language now actually matches what `03_Dashboard.md` and `DEVELOPMENT_GUIDELINES.md` already specified. Any future feature must be written in PT-PT from the start (per those documents) rather than shipped in English with translation deferred — this phase is the direct cost of that having happened silently across Phases 26.20–26.24 and earlier.

---

## Phase 26.19 — Manual Bet Lifecycle Rework: Duplicate Prevention, Rejected as a Permanent Analytical State

**Implemented:** 2026-07-10

**Goal.** Improve the Manual Bet lifecycle architecture, not just its UI: stop the Scout workspace from letting a user accidentally create a duplicate bet, make the backend independently refuse duplicates, stop treating "Reject" as deletion, and cleanly separate a bet's workflow state from its match outcome — all while reusing the existing shared settlement engine, the existing History page, and the existing `cloud_state.json` persistence model (no second CSV, no second JSON, no new endpoint, no duplicated settlement logic).

**Two pre-existing defects found and fixed as part of this work (see `05_Known_Issues.md` MANUAL-1):**
1. `renderManualScout()`'s hide-key excluded fixtures with a bet in `status ∈ {approved, rejected, settled}` — but not `pending`. A brand-new bet's Scout card stayed visible and clickable until approved/rejected, so a user could create a duplicate before ever approving the first one.
2. `apply_df_results_to_manual_bets()` unconditionally set `status = 'settled'` on any bet that got a result — including bets the user had already rejected — silently erasing the rejection and letting the bet count in bankroll/ROI (`getResolvedManualBets()` only checked `_lucro !== null`, never `status`).

**Scout duplicate prevention.** `renderManualScout()`'s `processedMatchKeys` set now includes every bet in `state.manualBets` regardless of `status` — a card hides the instant "Criar" succeeds and stays hidden through pending/approved/rejected/settled, reappearing only if the bet is removed ("Remover"). No polling or refresh is involved; it's derived from `state.manualBets` on every render, same as before.

**Frontend + backend duplicate protection (ADR-013).** `manualBetOpportunityKey()`/`findManualBetByOpportunity()` (reusing the existing `normalizeLeagueCode()`/`normalizeMarket()` normalisers) identify a bet by fixture + market. Both bet-creation paths (`addManualBetFromFixture()` for Scout, `addManualBet()` for the manual entry form) check this synchronously before pushing — since the check and the push happen in the same, non-yielding function call, a double-click cannot create two records; the second call always observes the first bet already in the array. The backend applies the identical rule independently: `sync_server.py`'s new `_dedupe_manual_bets()` (reusing `update_results._resolve_liga_display_name()` / `_normalize_market_code()` — no second normalisation implementation) runs inside `POST /save` before every write, keeping the earliest bet per `(data, liga, jogo, mercado)` identity. When it drops something, the response carries `duplicatesRemoved`, and `saveCloudState()` calls `_reloadManualBetsFromCloud()` to resync `state.manualBets` to the canonical copy.

**Rejected is now a permanent, terminal lifecycle state (ADR-012).** `mbHandleRowReject()` already only set `status: 'rejected'` (it never spliced the bet — the project's own documentation had drifted from the implementation here; corrected). What was missing was the backend guarantee: `apply_df_results_to_manual_bets()` now only advances `status` to `'settled'` when it was not already `'rejected'` — a rejected bet keeps `status: 'rejected'` forever, even after settlement populates its `resultado`/`lucro`/`placar`. `getResolvedManualBets()` (the single choke point for bankroll/ROI/analytics/versus/KPIs) additionally excludes `status === 'rejected'`, and `getFilteredRealClosedRows()`'s manual branch now builds on `getResolvedManualBets()` instead of a separately-duplicated `_lucro !== null` filter — one change point instead of two.

**Rejected bets settle through the exact same engine (no duplicated settlement logic).** `manual_bets_to_settlement_df()`/`update_dataframe()` never filtered by lifecycle status — every manual bet, rejected or not, was already being fed through settlement. The only code path that needed a change was the one line described above. A new `Placar` column (`"{home_goals}-{away_goals}"`, e.g. `"2-1"`) was added to `CSV_COLUMNS` and written at both settlement write sites (`try_update_row_via_api_football()` and the football-data.org branch in `update_dataframe()`), round-tripped through `manual_bets_to_settlement_df()`/`apply_df_results_to_manual_bets()` — additive and backward-compatible (`ensure_columns()` fills `""` for older rows without it). It is populated identically for bot picks, since the settlement engine is shared (no bot-pick-specific branch was added).

**Fixed during final verification:** `SYNC_RESULT_COLUMNS` (consumed by `sync_daily_from_history()`, the bot-pick catch-up path called from both `main()` and `run_settlement_remote()` — copies settlement results from `picks_history.csv` into `picks_hoje_simplificado.csv` when a pick settles in one file before the other) was not updated when `Placar` was added to `CSV_COLUMNS`. Without this, a bot pick's final score would settle correctly in `picks_history.csv` but never reach the corresponding row in the daily CSV via this catch-up path — and, because `update_dataframe()` skips rows whose `Resultado` is already `W`/`L`/`P` (`ALREADY_DONE`), it would never self-correct on a later run. `Placar` added to `SYNC_RESULT_COLUMNS`; verified with a dedicated round-trip test.

**Rejected History view (reuses the existing History page and table).** The "Fechadas reais filtradas" card gained a Resolvidas/Rejeitadas toggle (`_historyViewMode`, a transient, unpersisted view flag). Resolvidas is the unchanged existing table. Rejeitadas (`renderRejectedHistoryTable()` / `getRejectedHistoryRows()` / `getRejectedManualBets()`) reuses the same card, filter bar, and `<table>` element with a different `<thead>` and row-renderer: Data, Liga, Jogo, Mercado, Odd, Stake, Análise, Opinião, Placar Final, Resultado, Lucro Teórico, Notas.

**Analytics compatibility (no dashboard built, per the request's scope).** Every field needed for future rejected-bet metrics (rejected win rate, theoretical ROI, false-negative rate, by league/market/confidence/opinion) already exists on the bet object (`liga`, `mercado`, `botOpinion`, `scoreAtAnalysis`, `edgeAtAnalysis`, `resultado`, `lucro`, `placar`, permanent `status: 'rejected'`) — no schema change beyond `placar` was needed for this.

### Files Modified

| File | Change |
|---|---|
| `index.html` | Scout hide-key fix; `manualBetOpportunityKey()`/`findManualBetByOpportunity()`; duplicate guard in `addManualBetFromFixture()`/`addManualBet()`; `getResolvedManualBets()`/`getRejectedManualBets()`; `getFilteredRealClosedRows()` manual branch; History Resolvidas/Rejeitadas toggle + `renderRejectedHistoryTable()`/`getRejectedHistoryRows()`; `saveCloudState()` resync on `duplicatesRemoved` |
| `update_results.py` | `Placar` added to `CSV_COLUMNS`; written at both settlement write sites; round-tripped in `manual_bets_to_settlement_df()`; `apply_df_results_to_manual_bets()` preserves `status: 'rejected'` |
| `sync_server.py` | `_manual_bet_identity()`/`_dedupe_manual_bets()`; wired into `POST /save`; `duplicatesRemoved` added to the response |
| `docs/03_Dashboard.md`, `docs/02_Data_Flow.md`, `docs/04_Backend.md` | Manual Bet lifecycle, Scout, settlement, and History sections updated to describe the new behaviour |
| `docs/09_Architecture_Decisions.md` | ADR-012, ADR-013 added |
| `docs/05_Known_Issues.md` | MANUAL-1 added to Resolved Issues |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase |

### Validation

- Automated Chromium (Playwright) walkthrough of the live `index.html` (network calls blocked; deterministic seeded state) covering: Scout card hidden with no bet → visible again after Remove; Scout card disappears immediately after Create and stays hidden across a re-render; double-click/repeated create does not duplicate; a rejected-and-settled bet keeps `status: 'rejected'` while `resultado`/`placar` are populated; `getResolvedManualBets()` excludes it; `getRejectedManualBets()` includes it with its result; the Rejeitadas table renders game/opinion/final-score/notes; the Resolvidas table does not show the rejected bet. All checks passed.
- Isolated Python checks (no real GitHub/network calls): `_dedupe_manual_bets()` keeps the earliest bet across alias forms (`"premier"` vs `"Premier League"`, `"Over 2.5"` vs `"O2.5"`) and correctly treats a different market or date as not-a-duplicate; `manual_bets_to_settlement_df()` → simulated settlement write → `apply_df_results_to_manual_bets()` round-trip confirmed a rejected bet keeps `status: 'rejected'` with `resultado`/`placar`/`lucro` populated, and confirmed an approved bet still transitions to `status: 'settled'` exactly as before (no regression).
- `python -m py_compile update_results.py sync_server.py` passes. `node --check` on the extracted `<script>` block of `index.html` passes.
- `pytest tests/` — 29 passed, no regressions.
- Backward compatibility: an old CSV row without the `Placar` column loads correctly via `ensure_columns()`, defaulting to `""`.

### Impact

A user can no longer accidentally create a duplicate manual bet from the Scout workspace, and even if a race or a future frontend bug produced one, the backend refuses to persist it. Rejected bets are preserved forever as analytical records — settled by the same engine as any real bet, but structurally incapable of affecting bankroll, ROI, or any financial figure — laying the groundwork for future "rejected opportunity" analytics without any further schema change.

---

## Phase 26.18 — Provider API Error Visibility ("No Matches to Settle" Root Cause + Fix)

**Implemented:** 2026-07-07

**Root cause (diagnosed, no code changed to fix it).** The API-Football subscription had lapsed to the Free plan. Every `/fixtures` request for the 2025/2026 season returned HTTP 200 with an empty `response: []` and an `errors.plan` field explaining the season wasn't covered on that plan. `update_dataframe()` had no code path that inspected `errors` on a successful response — an empty `response` was always treated as "no games today". Every currently-open pick in a league routed through API-Football (all non-EU leagues, and any EU league falling back to it) came back `NO_MATCH`, and the dashboard reported "No matches to settle." with no indication a provider was actually rejecting the request. Diagnosed via a temporary, read-only audit harness that replayed real production data through the real pipeline with zero writes; renewing the subscription fixed settlement immediately with **no code change**, proving the settlement and matching logic itself was correct — the gap was response validation.

**Provider response validation.** `api_football_get()` now checks the `errors` field of every HTTP 200 response (`_extract_meaningful_errors_field()`) and raises a new `ProviderError` exception when it's non-empty, instead of returning the response as if it were a trusted (if empty) result. Genuine HTTP failures (401/403/429/5xx, both providers) are classified by `classify_provider_error()`, which prefers the response body's message content (`"plan"`/`"season"` → `PLAN_LIMIT`, `"quota"`/`"rate limit"` → `QUOTA_EXCEEDED`, `"token"`/`"auth"` → `AUTHENTICATION`, ...) and falls back to the HTTP status code otherwise.

**Normalized error record and structured logging.** Every provider failure — new or pre-existing — is normalized via `build_provider_error()` into `{provider, endpoint, request, category, message, retryable, timestamp}`, always printed as a `[API-FOOTBALL]` / `[FOOTBALL-DATA.ORG]` block (endpoint/category/message), and appended to `shared_state["provider_errors"]`. Successes are tracked via `record_provider_success()` so a provider that wasn't contacted this run can be told apart from one that failed.

**Settlement summary.** `build_settlement_result()` adds `provider_errors` to the `/run-settlement` response whenever any occurred, and — only when `updated == 0` and a provider error occurred — adds `settlement_aborted`/`abort_provider`/`abort_category`/`abort_reason`, picked via `pick_primary_provider_error()` (prefers a non-retryable error over a retryable one). When neither field is present and `updated == 0`, that is a genuine empty result, and "No matches to settle." is the correct message — this is now the *only* situation where that message appears.

**Provider health persistence.** `update_provider_health()` writes a new `cloud_state.json["providerHealth"]` field — `{provider: {status, consecutiveFailures, lastError, lastSuccessAt, lastCheckedAt}}` — so the failure state survives across Railway's stateless requests. Status flips `"ok"` → `"warning"` after `PROVIDER_HEALTH_WARNING_THRESHOLD` (2) consecutive failing runs for that provider, and resets on the next success. `cloud_state.json` is now saved whenever a settlement run contacts any provider, even if zero bets settled — previously it was only saved when a manual bet newly settled.

**Dashboard.** `runSettlement()` now distinguishes three outcomes: `✓ Settlement completed` (updated > 0), `⚠ Settlement unavailable — {provider}: {category text}` (provider error, nothing settled), and `No matches to settle.` (genuine empty result — unchanged from before). A new `#providerHealthLabel` badge next to the Cloud Status badge (Settings page) reads `state.providerHealth` — copied from `cloud_state.json` in `_doLoadCloudState()` and `_reloadManualBetsFromCloud()`, following the same cloud-field-copy pattern established for `state.movements` after the Phase 26.17 SYNC-1 fix — and shows `⚠ {provider}: {category text}` whenever any provider's status is `"warning"`.

**Backward compatibility.** All pre-existing failure reasons (`"HTTP {code}"`, `"OTHER"`, `"NO_LEAGUE_ID"`, `"NO_API_KEY"`) keep their exact strings and control flow; `update_dataframe()`'s precheck/matching/decision logic was not touched. The only behavioural change is the specific "HTTP 200 + meaningful `errors`" case, which previously returned `([], "")` (trusted empty result) and now returns `(None, "PROVIDER_ERROR")` (untrusted failed fetch) — the same code path every other provider failure already used. Validated against 7 required scenarios (valid fixtures; HTTP 200 + plan error; HTTP 200 + quota error; HTTP 401; HTTP 429; HTTP 500; genuinely empty HTTP 200) and against real production data (post-renewal, zero provider errors, settlement behaves exactly as before).

### Impact

A future provider outage — expired subscription, exhausted quota, revoked key, or a genuine API incident — will show up immediately as `⚠ Settlement unavailable` with a specific category, in the settlement summary, in structured logs, and in a persistent dashboard health badge, instead of silently accumulating unsettled picks behind an ambiguous "No matches to settle." message.

### Root Cause

- API-Football's Free plan rejects requests for the 2025/2026 season by returning HTTP 200 with an empty `response` and the real reason inside `errors.plan` — a response shape `update_dataframe()` had no code to distinguish from a genuine empty result.

---

## Phase 26.17 — Manual Bet & Bankroll Cloud Synchronization Fixed

**Implemented:** 2026-07-01

A multi-session investigation into a Live Center staleness report (LIVE-1) uncovered and fixed a chain of related synchronization defects across the frontend, backend, and Railway deployment configuration.

**Root cause of the manual bet synchronization issue (LIVE-1).** `state.manualBets` was populated from `localStorage` at startup. The 60-second `loadData()` auto-refresh interval only re-fetched the read-only picks CSVs from GitHub raw URLs — it never called `GET /load` and never refreshed `state.manualBets`. If settlement ran in another browser session, via GitHub Actions, or via a different device, the current tab kept showing stale manual-bet state (e.g. a settled bet still appearing in Live Center) until the user manually clicked "Load Cloud" or triggered settlement from that same tab.

**Boot synchronization redesign and guard.** `boot()` was restructured around a `_bootSyncComplete` flag. On startup, if no meaningful local session exists, `_doLoadCloudState()` recovers the full state from the cloud and sets the guard; otherwise `_reloadManualBetsFromCloud()` runs once to bring `state.manualBets` (and now `state.movements`) up to date without disturbing the rest of local state. The guard prevents a redundant second cloud fetch on the same boot and blocks `saveCloudState()` from firing before the first successful sync completes, avoiding a race where an unsynced local state could overwrite the cloud copy.

**Event-driven cloud synchronization.** The periodic 60-second interval now refreshes only the read-only picks CSVs, league stats, and pending-alert checks — it never touches manual bets. Manual bets (and movements) are instead refreshed on four explicit events: page boot, the "Run Settlement" button completing (`runSettlement()` → `_reloadManualBetsFromCloud()`), the "Load Cloud" button (`loadCloudState()` → `_doLoadCloudState()`), and the browser tab regaining visibility (`visibilitychange` → `_reloadManualBetsFromCloud()`). This covers settlement happening while the tab is backgrounded without adding a second polling interval.

**Bankroll movements lost during cloud recovery.** A follow-up audit found that `_doLoadCloudState()` and `_reloadManualBetsFromCloud()` copied `bankrollInicial`, `manualBets`, `localEdits`, and `sessionStartDate` from the `/load` response but never `content.movements`. `state.movements` therefore stayed at its initial empty array on any fresh session (e.g. Incognito), so the bankroll silently ignored all deposits/withdrawals after a cloud recovery while every betting-related figure (bets, wins, losses, ROI) stayed correct. Both functions now assign `state.movements = Array.isArray(content.movements) ? content.movements : []`, mirroring the other recovered fields. No new save call was introduced — the existing post-recovery `saveLocalState()` calls now persist movements to `localStorage` along with everything else.

**Railway `GITHUB_REPO` misconfiguration discovered and resolved.** While verifying the fixes against production, `GET /load` was found returning an empty `{}` body. Root cause: `sync_server.py` builds the GitHub Contents API URL from `GITHUB_OWNER`/`GITHUB_REPO` environment variables (`f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"`), and Railway's `GITHUB_REPO` variable was set to the fully-qualified `jorgepita/apostas-over-futebol` instead of just `apostas-over-futebol`, producing a doubled, 404-ing path. `update_results.py` was unaffected because it hardcodes the same two values as constants rather than reading them from the environment, which is why GitHub Actions settlement and `/run-settlement` kept working throughout. The Railway environment variable was corrected; no code change was needed or made (ADR-010 — configuration belongs in environment variables, not code).

**Dashboard KPI/alert consistency fixes.** The "Pendentes Abertas" KPI and the "Muitas apostas abertas" alert both independently re-derived an open-bet count instead of calling the same `getPendingRows()` helper the Pending page uses, causing them to include live (already-kicked-off) bets that the Pending page correctly excludes. Both now call `getPendingRows()` directly. Exposure-related widgets (`stakeOpen`, `potencialLucro`, "Risco Atual") were deliberately left on `getRiskMetrics().openCount`, since those intentionally measure total capital at risk including live bets — a different metric, not a duplicate.

**Diagnostic instrumentation removed.** All temporary investigation instrumentation — `debugger` statements, `[F1]`–`[F6]`, `[BOOT-DIAG]`, `[RECOVERY]`, `[RECOVERY-SCHEMA]` console logging in `index.html`, and `[STEP 1]`–`[STEP 5]` print statements in `update_results.py` — was removed once every fix was validated. Normal production logging (`[settlement] ...`, `console.error` in catch blocks, etc.) was left unchanged.

### Impact

`cloud_state.json` is now reliably the authoritative source for manual bets and bankroll movements alike — a fresh browser session reconstructs the same runtime state as a session with existing local data. Synchronization is fully event-driven with no periodic polling of manual-bet/bankroll state. The Pending KPI, Pending page, and volume alert can no longer numerically diverge, since they share one filtering function.

### Root Causes Fixed

- LIVE-1: 60-second interval never refreshed `state.manualBets` from the cloud.
- Bankroll movements (`state.movements`) were never copied out of the `/load` response during cloud recovery, in two separate functions.
- Railway `GITHUB_REPO` environment variable held a fully-qualified `owner/repo` value instead of just the repo name.
- Pending KPI and volume alert each re-implemented open-bet counting instead of reusing `getPendingRows()`.

---

## Documentation System Established

**Implemented:** 2026-06-29

A complete documentation system was created under `/docs` and a Claude workflow entry point added at the repository root. The system is designed so that any future Claude session can begin productive work by reading the documentation alone, without relying on previous chat history.

**Documents created:**

- `docs/README.md` — Documentation index, reading order, session lifecycle, update rules, documentation philosophy
- `docs/PROJECT_MAP.md` — Repository navigation guide: where every file and directory lives, development entry points, files that should rarely be modified
- `docs/SESSION_HANDOVER_TEMPLATE.md` — Reusable template for end-of-session handovers; copied and filled at the end of each session
- `docs/handovers/` — Directory for filled session handover documents
- `CLAUDE.md` (repository root) — Startup workflow and working principles for Claude sessions

**Documents rewritten or significantly extended:**

- `docs/DEVELOPMENT_GUIDELINES.md` — Rewritten as a practical engineering handbook: general principles, debugging workflow, frontend/backend/CSS/JS guidelines, validation requirements, implementation philosophy, "Working with Claude" section
- `docs/09_Architecture_Decisions.md` — 10 ADRs covering all major architectural decisions
- `docs/05_Known_Issues.md` — Restructured as a permanent issue tracker with severity, root cause, fix strategy, and validation checklist
- `docs/06_Roadmap.md` — Complete long-term roadmap with short/medium/long-term items and summary table
- `docs/07_Current_Status.md` — Refactored as a stable-structure status snapshot
- `docs/08_Change_Log.md` — Summary table added; implementation dates and Impact sections added to all phases

### Impact

Future Claude sessions have a complete documentation system to work from. The session handover workflow ensures that context survives across conversation boundaries without depending on chat history. The development guidelines provide enforceable engineering standards.

---

## Phase 26.16 — Manual Settlement Unified into `cloud_state.json`

**Implemented:** 2026-06-28

Manual bet settlement migrated from `manual_bets.csv` to `cloud_state.json`. `update_results.py` now loads `cloud_state.json`, converts `manualBets` to a DataFrame, settles using the same `update_dataframe()` engine as bot picks, and writes results back. `sync_server.py` was rewritten to remove dead CSV-based endpoints and retain only `/load`, `/save`, `/run-settlement`, and `/health`.

### Impact

`cloud_state.json` became the exclusive persistence layer for manual bets. Bot and manual settlement now share a single engine (`update_dataframe()`), eliminating divergence risk. The Railway API surface is minimal and well-defined.

### Breaking Changes

- `manual_bets.csv` retired as an active data store. The file remains in the repository with a header row only. No active code path reads bet data from it.
- `/state` GET and POST endpoints removed from `sync_server.py`.

---

## Phase 26.15 — Automatic Cloud-State Recovery on Boot

**Implemented:** 2026-06

`boot()` now calls `_doLoadCloudState()` automatically on startup if `hasMeaningfulLocalState()` returns false. A fresh browser session with no localStorage recovers the full state from `cloud_state.json` without a manual "Load Cloud" click.

### Impact

New browser sessions and incognito windows are now self-recovering. The cloud is always consulted before presenting an empty dashboard to the user.

---

## Phase 26.14 — Canonical League Key in Pick Deduplication

**Implemented:** 2026-06

`makePickKey()` now uses the canonical league key from the registry rather than the raw display name. Existing `localEdits` entries were migrated to match.

### Impact

Pick deduplication is stable across league name variants. `localEdits` are no longer lost when the same league is referenced by different display strings (e.g. `"LaLiga"` vs `"La Liga"`).

---

## Phase 26.12 — Calendar-Year League Season Model Fix

**Implemented:** 2026-06

`api_football_season_from_date()` now consults `AF_SEASON_MODELS` from the league registry to determine the correct season integer per league. MLS and Nordic leagues were incorrectly mapped to season 2025 for June 2026 fixtures.

### Impact

Season resolution is now driven by `src/league_registry.py`. Adding a new league with a non-European season model requires only a `season_model` field in the registry entry.

---

## Phase 26.11 — Railway Backend Migration

**Implemented:** 2026-06

Dashboard migrated from GitHub Actions-based settlement to an always-on Railway server. `sync_server.py` introduced as the Flask application. "Run Settlement" button added to the Live Center. Settlement league mapping unified into the league registry.

### Impact

Settlement became on-demand and browser-triggered, no longer requiring a GitHub Actions run or direct API call. Railway became the single CORS bridge between browser and GitHub. The league registry became the authoritative source for all settlement routing.

### Breaking Changes

- Settlement previously required a GitHub Actions dispatch or manual script execution. On-demand settlement via the dashboard replaced this for the common case.

---

## Phase 26.7–26.9 — KickoffUTC End-to-End

**Implemented:** 2026-05

**Note (2026-07-12, Phase 26.32):** the claim below that `KickoffUTC` was propagated to "manual bet objects" was inaccurate — only a transient, render-time-only placeholder (`kickoffUTC: ''`, used solely so the Kickoff column could format safely) existed; the field was never actually persisted on a manual bet, and was never read by the settlement engine before Phase 26.32. See `05_Known_Issues.md` SETTLEMENT-2 for the resulting bug and its fix.

`KickoffUTC` field propagated through fixtures, picks CSVs, Scout bet creation, manual bet objects, and Live/Pending display. Pending and Live filter logic made kickoff-aware. Odd Real / Stake Real field persistence on page refresh fixed.

### Impact

Pending and Live Centre state transitions are now determined by actual kickoff time, not just bet date. Bets with future dates stay in Pending until kickoff passes; bets cross into Live only when they are genuinely in play.

---

## Phase 26.6 — Pending Queue Overhaul

**Implemented:** 2026-05

Pending section redesigned as an execution workspace with approve and reject actions. Approve button event binding fixed. Daily Picks page cleaned up to show only unplaced picks.

### Impact

The approve/reject action path became reliable. The distinction between "created", "approved/pending kickoff", and "approved/live" became consistent with the data model.

---

## Phase 20–21 — Live Center and Live Settlement Engine

**Implemented:** 2026-04

Live Center V1 introduced with merged bot and manual bet display. Pending/Live state separation formalised. Live settlement engine added with audit trail. Settlement hardening against partial results and malformed rows.

### Impact

The dashboard gained a unified view of all in-play bets. The settlement engine became robust enough for production use on real money.

---

## Phase 19 — Pending Queue

**Implemented:** 2026-03

Pending queue introduced as the first end-to-end manual bet workflow: create → approve → live. Manual bets tracked from creation through to a live state.

### Impact

Manual bets became a first-class feature with a defined lifecycle. The three-state model (pending, approved, settled) was established here and has remained unchanged.

---

## Phase 17 — Manual Bets Scout Workspace

**Implemented:** 2026-03

Scout workspace added to the Manual Bets tab with real-time Poisson analysis run in the browser. Manual bet workflow formalised: analyse → approve → reject. Manual bets integrated into financial calculations (bankroll, ROI, Bot vs Manual comparison).

### Impact

Manual bets became analytically consistent with bot picks. The Scout workspace established the pattern of running the Poisson model client-side using `state.fixtures`.

---

## Phase 14–16 — History Intelligence and Equity Curve

**Implemented:** 2026-02

History section redesigned from a simple table into an investigation tool. Equity curve, drawdown analysis, and financial intelligence panels added. Filtering by date range, league, and result added.

### Impact

The History tab became the primary performance review surface. Equity curve data is consumed by the Bankroll page for evolution charts.

---

## Phase 8–13 — Analytics Intelligence Engine

**Implemented:** 2026-01

Analytics section built incrementally across six phases: edge validation, strategy validation, model calibration display, action engine, learning centre, bot vs manual performance intelligence, score-band intelligence, and opinion intelligence.

### Impact

The dashboard shifted from a pick-viewing tool to a model-evaluation tool. Per-league ROI tracking, win-rate calibration, and the Bot vs Manual comparison tab were all established in this phase and have not required structural changes since.
