# Known Issues

Unresolved issues only. Move entries to `08_Change_Log.md` when fixed; a brief historical record is kept in the Resolved Issues section below.

Issue ID format: `LIVE-#`, `SETTLEMENT-#`, `SYNC-#`, `API-#`, `DASHBOARD-#`, `ANALYTICS-#`, `TELEGRAM-#`, `PERFORMANCE-#`, `GENERATION-#`

---

## Open Issues

None currently open.

---

## Resolved Issues

### SYNC-3 — `_reloadManualBetsFromCloud()` Had No Season-Recency Guard, So a Stale Cloud Restore Could Silently Overwrite Current-Season Manual Bets and Get Auto-Saved Back to GitHub

**Status:** Resolved — 2026-08-23 (Phase 29.6, code-only; closes the architectural gap the Phase 29.5/29.5B incident exposed).

**Incident that exposed this (Phase 29.5/29.5B):** an explicit manual "Restore" action in the dashboard's Backups tab reverted `cloud_state.json` on GitHub to a pre-season-close snapshot (backup `2026-08-02T19-01-03-057-manual-7e9dc5e1`, itself from before the 2026-08-03 season close). `boot()`'s Phase 28.3A recency guard (`isCloudSeasonNewer()`, feeding `_doLoadCloudState()`) correctly protected `sessionStartDate`/`bankrollInicial`/`localEdits` from that stale content — those fields were never at risk. But `_reloadManualBetsFromCloud()` (Phase 26.17/LIVE-1, called unconditionally on every boot and every tab `visibilitychange`) had no equivalent protection: it unconditionally executed `state.manualBets = content.manualBets`. Whichever browser's boot/visibilitychange fired against the reverted cloud content had its correct, in-memory current-season manual bets (176 real bets, 2026-08-07→08-22, €95 stake / −€9.38 profit across 95 settled bets) silently replaced with the old (pre-season-close) manual-bet array, persisted to `localStorage` via the same function's own `saveLocalState()` call, and then pushed permanently back to GitHub by an ordinary subsequent auto-save (`markDirty()` → `saveCloudState()`) — with no season check anywhere in that chain. Recovered via a git-history-based data restoration in Phase 29.5B (see `08_Change_Log.md`); this entry is the code-side fix preventing recurrence.

**Root cause:** two structurally distinct cloud-content consumers existed side by side — `_doLoadCloudState()` (season-guarded since Phase 28.3A) and `_reloadManualBetsFromCloud()` (never guarded, an older code path predating Phase 28.3A) — and only one of them was ever hardened. `content.manualBets` itself carries no season marker of its own; the only reliable signal is the sibling `content.sessionStartDate` field already present in the same `/load` response, which `_reloadManualBetsFromCloud()` fetched but never inspected.

**Fix:** extracted the exact comparison `_doLoadCloudState()`'s `fromUser` guard already used (Phase 28.3A) into one shared helper, `isCloudSessionStale(cloudSessionStartDate)` (`index.html`) — stale only when a meaningful local season already exists and the cloud's own `sessionStartDate` strictly predates it; permissive (not stale) for a brand-new browser or a cloud payload with no `sessionStartDate` at all, exactly matching prior behaviour in both cases. `_doLoadCloudState()`'s guard now calls this helper instead of repeating the comparison inline (no behaviour change there — same logic, no longer duplicated). `_reloadManualBetsFromCloud()` now calls the same helper before touching `state.manualBets`/`state.movements`/`localStorage`; a stale snapshot is rejected outright (nothing mutated) and the sync is still marked complete via `_completeBootSync()`, so a correctly-rejected stale sync doesn't leave `saveCloudState()`/Live Center stuck waiting on `_bootSyncComplete` forever. Both cloud-content consumers now make the identical season-safety decision from one shared primitive.

**New invariant:** a cloud snapshot belonging to a season strictly older than the browser's own current season can never overwrite `state.manualBets` (or, via the pre-existing Phase 28.3A path, `sessionStartDate`/`bankrollInicial`/`localEdits`) — regardless of which of the two cloud-loading code paths encounters it, or whether it arrives at boot or via `visibilitychange`.

**Verification:** real-browser (Playwright/Chromium) regression against the unmodified `index.html` (local static server, `/load`/`/save`/CSV network fully mocked) — 8 scenarios/assertions: current-season cloud accepted at boot; previous-season cloud rejected at boot (local manual bets preserved); the same rejection via the exact function `visibilitychange` invokes; the critical regression — a rejected stale snapshot is never subsequently included in a `saveCloudState()` POST body (reproduces the Phase 29.5 corruption-then-persist chain and proves it can no longer happen); a genuinely newer/same-season cloud update still syncs; the `visibilitychange` DOM listener is confirmed (via a spy) to actually invoke `_reloadManualBetsFromCloud()`; `isCloudSessionStale()`'s full truth table (older/same/newer/missing cloud date); manual-bet creation confirmed unaffected. All 8 confirmed to **fail** against the pre-fix code (reproducing the real defect) and **pass** against the fix — a negative control proving the tests exercise the actual vulnerability, not a tautology. Scratchpad-only per this project's established convention (Playwright is not a repository dependency). Full Python suite 430/430 and QuantEngine golden vectors 285/285, both unchanged, as expected for a JS-only change touching no calculation code. Zero production data files touched — `cloud_state.json`/`picks_history.csv`/`league_stats.csv`/`picks_*.csv` do not appear in this phase's diff.

---

### DASHBOARD-8 — History, Bank, Dashboard Home, and Bot vs Manual Kept Showing Previous-Season Data After a Correctly-Executed Season Close

**Status:** Resolved — 2026-08-04 (Phase 28.5, implementing the architectural fix identified by the Phase 28.4 read-only audit).

