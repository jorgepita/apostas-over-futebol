# Change Log

Major architectural phases in reverse chronological order. Minor commits, CSV updates, and hotfixes are not listed — see `git log` for the full record.

---

## Summary

| Phase | Date | Summary |
|---|---|---|
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
