# Session Handover

---

## Session Information

```
Date:     2026-08-04
Branch:   phase-26.46-exposure-warning-current-production
Commit:   this commit (HEAD at session start: 73448101 — "fix: season-recency-aware boot sync so returning browsers adopt a newer cloud season")
```

---

## Session Objective

Phase 28.4 (read-only audit, prior turn this session): trace why History/Bank/Dashboard Home/Bot vs Manual kept showing previous-season data after a correctly-executed Season Close, with Phase 28.3A's boot-sync fix already confirmed working. Phase 28.5 (this work): implement the smallest architectural fix identified by that audit — wire the dashboard's existing season-boundary infrastructure (`isOnOrAfterSession()`) into the pages that were never connected to it — without redesigning the season system, archive system, backups, or cloud synchronization.

---

## Work Completed

- **Phase 28.4 audit conclusion (informs this work):** not a Season Close defect — `executeSeasonClose()` correctly resets `bankrollInicial`/`manualBets`/`movements`/`localEdits` and never touches `picks_history.csv` (a permanent, cross-season record by design). The gap: `isOnOrAfterSession()` already existed and was already correctly wired into `getMetrics()`'s `sessao` bundle and Strategy Lab's default season filter, but was never connected to `getFilteredRealClosedRows()` (History/Home/Bank's evolution chart), `getBankrollState()` (Bank's documented single source of truth), or `renderVersus()` (Bot vs Manual + the whole Opinion suite via `window._opnSimCache`). This is `docs/06_Roadmap.md`'s DX-4, a previously-deferred, documented gap — not a regression.
- **Phase 28.5 fix (`index.html` only):**
  - New shared, memoized helpers `getSessionRealResolvedBotHistory()`/`getSessionResolvedManualBets()`, next to `getResolvedManualBets()` — each a one-line `.filter(isOnOrAfterSession(...))` wrapper.
  - `getMetrics()`'s `sessao` bundle now calls these instead of its own inline filter.
  - `getBankrollState()` now sums these instead of independently recomputing an all-time figure — eliminating a real, provably-divergent duplicate bankroll calculation. Its own per-row profit formula (`_lucroRealLocal ?? _lucroModeloLocal`) is unchanged.
  - `renderBankrollPerformanceBreakdown()` and `renderBankrollAudit()` (`.geral` → `.sessao`) updated for consistency.
  - `renderVersus()`: top-level `botRows`/`manualRows` now use the two helpers; 7 further independent `getResolvedManualBets()` re-derivations inside the same function (score-band calibration, Opinion Validation's `opinionBets`, Edge Realization, and 3 inside Model Health) all now reuse the single `manualRows` variable — collapsing 8 independent computations into 1. This is the single change that makes Opinion Validation/Calibration/Recommendation Engine/Simulator season-aware automatically (they consume `window._opnSimCache`, populated from this same pool).
  - `getFilteredRealClosedRows(filters, sessionOnly = false)` gained one optional parameter. Exactly 4 call sites pass `true`: `getHistoryFilteredRows()`, `renderSummaryHeadlineStats()`, `renderBankrollChart()`, `renderBankrollEvolution()`. All ~18 other call sites (archive snapshot, every Analytics-tab function, the Close Season wizard's own review step) are untouched.
  - `renderHistoryIntelligence()`'s separate "highest edge" anomaly card now uses `getSessionRealResolvedBotHistory()`.
  - `exportRealCsv()` now calls `getHistoryFilteredRows()` directly instead of an independent, slightly different call — export always matches the table.
- **Explicitly not touched:** `executeSeasonClose()`, `csmExecute()`/`csmGoStep4()`, `buildSeasonArchiveObject()`, the backup subsystem, R2, Railway, GitHub persistence, cloud sync, and Strategy Lab's own pre-existing season filter (`getStrategyLabPool()`). Analytics (`league_stats.csv`) left completely unchanged and documented as intentionally excluded — no season concept exists anywhere in the Python backend.
- Validated: `node --check`, full Python suite (430/430), QuantEngine golden vectors (285/285), and a new real-browser Playwright regression (27/27 assertions across 3 scenarios — see Validation Performed below).
- Documentation updated in the same session (see below).

---

## Files Modified

| File | Reason for change |
|---|---|
| `index.html` | Added the two session-scoped helpers; refactored `getMetrics()`, `getBankrollState()`, `renderBankrollPerformanceBreakdown()`, `renderBankrollAudit()`, `renderHistoryIntelligence()`, `exportRealCsv()`, `getFilteredRealClosedRows()`, `getHistoryFilteredRows()`, `renderSummaryHeadlineStats()`, `renderBankrollChart()`, `renderBankrollEvolution()`, `renderVersus()`. |
| `docs/03_Dashboard.md` | Documented the new season-scoping behaviour for Home/Summary, History, Analytics (explicit exclusion), Bankroll, and Bot vs Manual. |
| `docs/05_Known_Issues.md` | Added `DASHBOARD-8` (Resolved), documenting the Phase 28.4 finding and the Phase 28.5 fix. |
| `docs/06_Roadmap.md` | Updated DX-4 from "Deferred" to "Partially done (Phase 28.5)" — a season selector for *archived* seasons specifically is still not built. |
| `docs/07_Current_Status.md` | New "Last Updated" entry; updated "Current Development" and the "Dashboard" completed-areas bullet. |
| `docs/08_Change_Log.md` | New summary-table row and full "Phase 28.5" section (folding in the Phase 28.4 audit narrative, matching this project's convention of not giving read-only audits their own row). |
| `docs/handovers/handover-2026-08-04-phase-28.5.md` | This handover. |

No production runtime data file (`cloud_state.json`, any CSV) was touched — confirmed via `git status`.

---

## Documentation Updated

- `docs/03_Dashboard.md`
- `docs/05_Known_Issues.md` (new `DASHBOARD-8`, Resolved)
- `docs/06_Roadmap.md` (DX-4 status updated)
- `docs/07_Current_Status.md`
- `docs/08_Change_Log.md`
- This handover

---

## Architectural Decisions

None. This phase implements an existing, previously-designed-but-unfinished feature (MT-4/DX-4 in `06_Roadmap.md`) using existing infrastructure — no new ADR was needed or created.

---

## Current Project State

Stable. Dashboard-only, JS-only change, fully backed by a real-browser regression suite and the unchanged Python/QuantEngine baselines. No other subsystem (settlement, generation, backups, cloud sync) was touched.

---

## Outstanding Issues

None related to this phase. `06_Roadmap.md` DX-4 remains partially open: there is still no UI to select a *specific archived* season for History/Bank/Analytics — only "current season" (now the default) and "all-time" (used internally by Analytics/the archive) exist. A future session could build that selector on top of `getStrategyLabPool()`'s existing `archive:{id}` pattern.

---

## Validation Performed

- `node --check` on the extracted `<script>` block — OK.
- `python -m pytest -q` — 430 passed, 0 failed (unchanged).
- `node tests/test_quant_engine_golden.js` — 285/285 assertions passed (unchanged).
- New scratchpad Playwright script (`test_phase285_season_boundary.js`, Chromium, network fully mocked — not committed, per this project's established scratchpad-tooling convention), driving the real, unmodified `index.html` and its real, now-modified functions directly via `page.evaluate()` (not a reimplementation):
  1. **Immediately after Season Close** (old-season bot pick present, no new-season activity): History page empty; Dashboard Home summary rows/DOM empty; Bot vs Manual KPI row empty; Bank shows current bankroll = starting bankroll, P/L = €0, global result = €0, session ROI/W/L/resolved-count all zero; evolution chart shows its empty state; the old-season row confirmed still present in the all-time `getHistoryRowsMerged()` store (not deleted); no unexpected `POST /save`. **11 checks, all pass.**
  2. **A new-season bet correctly appears**: one new bot pick + one new manual bet (dated on/after `sessionStartDate`) correctly show in History/Bank/`window._opnSimCache`, while the old-season bot pick stays excluded from every session-scoped view but remains fully visible in `.geral` (the untouched all-time bundle Analytics/the archive still use). **5 checks, all pass.**
  3. **Regression**: Strategy Lab's own season pool, Pending, Live Center, Manual Bets, Daily Picks all compute without error; Analytics's enrichment call confirmed to still see the full all-time pool and renders without error. **11 checks, all pass.**
  - **Total: 27/27 assertions passed, zero page errors.**

---

## Remaining Work

None for this phase. See "Outstanding Issues" for the one still-open roadmap item (archived-season selector, DX-4's remaining half).

---

## Next Recommended Task

None specific — this closes `DASHBOARD-8`. See `07_Current_Status.md`'s "Next Priorities" for the project's other standing, unrelated follow-ups.

---

## Notes for the Next Session

- The scratchpad Playwright test (`test_phase285_season_boundary.js`) lives entirely in this session's temporary scratchpad directory, not the repository — consistent with every prior session's Playwright validation.
- A genuine, pre-existing formula divergence was found (not fixed, out of scope) during implementation: `getBankrollState()`'s per-row profit formula falls back to `_lucroModeloLocal` when `_lucroRealLocal` is null; `buildMetricsBundle()`'s `realBotProfit` (feeding `.sessao`/`.geral`) does not have this fallback. This means `getBankrollState().lucroReal` and `getMetrics().sessao.realProfit` can differ by a small amount in the edge case of an approved, resolved bot pick with a missing real stake/odd. Deliberately left alone this phase (a financial-formula change beyond "add a season filter" needs its own explicit sign-off) — flagged here for whoever picks it up next.
- If a future session builds the DX-4 archived-season selector, `getFilteredRealClosedRows()`'s new `sessionOnly` boolean parameter is the natural place to extend into a full season-mode string (mirroring `getStrategyLabPool(seasonMode)`'s existing `'current'`/`'all'`/`'archive:{id}'` pattern) rather than inventing a second mechanism.
- Per this session's explicit instructions: do not commit unless asked, do not push.

---

## End-of-Session Checklist

- [ ] Code committed (pending — see final instructions this session)
- [x] `07_Current_Status.md` updated
- [x] `05_Known_Issues.md` updated (new `DASHBOARD-8` added, Resolved)
- [x] `08_Change_Log.md` updated (phase completed)
- [ ] `09_Architecture_Decisions.md` updated — not applicable, no new ADR this phase
- [x] `06_Roadmap.md` updated (DX-4 status changed)
- [x] This handover document filled and saved
- [x] Next session can start from "Next Recommended Task" without reading chat history