**Was:** Immediately after a successful Season Close (with Phase 28.3A's boot-sync fix already confirmed working and `cloud_state.json` correctly holding the new season), the dashboard still displayed the previous season's data: History listed every previously-resolved bet ever placed; Bank showed cumulative all-time ROI/P&L/win-loss and a bankroll-evolution chart that replayed the entire betting history on top of the fresh bankroll; the Dashboard Home headline KPIs and the Bot vs Manual comparison (and, by inheritance, the entire Opinion Validation/Calibration/Recommendation Engine/Simulator suite) were equally all-time.

**Root cause (Phase 28.4 audit, full trace in `08_Change_Log.md` Phase 28.4):** not a Season Close failure — `executeSeasonClose()` correctly resets `bankrollInicial`/`manualBets`/`movements`/`localEdits` and never touches `picks_history.csv`, which is a permanent, cross-season record by design. The gap was that the dashboard's own season-boundary primitive, `isOnOrAfterSession()`, already existed and was already correctly wired into `getMetrics()`'s `sessao` bundle and Strategy Lab's default "Época Atual" filter — but was never connected to `getFilteredRealClosedRows()` (History/Dashboard Home/Bank's evolution chart), `getBankrollState()` (Bank's documented single source of truth), or `renderVersus()` (Bot vs Manual and everything downstream of `window._opnSimCache`). This is exactly `docs/06_Roadmap.md`'s DX-4, "Season selector in History tab" — a documented, previously-deferred gap, not a regression.

**Fix:** Reused the existing infrastructure exclusively — no new season model, no new global state, no duplicated filter logic:
- Two new shared, memoized helpers, `getSessionRealResolvedBotHistory()`/`getSessionResolvedManualBets()` (`index.html`, immediately after `getResolvedManualBets()`), each a one-line `.filter(isOnOrAfterSession(...))` wrapper around the existing all-time getters. `getMetrics()`'s `sessao` bundle now calls these instead of its own inline filter (removing that duplication); `getBankrollState()`, `renderBankrollPerformanceBreakdown()`, and `renderVersus()` (Bot vs Manual, plus every `getResolvedManualBets()` re-derivation inside it — 7 call sites collapsed into one shared `manualRows` variable) now consume the same two helpers instead of each independently re-deriving an all-time pool.
- `getFilteredRealClosedRows(filters, sessionOnly)` gained one optional, default-`false` parameter. `getHistoryFilteredRows()` (History), `renderSummaryHeadlineStats()`/`renderBankrollChart()` (Dashboard Home), and `renderBankrollEvolution()` (Bank) now pass `true`. Every other caller — `buildSeasonArchiveObject()` (the archive snapshot), Analytics's league enrichment, and the Close Season wizard's own review step — was left unchanged, deliberately, since none of those may be touched.
- `exportRealCsv()` now reuses `getHistoryFilteredRows()` instead of an independent, slightly different direct call — the CSV export always matches what's on screen.

**Explicitly not changed:** Season Close flow (`executeSeasonClose()`, `csmExecute()`, `csmGoStep4()`), archive generation (`buildSeasonArchiveObject()`), the backup subsystem, R2, Railway, cloud synchronization, and Strategy Lab's own pre-existing season filter. Analytics (`league_stats.csv`) is unchanged and remains all-time by architecture — it is computed entirely server-side (`src/league_stats.py`) with no `sessionStartDate` concept in the Python backend at all; fixing that would require a backend redesign, explicitly out of scope for this phase.

**Verification:** real-browser (Playwright/Chromium) test against the unmodified `index.html`, 27 assertions across 3 scenarios — immediately-after-close (History/Bank/Dashboard Home/Bot vs Manual all correctly empty; old-season data confirmed still present and un-deleted in the underlying store), a new-season bet correctly appearing while the old one stays excluded from every season-scoped view but still visible in the untouched all-time (`.geral`)/Analytics path, and a full regression pass (Strategy Lab, Pending, Live Center, Manual Bets, Daily Picks, Analytics all confirmed unaffected). Full Python suite 430/430 and QuantEngine golden vectors 285/285, both unchanged, as expected for a JS-only, dashboard-only change.

---

### DASHBOARD-7 — Returning Browsers Never Re-Checked the Cloud, So a Season Close Executed Elsewhere Left Them Showing a Stale Season Indefinitely

**Status:** Resolved — 2026-08-04 (Phase 28.3A, following the Phase 28.3 read-only audit). Full technical detail in `08_Change_Log.md` — Phase 28.3A.

**Was:** Immediately after a successful End-of-Season execution, a dashboard could still show the old season's bankroll, `sessionStartDate`, and bot-pick approvals (`localEdits`) — while `manualBets`/`movements` correctly showed the new (empty) season, producing a visibly inconsistent, part-old/part-new state.

**Root cause (confirmed by the Phase 28.3 audit, including a live read of the production `cloud_state.json` via Railway `/load`):** `cloud_state.json` on GitHub was never wrong — it already held the correct new season the moment `executeSeasonClose()`'s Step 12 cloud push completed. The defect was entirely client-side: `boot()`'s auto-recovery gate, `if (!hasMeaningfulLocalState())`, is a one-time "is this a brand-new/anonymous browser" check — `hasMeaningfulLocalState()` returns `true` for any browser that has ever had a bankroll configured, forever, so the full cloud-recovery path (`_doLoadCloudState()`, which restores `bankrollInicial`/`sessionStartDate`/`localEdits`/`manualBets`/`movements`) was skipped unconditionally on every subsequent boot for a returning browser, regardless of how much newer the cloud's season had become. Such a browser fell instead to `_reloadManualBetsFromCloud()`, which only patches `manualBets`/`movements`/`providerHealth` from the cloud — leaving `bankrollInicial`/`sessionStartDate`/`localEdits` stuck on the old season. The browser/tab that actually executed Season Close was never affected (`executeSeasonClose()` writes the new season directly into its own `localStorage` before the cloud push, and `csmExecute()` re-renders the already-updated in-memory state immediately) — this only affected *other* browsers, tabs, or devices with their own pre-existing local season data.

**Fix:** A new `isCloudSeasonNewer()` helper (`index.html`) — a single read-only `GET /load` that compares `content.sessionStartDate` to the local `state.sessionStartDate` and returns a boolean, mutating nothing. `boot()`'s auto-recovery gate now also calls the *existing* `_doLoadCloudState({ fromUser: false })` — no new or duplicated recovery logic — whenever `hasMeaningfulLocalState()` is true but `isCloudSeasonNewer()` confirms the cloud season is strictly newer. When the cloud season is the same age or older, behaviour is byte-for-byte unchanged from before this phase: the local snapshot is kept, protecting both a genuinely newer local season and any local edit not yet synced to the cloud under the same season (the exact case `hasMeaningfulLocalState()` was originally designed to protect — see `SYNC-1`/`SYNC-2` and `02_Data_Flow.md`'s Cloud Recovery section). `executeSeasonClose()`, `saveCloudState()`, and the manual "Load Cloud" button's own recency guard (`fromUser: true`) were not modified.

**Verification:** confirmed with a real-browser (Playwright/Chromium) test against the unmodified `index.html`, network fully mocked/deterministic — 6 scenarios, 22 assertions, all passing: (1) the browser that executed Season Close, reloaded (local == cloud, both new) — unchanged; (2) a second browser that never ran the close, with a real old season locally and a newer cloud season — now correctly adopts the new season in full; (3) a fresh/anonymous browser with no localStorage — unaffected, pre-existing path; (4) a browser with very old, minimal local data (bankroll-only signal) — correctly recovers; (5) a browser with a genuinely unsynchronised local edit under the *same* season as the cloud — correctly left untouched (`isCloudSeasonNewer()` returns `false` when seasons match); (6) a browser whose local season is *newer* than the cloud's — correctly left untouched (protects local work, mirrors the manual Load Cloud button's existing guard). Full Python suite (430/430) and QuantEngine golden vectors (285/285) re-run unchanged, as expected for a JS-only, boot-sequence-only change.

---

### GENERATION-1 — Cross-Run Correlated-Market Duplication: A Fixture Could Receive Both O2.5 and BTTS Bot Picks Across Separate Generation Runs

**Status:** Resolved — 2026-07-27 (Phase 26.45). Full technical detail in `08_Change_Log.md` — Phase 26.45. See ADR-018.

**Was:** `dedupe_correlated_picks()` correctly selected one market per fixture (highest Edge) *within a single generation run*, but had no visibility into a fixture already recommended in an *earlier* run. Because the same fixture is re-evaluated fresh every run (main 17:00 UTC, top-up 23:00 UTC, across a rolling multi-day window), a later run whose Edge ranking flipped could persist the competing market as a second, correlated bot recommendation for a fixture that already had one. Confirmed in production twice: West Ham vs Leeds (O2.5 persisted 2026-05-20, BTTS added ~24h later; both subsequently carried `apostada:true` with identical real stake/odd in `cloud_state.json["localEdits"]`) and Gnistan vs Mariehamn (O2.5 persisted 2026-07-07, BTTS added ~4 days later).

**Root cause:** Every persisted identity downstream of `dedupe_correlated_picks()` — `picks_history.csv`'s merge key, `localEdits` keys, settlement matching, `sent_state.json` — is market-specific (`Date+League+Game+Market`). No fixture-only identity existed anywhere in the generation pipeline to answer "has this fixture already received a bot recommendation, under any market?", so nothing prevented a later run from treating a re-evaluated fixture as brand new.

**Fix:** A read-only investigation first established that Policy A (the first persisted market is permanent) fit the existing architecture with far less risk and complexity than Policy B (pre-approval re-evaluation), given the current settled-history sample size. `apply_fixture_market_lock()` (`src/pipeline.py`) now runs on the concatenated O2.5+BTTS candidate set before `dedupe_correlated_picks()`, rejecting any candidate whose fixture already has a *different* market recorded in `picks_history.csv` — regardless of approval, settlement, or void state. Same-market regeneration is unaffected. One shared call site in `main.py` covers both the main and top-up generation jobs. See ADR-018 for full reasoning, including why the lock runs *before* (not after) the same-run cross-market selection.

**Not fixed by this change (explicitly out of scope):** the two historical production duplicates (West Ham vs Leeds, Gnistan vs Mariehamn) are preventative-only — neither existing history row was migrated, deleted, or altered. Policy B (pre-approval re-evaluation) was evaluated and explicitly deferred, not implemented.

---

### ANALYTICS-1 — `league_stats.csv` Regenerated Locally on Every Settlement/Generation Run but Never Uploaded, Freezing "Desempenho por Liga" at a 2026-05-24 Snapshot for ~2 Months

**Status:** Resolved — 2026-07-21 (Phase 26.44). Full technical detail in `08_Change_Log.md` — Phase 26.44. See `04_Backend.md` §11 "Derived-file persistence invariant".

**Was:** Dashboard → Análises → "A — Desempenho por Liga" (and its 4 top insight cards, which read the identical dataset) showed only ~15 stale league/market rows, all carrying `LastUpdate: 2026-05-24T11:43:08Z`, regardless of how much real settlement/generation activity had happened since — including the entire MLS/MLS Next Pro routing fix (Phase 26.42) and every bet settled under it. A read-only investigation (prompted by MLS's absence from the table) confirmed MLS alone had 22 real, resolved-or-pending picks in `picks_history.csv` that were fully Analytics-eligible and simply never reached the derived file.

**Root cause:** `src/league_stats.py::update_league_stats()` correctly recomputes `league_stats.csv` from `picks_history.csv` on both production paths that call it — `update_results.py::main()` (GitHub Actions settlement, 07:00/22:30 UTC) and `main.py` (via `src/pipeline.py::persist_history()`, called by GitHub Actions generation at 17:00 UTC and top-up at 23:00 UTC) — but the regenerated file was **never included in either path's GitHub upload list** (`update_results.py::main()`'s `upload_csv_to_github()` calls only covered `HISTORY_FILE`/`DAILY_FILE`; `main.py`'s `upload_outputs()` list only covered the picks output files). Since GitHub Actions runners are ephemeral, the correctly-computed local file was discarded at the end of every single run, with zero durable effect — while `picks_history.csv` itself (uploaded correctly) kept advancing normally. This affected every league equally; nothing about it was MLS-specific.

A narrow, related audit found `sent_state.json` and `team_alias_cache.json` share the identical write-locally-never-upload pattern (both files' last commits predate or coincide with `league_stats.csv`'s), suggesting a repeated persistence mistake rather than an isolated one. **Not fixed in this phase** — deliberately out of scope; flagged for a future, separately-scoped investigation, since neither file is directly dashboard-visible the way `league_stats.csv` is, and the practical impact needs its own assessment.

**Fix:** `update_results.py::main()` now calls a new `_persist_league_stats()` helper — `update_league_stats()` followed immediately by `upload_csv_to_github(LEAGUE_STATS_FILE, "league_stats.csv")`, in one `try/except` that preserves this derived file's pre-existing failure tolerance (a computation or upload problem is logged and skipped, never allowed to abort the history/daily settlement that already succeeded above it). `main.py`'s `upload_outputs()` call now additionally includes `HISTORY_PATH.parent / 'league_stats.csv'`, using the exact same path convention `update_league_stats()` itself defaults to. `update_results.py::run_settlement_remote()` (the Railway on-demand "Executar Resolução" path) does not call `update_league_stats()` at all and is unaffected — unchanged from before this fix. No Analytics calculation (`groupby`, `ROI%`, `WinRate%`, `Tier`, P handling, minimum-sample/"Unproven" behaviour) was touched.

**Verification:** running the real `update_league_stats()` against current production `picks_history.csv` (scratch output only, not committed) produced 27 rows including `MLS/O2.5` (21 picks, 11W/7L/3 pending, ROI −18.05%, Tier Weak) and `MLS/BTTS` (1 pick, 100% win rate) — confirming MLS is fully Analytics-eligible and was purely blocked by the upload gap. MLS Next Pro correctly produced no row (zero currently-labelled records in production; a separate, deferred data-identity issue — not this bug) — this is expected, data-driven behaviour, not forced.

---

### SETTLEMENT-4 — `HISTORY_COLUMNS` Schema Drift Silently Erased `Placar` From Every Settled Row on Each Daily Generation Cycle (Already Active in Production)

**Status:** Resolved — 2026-07-21 (Phase 26.43's pre-commit safety audit, discovered while verifying the phase's own new `SettlementReason`/`MissingAttempts` columns). Full technical detail in `08_Change_Log.md` — Phase 26.43. See ADR-017's "Correction" section.

**Was:** Every settled row's `Placar` (final score, added Phase 26.19) was silently stripped from `picks_history.csv` on each daily generation run. Confirmed already active against real production data at the time this was discovered: 90 of 93 settled rows in the live file had an empty `Placar`, only the 3 most recent (not yet through a generation cycle) still had it.

**Root cause:** `src/history.py`'s `HISTORY_COLUMNS` — a separate, hardcoded 14-field schema list consumed by `load_history()`/`ensure_simple_columns()`/`merge_into_history()` (the daily-generation persistence path, `main.py` → `persist_history()` — distinct from `update_results.py`'s settlement engine and its own `CSV_COLUMNS`, which *did* get `Placar` added correctly in Phase 26.19) — was never updated to include it. `ensure_simple_columns()`'s reindex (`df[HISTORY_COLUMNS]`) is a hard "keep only these columns" operation, not a union — so `load_history()` dropped `Placar` from every row the moment it read `picks_history.csv`, and `merge_into_history()` wrote the stripped result back. Because `Resultado`/`Lucro€`/`LucroReal€` *are* in `HISTORY_COLUMNS`, a settled row still looked `already_done` to `update_dataframe()` on every subsequent settlement run — so the field, once stripped, was never re-populated. This was purely a display/analytics-field loss; no financial value (`Resultado`, `Lucro€`, `LucroReal€`) was ever affected.

**Discovered via:** Phase 26.43 (the postponed/cancelled/missing-fixture void policy, see ADR-017) added two new settlement-written fields, `SettlementReason` and `MissingAttempts`, to `update_results.py`'s `CSV_COLUMNS` — a pre-commit safety audit tracing their persistence lifecycle found they would be exposed to the identical erasure path, which led to finding `Placar` already silently affected in production.

**Fix:** `HISTORY_COLUMNS` extended to include `Placar`, `SettlementReason`, and `MissingAttempts`, restoring it as an exact mirror of `CSV_COLUMNS`. `src/pipeline.py`'s `save_all_outputs()` — a second, separate consumer that reindexes to `HISTORY_COLUMNS` directly without `ensure_simple_columns()`'s add-if-missing safety net — gained explicit blank-column assignments for the three fields (it would otherwise raise `KeyError` on every generation run once the schema grew). A new regression suite, `tests/test_history_schema.py`, asserts `HISTORY_COLUMNS` stays a set-equal mirror of `CSV_COLUMNS` going forward, specifically to catch the next drift immediately instead of after 11+ days of silent production loss.

**This fix is preventative only.** It does not and must not attempt to reconstruct the already-lost historical `Placar` values for the ~90 affected rows — that would require querying providers for old fixture data and was explicitly out of scope for this correction. Historical `Placar` reconstruction, if ever desired, must be a separate, explicitly-approved data-repair task.

---

### SETTLEMENT-3 — MLS Settlement Queried MLS Next Pro (API-Football ID Collision), Leaving Every Senior MLS Bet Unresolved

**Status:** Resolved — 2026-07-20 (Phase 26.42). Full technical detail in `08_Change_Log.md` — Phase 26.42. See ADR-004 update.

**Was:** Approved bot picks and manual bets on current senior MLS fixtures (e.g. Chicago Fire vs Vancouver Whitecaps, St. Louis City vs Sporting Kansas City, Nashville SC vs Atlanta United FC, Los Angeles Galaxy vs Los Angeles FC) never settled, even long after kickoff and `RESULT_READY_DELAY`. Meanwhile older `"MLS"`-labelled bets from earlier in the season had settled correctly, making the failure look intermittent rather than systemic.

**Root cause:** `src/league_registry.py`'s `"mls"` entry had `af_id=909` — API-Football's **MLS Next Pro** (reserve league) competition, not senior MLS (`253`) — hardcoded in Phase 26.12 to fix 13 bets that, at the time, genuinely were reserve-team fixtures. `config.json`'s `api_football.league_ids.mls` had held the correct `253` the entire time, undetected, because generation (`fetch_oddsapi_fixtures.py`) reads `config.json` directly and never imports the registry. The reason Phase 26.12's 13 stuck bets really were reserve-team fixtures: `fetch_fixtures_for_league_date()`'s zero-fixture retry (`search_league_id_by_api()`) fuzzy-matched the configured league's short name (`"MLS"`) against API-Football's `/leagues` listing — since `"major league soccer"` does not contain the substring `"mls"` but `"MLS Next Pro"` does, any date where senior MLS legitimately had no fixture silently substituted MLS Next Pro fixtures under the `"MLS"` label instead. Both defects together were self-consistent (generation and settlement agreed, on the wrong competition) for as long as senior MLS had sparse fixtures on the checked dates; once senior MLS resumed a normal calendar, generation started finding real senior-MLS fixtures directly (no substitution needed) while settlement kept querying MLS Next Pro — the two paths diverged and every senior MLS bet since became permanently unsettleable.

**Fix:** `"mls"` restored to `af_id=253` (`af_name="Major League Soccer"`). A new, distinct `"mls_next_pro"` registry entry (`af_id=909`) gives the reserve competition its own stable identity. Generating MLS Next Pro picks was always an intentional part of this project's coverage — the defect was never that they were generated, only that they were obtained via a fallback from MLS and stored under MLS's identity — so `mls_next_pro` was **also** registered in `config.json`'s `leagues` / `api_football.league_ids` sections (plus `main.py`'s non-EU top-up league set and a real `data_raw/mls_next_pro.csv` history file), making it a fully independent, actively-generating league exactly like MLS, never dependent on or substituting for it. `fetch_fixtures_for_league_date()` no longer retries a zero-fixture response with a different competition at all — a configured canonical ID is now authoritative everywhere, for both leagues.

**Historical data audit (Part 4 of the investigation, no destructive migration):** Every `"MLS"`-labelled row across `picks_history.csv` and `cloud_state.json["manualBets"]` was inspected. 14 bot-pick rows and 14 manual bets are genuine, already-**settled** MLS Next Pro fixtures (reserve/"II" teams, `Atlanta United II`, `Chattanooga`, `Real Monarchs`, etc.) — left untouched, per the investigation's explicit instruction not to migrate already-resolved historical data without a proven correctness reason. Exactly one row was both unresolved and deterministically identifiable as MLS Next Pro by team identity: `picks_history.csv`, `"Huntsville City vs Crown Legacy"` (2026-06-21) — both clubs are exclusively MLS Next Pro sides. Its `Liga` was changed from `"MLS"` to `"MLS Next Pro"` so it remains resolvable going forward; the matching `cloud_state.json["localEdits"]` key (`"2026-06-21|mls|..."` → `"2026-06-21|mls_next_pro|..."`) was re-keyed identically so its existing manual-result bridge (`resultadoManual: "P"`, ADR-015) is not orphaned. No `Resultado`/`Lucro€`/`resultado` field was touched on any row. 6 unresolved manual bets and 3 bot-pick rows already correctly carried senior-MLS identity (`leagueId: 253`, real club names) and needed no change — they simply now settle correctly under the corrected routing.

**Verification (read-only, live API-Football query under the corrected routing, 2026-07-20):** St. Louis City vs Sporting Kansas City — `FT`, `3-2` (Over 2.5 → W). Nashville SC vs Atlanta United FC — `FT`, `1-0` (Over 2.5 → L). Los Angeles Galaxy vs Los Angeles FC — `FT`, `0-3` (Over 2.5 → W). Chicago Fire vs Vancouver Whitecaps was not found in API-Football's schedule within a ±10-day window of its stored kickoff, consistent with a genuine postponement whose two clubs have since resumed against different opponents — the engine correctly does not match or settle it (no `FT`/`AET`/`PEN` status to observe), it simply remains open. See `08_Change_Log.md` Phase 26.42 for the full per-fixture trace.

---

### DASHBOARD-6 — Manual Bets' Persisted `kickoffUTC` Was Never Read by Pending/Live Center, Showing "Kickoff: —" Once a Fixture Aged Out of the Live Feed

**Status:** Resolved — 2026-07-20 (Phase 26.42). Full technical detail in `08_Change_Log.md` — Phase 26.42.

**Was:** Manual bets in the Live Center and Pending page showed `Kickoff: —` even though Phase 26.32 already persists `kickoffUTC` on fixture-backed manual bets at creation time. Bot picks, which read their own CSV `KickoffUTC` column directly, were unaffected.

**Root cause:** Two independent gaps. First, `getManualRowsMerged()` — the shared function both `getPendingRows()` and `getLiveRows()` build their manual rows from — never copied `kickoffUTC` from the raw `state.manualBets` entry onto its merged row object at all, so the field was unconditionally lost before any consumer could read it. Second, even had it been propagated, `getPendingRows()`/`getLiveRows()`/`getPendingCount()` derived a manual bet's kickoff exclusively via `findFixtureKickoff()` — a live lookup against the current rolling `fixtures_today.csv` window — rather than ever reading the bet's own persisted field; once a fixture's date passed and it aged out of that forward-looking window, the lookup naturally returned empty. Backend settlement was unaffected — `manual_bets_to_settlement_df()` already read `bet.get('kickoffUTC')` directly from the persisted field, so `RESULT_READY_DELAY` gating was always correct; this was a display/classification-only gap.

**Fix:** `getManualRowsMerged()` now includes `kickoffUTC` on every local manual row. A new `resolveManualKickoff(b)` helper (`b.kickoffUTC || findFixtureKickoff(...)`) is used at all four manual-row kickoff call sites (`getPendingRows()`, `getLiveRows()`, `getPendingCount()` — kept in sync with `getPendingRows()` per its Phase 26.38 invariant), preferring the persisted value and falling back to the live lookup only for bets that genuinely predate Phase 26.32 and have no persisted kickoff of their own. Bot-pick kickoff handling (`r['KickoffUTC']`) is untouched. The Manual Bets tab's own row table (a separate, out-of-scope render path) still calls `findFixtureKickoff()` directly and was not touched — it exhibits the same latent live-lookup weakness but was outside this fix's stated scope.

---

### DASHBOARD-5 — StakeReal Auto-Fill Guard Treated a Stored "0" as an Already-Entered Value, Permanently Suppressing the Default

**Status:** Resolved — 2026-07-15 (Phase 26.35). Full technical detail in `08_Change_Log.md` — Phase 26.35.

**Was:** The Phase 26.33 auto-fill guard (`.js-bot-approve` handler in `bindBotTableControls()`) used string truthiness — `if (!cleanString(stakeReal))` — to decide whether a pick already had a real stake. `"0"` is a non-empty string, so the guard treated a stored `stakeReal: "0"` identically to a deliberately-typed value and never replaced it with the recommended stake. A real, approved bot pick ("Mjallby AIF vs Vasteras SK FK") was found with exactly this state in `cloud_state.json` — `StakeReal` showed `€0.00` on the Pending page and did not contribute to Open Exposure, while a comparable pick approved the same way worked correctly.

**Root cause:** `computeRecommendedStake()` cannot itself produce zero — its output is hard-floored by `clamp(x, 1, maxCap)` with `maxCap ≥ 2` — so a stored `"0"` could only have entered `stakeReal` via the free-form `.js-stake-real` Pending-page input (no floor validation). `pendingCancel()` ("Cancelar") deliberately preserves `stakeReal` across a cancel, so a stray `"0"` could also survive an approve→cancel→re-approve cycle and keep suppressing the default indefinitely. `getRiskMetrics()`'s exposure sum does not filter out `0` (only `null`), so the pick was correctly counted as open but contributed nothing — exposure was faithfully summing a bad stored value, not miscalculating.

**Fix:** The guard now parses the existing value with the project's existing `num()` helper and auto-fills whenever it is `null` or `<= 0` — covering empty, undefined, NaN, invalid strings, zero, and negative values uniformly, while a genuine positive value (user-typed or from a prior auto-fill) is never touched. No change to `computeRecommendedStake()`, exposure calculation, or bankroll calculation. No data migration: a pick already sitting at a stale `stakeReal: "0"` self-corrects the next time it goes through Cancelar → Aprovar, not automatically.

---

### DASHBOARD-4 — Manual Result Override (`resultadoManual`) Could Permanently Mask a Later, Real Automated Settlement Result

**Status:** Resolved — 2026-07-15 (Phase 26.34). Full technical detail in `08_Change_Log.md` — Phase 26.34. See ADR-015.

**Was:** `getRowWithLocalEdits()` computed `resultadoFinal = ['W','L','P'].includes(resultadoManual) ? resultadoManual : resultadoBase` — a valid `resultadoManual` (set via the History page's result dropdown or "Live Settle") permanently took precedence over the CSV's own `Resultado`, even after automated settlement later wrote a real, possibly different, result into `picks_history.csv`. A read-only investigation prompted by a reported inconsistency on "Huntsville City vs Crown Legacy" (2026-06-21) found this had already caused two real, silent bankroll/ROI misstatements: "Saint Etienne vs Nice" (2026-05-26) displayed a stale manual `W` (+€0.70) when automated settlement had actually determined `L` (−€1.00); "Nice vs Saint Etienne" (2026-05-29) displayed a stale manual `P` (€0.00) when automated settlement had determined `W` (+€1.00).

**Root cause:** The manual-override mechanism was designed as a bridge for bot picks automated settlement can't resolve, but its precedence logic had no expiry or reconciliation against the CSV once a real result eventually arrived — a human's earlier best guess could out-rank the actual, confirmed outcome indefinitely.

**Fix:** `getRowWithLocalEdits()` now prefers a valid CSV `Resultado` whenever one exists, falling back to `resultadoManual` only while the CSV cell is still empty/invalid. `getDailyRowsMerged()`'s cross-file reconciliation (borrowing a result from `picks_history.csv` when a row's own daily-CSV cell is empty) was extended identically, so it also wins over a stale manual override, not only over a genuinely-unresolved row. `resultadoManual` is never deleted or mutated automatically — it simply stops being read once the CSV has a real result, preserving it as an inert historical record (see ADR-015 for the full reasoning, including why automatic cleanup was rejected). The two affected historical bets now display the correct automated result; the Huntsville fixture (whose automated settlement genuinely never resolved) is unaffected and continues to show its manual result exactly as before.

---

### SETTLEMENT-2 — Manual Bets Bypassed `RESULT_READY_DELAY`, Settling Before the Equivalent Bot Pick for the Same Fixture

**Status:** Resolved — 2026-07-12 (Phase 26.32). Full technical detail in `08_Change_Log.md` — Phase 26.32.

**Was:** For a fixture with both a bot pick and a manual bet on the same market, clicking "Executar Resolução" would settle the manual bet immediately while the bot pick stayed `LIVE`. Some time later, without any manual intervention, the bot pick settled correctly on a subsequent run. Both eventually settled correctly, but never during the same execution.

**Root cause:** This was not a settlement-engine bug — `update_dataframe()` is the single shared engine for both bot picks and manual bets (ADR-002/ADR-009), processed atomically in the same `/run-settlement` request with a shared provider-response cache. The asymmetry was in the *input data*: `update_dataframe()`'s `KICKOFF_TOO_EARLY` gate (`now < KickoffUTC + RESULT_READY_DELAY` — 2h15m) only runs `if kickoff_str:` — i.e. only when the row actually has a `KickoffUTC` value. Bot picks always have it (propagated end-to-end since Phase 26.7–26.9). Manual bets never did: `addManualBetFromFixture()` (`index.html`) never set a `kickoffUTC` field on the bet object, despite `docs/08_Change_Log.md`'s Phase 26.7–26.9 entry claiming this field was "propagated through... manual bet objects" — that claim was inaccurate; only a transient, render-time-only placeholder (`kickoffUTC: ''`, for display formatting) existed, never a persisted field read by settlement. So a manual bet became eligible for settlement as soon as its date matched, with no 2h15m safety margin — while the bot pick for the identical fixture correctly waited out the delay.

**Fix:** Manual bets created from an existing fixture (the Scout workspace) now persist `kickoffUTC`, `homeTeam`, `awayTeam`, and `leagueId` (the last derived from the already-fetched `config.json.api_football.league_ids`, no new network call) at creation time — immutable fixture metadata, never re-derived from `state.fixtures` later. `manual_bets_to_settlement_df()` already read `bet.get('kickoffUTC')`; it simply had never been given real data. **No change was made to the settlement engine, `RESULT_READY_DELAY`, matching logic, or persistence architecture** — this was purely a data-completeness fix at bet-creation time. Free-form manual bets (the text-entry form, not tied to any fixture) are unaffected and continue to have no kickoff metadata — this is a documented, accepted limitation, not a bug: there is no fixture to source it from. Pre-existing manual bets created before this phase also have no kickoff metadata and are unaffected; no persistence migration was performed or required.

---

### DASHBOARD-3 — DASHBOARD-2's Fix Targeted the Wrong Page; Duplicate Visibility Corrected in the Operational List Instead

**Status:** Resolved — 2026-07-11 (Phase 26.31). Full technical detail in `08_Change_Log.md` — Phase 26.31. **Supersedes DASHBOARD-2 below — see that entry's note.**

**Was:** DASHBOARD-2's fix made `getRejectedManualBets()` hide a rejected bet from "Rejeitadas" once it settled. This was the wrong page to fix: "Rejeitadas" is the intended permanent archive of rejected bets (settled or not), while the actual duplicate-visibility problem was that the *operational* "Apostas Manuais" list never stopped showing a rejected bet after it settled — that list's filter (`renderManualBets()`) only checked `status` (`!== 'approved' && !== 'settled'`), and a rejected bet's `status` stays `'rejected'` forever (ADR-012), so it never dropped out of the list a user works from day to day.

**Root cause:** Two separate filters govern rejected-bet visibility, and DASHBOARD-2 corrected the one that didn't need it while leaving the real bug in place: `renderManualBets()`'s row filter had no check on settlement state at all, so a settled rejected bet stayed in the operational list indefinitely, needing no further action but still cluttering the page the user actually triages from.

**Fix:** `getRejectedManualBets()` reverted to its pre-DASHBOARD-2 predicate (`status === 'rejected'`, settled or not) — "Rejeitadas" is now correctly the permanent archive. `renderManualBets()`'s filter gained one additional exclusion: a `status === 'rejected'` bet with `_lucro !== null` (settled) is now hidden from the operational list. Net effect: a rejected bet appears in both "Apostas Manuais" and "Rejeitadas" while unsettled; once settled, it drops out of "Apostas Manuais" only, remaining permanently in "Rejeitadas" and in every analytical module that reads `state.manualBets` directly (unaffected by either fix, since none of them call `getRejectedManualBets()`).

---

### DASHBOARD-2 — Settled Rejected Bets Remained Visible in History → Rejeitadas, Creating Duplicate Visibility With Analytics

**Status:** Resolved — 2026-07-11 (Phase 26.28). **Note (2026-07-11, Phase 26.31): this fix targeted the wrong page — see DASHBOARD-3 above for the correction.** Full technical detail in `08_Change_Log.md` — Phase 26.28 and Phase 26.31.

**Was:** A rejected manual bet stayed visible in the History page's "Rejeitadas" view forever, even after settlement gave it a real result. At the same time, the same bet correctly began appearing in Strategy Lab, Opinion Validation, and other analytical modules once settled (by design — see ADR-012). This created the appearance of the same analytical record being shown twice at once.

**Root cause (as understood at the time):** `getRejectedManualBets()` (`index.html`) filtered only on `status === 'rejected'`, with no check on whether the bet had been settled. Since ADR-012 deliberately keeps a rejected bet's `status` at `'rejected'` forever — even after `resultado`/`lucro`/`placar` are populated by the shared settlement engine — this predicate returned every rejected bet regardless of settlement state. "Rejeitadas" is the only consumer of this function (2 call sites total: its own definition and `getRejectedHistoryRows()`); every analytical module (Strategy Lab, Opinion Validation, Recommendation Engine, Simulator, Bot vs Manual) sources its bet pool independently and never calls this function, so none of them were affected by the bug or by the fix.

**Fix applied at the time (since reverted — see DASHBOARD-3):** `getRejectedManualBets()` was changed to also require `b._lucro === null` (not yet settled). This was later recognised as fixing the symptom on the wrong page — "Rejeitadas" is the intended permanent archive, and the operational "Apostas Manuais" list was the one that actually needed the settlement check. See DASHBOARD-3.

---

### MANUAL-1 — Scout Card Stayed Visible for Pending Manual Bets; Rejected Bets Lost Their Status When Settled

**Status:** Resolved — 2026-07-10 (Phase 26.19). Full technical detail in `08_Change_Log.md` — Phase 26.19.

**Was (two related defects found while implementing the Manual Bet lifecycle rework):**
1. `renderManualScout()`'s hide-key only excluded fixtures with a manual bet in `status ∈ {approved, rejected, settled}` — a brand-new `pending` bet was not in that set, so its Scout card remained visible and clickable until the user approved or rejected it. A user who clicked "Criar" twice (or came back to the Manual Bets tab before approving) could create a second, duplicate bet for the same fixture.
2. `apply_df_results_to_manual_bets()` unconditionally set `status = 'settled'` on any bet that received a result, including bets the user had already rejected. A rejected bet whose fixture finished silently lost its "rejected" status the moment settlement ran, and — because `getResolvedManualBets()` only checked `_lucro !== null`, not `status` — it then counted as a real result in bankroll, ROI, and every other financial calculation, even though the user had explicitly declined to place it.

**Root cause:** Both were the same class of bug — a lifecycle check (`status === 'approved'`/`'rejected'`) that was written for the states that existed at the time and never revisited when a new state (`pending` staying visible; `rejected` meeting the settlement engine) started reaching that code path.

**Fix:** `renderManualScout()`'s hide-key now covers every bet regardless of `status`. `apply_df_results_to_manual_bets()` only advances `status` to `'settled'` when it was not already `'rejected'`. `getResolvedManualBets()` additionally excludes `status === 'rejected'`. See ADR-012 for the underlying decision (lifecycle status and settlement result are independent) and `03_Dashboard.md` §7/§9 for the resulting behaviour.

---

### SETTLEMENT-1 — "No Matches to Settle" Caused by an Expired API-Football Subscription Masquerading as Empty Fixtures

**Status:** Resolved — 2026-07-07 (Phase 26.18). Full technical detail in `08_Change_Log.md` — Phase 26.18.

**Was:** The dashboard reported "No matches to settle." on every settlement run, even though bets in non-EU leagues (MLS, Allsvenskan, Veikkausliiga, K League 1) had clearly finished. `updated` was 0 and every eligible pick came back `NO_MATCH`.

**Root cause:** The API-Football subscription had lapsed to the Free plan, which rejects the 2025/2026 season. API-Football responded with HTTP 200, an empty `response: []`, and the real reason in `errors.plan`. `update_dataframe()` never inspected `errors` on a 200 response — an empty `response` was indistinguishable from "no games today". Renewing the subscription fixed settlement immediately with no code change, confirming the settlement/matching logic itself was never broken.

**Fix:** API provider responses (both API-Football and football-data.org) are now validated for embedded errors before being trusted, normalized into one error record shape, logged, surfaced in the `/run-settlement` summary (`settlement_aborted`/`provider_errors`) and the dashboard (`⚠ Settlement unavailable`, plus a persistent provider-health badge), and tracked across runs in `cloud_state.json["providerHealth"]`. See ADR-011.

Full technical detail, root cause analysis, and validation for the rest of these is in `08_Change_Log.md` — Phase 26.17.

### LIVE-1 — Live Center Does Not Auto-Refresh Manual Bet Results

**Status:** Resolved — 2026-07-01 (Phase 26.17)

**Was:** The Live Center showed manual bets as LIVE after they had already been settled on the backend. The user had to manually click "Load Cloud" or trigger "Run Settlement" to see the updated result. Root cause: the 60-second `loadData()` auto-refresh interval fetched picks CSVs only and never called `GET /load`, so `state.manualBets` went stale whenever settlement happened outside the current tab.

**Fix:** Replaced the assumption of periodic polling with an event-driven refresh model. `state.manualBets` (and `state.movements`) now refresh on four events: boot (via a new `_bootSyncComplete` guard deciding between `_doLoadCloudState()` and `_reloadManualBetsFromCloud()`), on-demand settlement completing, the "Load Cloud" button, and the browser tab regaining visibility. The 60-second interval continues to refresh only the read-only picks CSVs and league stats.

### SYNC-1 — Bankroll Movements Lost During Cloud Recovery

**Status:** Resolved — 2026-07-01 (Phase 26.17)

**Was:** A fresh browser session (e.g. Incognito) that recovered state from `cloud_state.json` showed the correct bankroll base, manual bets, and betting KPIs, but ignored all deposits/withdrawals — bankroll totals, "Global Result", and the Movement History table differed from a normal session with existing local data, even though both were reading the same cloud data.

**Root cause:** `_doLoadCloudState()` and `_reloadManualBetsFromCloud()` copied `bankrollInicial`, `manualBets`, `localEdits`, and `sessionStartDate` from the `/load` response, but neither ever assigned `content.movements` to `state.movements`. `state.movements` stayed at its initializer value (`[]`) on any session that went through cloud recovery.

**Fix:** Both functions now include `state.movements = Array.isArray(content.movements) ? content.movements : []`, matching how every other recovered field is handled. The existing post-recovery `saveLocalState()` calls persist the recovered movements to `localStorage` — no new save call was introduced.

### SYNC-2 — Railway `GITHUB_REPO` Misconfiguration

**Status:** Resolved — 2026-07-01 (Phase 26.17)

**Was:** `GET /load` on the Railway backend returned an empty `{}` body, so any fresh session had nothing to recover from the cloud at all, independent of the SYNC-1 code defect above.

**Root cause:** `sync_server.py` builds the GitHub Contents API URL from the `GITHUB_OWNER`/`GITHUB_REPO` environment variables. Railway's `GITHUB_REPO` variable was set to the fully-qualified `jorgepita/apostas-over-futebol` instead of just `apostas-over-futebol`, producing a doubled path (`.../repos/jorgepita/jorgepita/apostas-over-futebol/...`) that 404s against GitHub. `update_results.py` was unaffected — it hardcodes the same two values as module-level constants instead of reading them from the environment — which is why GitHub Actions settlement and `/run-settlement` kept working the whole time.

**Fix:** The Railway `GITHUB_REPO` environment variable was corrected to `apostas-over-futebol`. No code change was made or needed (per ADR-010, this class of value belongs in environment configuration, not code).

### DASHBOARD-1 — Pending KPI / Alert Count Diverged From the Pending Page

**Status:** Resolved — 2026-07-01 (Phase 26.17)

**Was:** The "Pendentes Abertas" dashboard KPI and the "Muitas apostas abertas" alert both showed a higher count than the Pending page for the same nominal dataset.

**Root cause:** The Pending page's `getPendingRows()` excludes bets whose kickoff has already passed (those belong to Live Center). The KPI and the alert instead read `getRiskMetrics().openCount`, which counts every approved-and-unsettled bet with no kickoff-time filter — i.e. Pending + Live combined.

**Fix:** The KPI and the alert now call `getPendingRows()` directly. `getRiskMetrics().openCount` was left unchanged and is still used by the exposure/risk widgets ("Risco Atual", stake-at-risk figures), which intentionally include live bets since they measure total capital currently at risk, not the "awaiting kickoff" count.
