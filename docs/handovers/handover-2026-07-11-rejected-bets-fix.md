# Session Handover

---

## Session Information

```
Date:     2026-07-11
Branch:   main
Commit:   (pre-commit — see End-of-Session Checklist)
```

---

## Session Objective

Fix a Manual Bet lifecycle presentation bug: rejected manual bets stayed visible in the History page's "Rejeitadas" view forever, even after settlement gave them a real result, creating the appearance of the same analytical record being shown twice at once (it also correctly appears in Strategy Lab/Opinion Validation/etc. once settled, by design). Investigate first, confirm it's purely a filtering issue, implement the minimal fix, verify no dedicated "is settled" helper already existed to reuse, and validate zero impact on every other lifecycle transition and analytical module.

---

## Work Completed

- Traced the complete lifecycle of a rejected bet: storage (`cloud_state.json` → `manualBets`), where settlement writes `resultado`/`placar`/`lucro`/`settledAt` (backend's `apply_df_results_to_manual_bets()`, `status` left at `'rejected'` per ADR-012), and every frontend filter site that reads rejected/settled state (`getResolvedManualBets()`, `getRejectedManualBets()`, `getStrategyLabPool()`).
- Identified the exact root cause: `getRejectedManualBets()` filtered only on `status === 'rejected'`, with no settlement-state check — it is the sole function backing History → Rejeitadas (2 call sites total: itself + `getRejectedHistoryRows()`), and no analytical module (Strategy Lab, Opinion Validation, Recommendation Engine, Simulator, Bot vs Manual) calls it — they each source bet pools independently, so none of them were affected by the bug.
- Implemented the approved fix: `getRejectedManualBets()` now also requires `b._lucro === null` (not yet settled). Updated its docstring and `getRejectedHistoryRows()`'s docstring, both of which had explicitly documented the old "shows settled or not" behaviour as intentional.
- **Quality review (this session's specific ask):** searched the entire codebase for an existing `isSettled()`/`isResolvedBet()`/`hasSettlement()`/`isOpenBet()`-style helper before finalizing the fix. None exists — the established convention throughout `index.html` is the raw inline check `_lucro === null`/`!== null` (already used 5+ times, including inside the sibling function `getResolvedManualBets()`) or `_resultKey === 'pending'` (used 6+ times). Per the project's stated preference for the existing convention over a one-use abstraction, no helper was introduced — the implementation was kept exactly as originally written.
- Updated `docs/03_Dashboard.md` in 4 places that had documented the old behaviour as intentional (Manual Bets §, Step 5 lifecycle narrative, the ASCII lifecycle diagram, and §9's Resolvidas/Rejeitadas toggle description).
- Added a new resolved-issue entry, `DASHBOARD-2`, to `docs/05_Known_Issues.md`.
- Updated `docs/07_Current_Status.md` and `docs/08_Change_Log.md` for Phase 26.28.
- Re-ran full lifecycle and regression validation (see below) — confirmed identical results to the pre-quality-review validation, since no code changed as a result of the helper search (none was found to reuse).

---

## Files Modified

| File | Reason for change |
|---|---|
| `index.html` | `getRejectedManualBets()` predicate narrowed to `status === 'rejected' && b._lucro === null`; two doc comments updated |
| `docs/03_Dashboard.md` | 4 passages updated to describe the new settled/unsettled distinction |
| `docs/05_Known_Issues.md` | New resolved-issue entry `DASHBOARD-2` |
| `docs/07_Current_Status.md` | Updated for Phase 26.28 |
| `docs/08_Change_Log.md` | Phase 26.28 summary row + detailed section added |
| `docs/handovers/handover-2026-07-11-rejected-bets-fix.md` | This document |

---

## Documentation Updated

- `docs/03_Dashboard.md` — updated (lifecycle documentation, as required).
- `docs/05_Known_Issues.md` — new `DASHBOARD-2` resolved-issue entry.
- `docs/07_Current_Status.md` — "Last Updated" line, a new Phase 26.28 narrative paragraph, the Manual Bet lifecycle "Completed Areas" bullet updated, Current Development section updated.
- `docs/08_Change_Log.md` — new Phase 26.28 summary row and full detailed section.
- `docs/09_Architecture_Decisions.md` (ADR-012) — **no change required.** ADR-012's actual decision (status/resultado are independent axes; a rejected bet's status never advances to settled) is completely unaffected by this fix. It never mandated that "Rejeitadas" show settled bets forever — that was a downstream implementation/comment detail in `03_Dashboard.md` and `index.html`, now corrected to match the refined behaviour.
- `docs/PROJECT_MAP.md`, `README.md`, `CLAUDE.md`, and every other `docs/` file — **no change required.** None reference this specific lifecycle detail.

---

## Architectural Decisions

None. No ADR was created, changed, or reversed — this is a presentation-filter bug fix consistent with (not contradicting) ADR-012's existing decision.

---

## Current Project State

**Stable.** `index.html`'s `getRejectedManualBets()` is the only functional change. Settlement, persistence, `cloud_state.json`, CSV schema, bankroll, ROI, and every analytical module (Strategy Lab, Opinion Validation, Recommendation Engine, Simulator, Bot vs Manual) are verified unchanged.

---

## Outstanding Issues

None opened. `DASHBOARD-2` added to `05_Known_Issues.md` as **resolved** this session. Pre-existing, unrelated: ST-3, ST-2 (both already on the roadmap).

---

## Validation Performed

- **Quality-review search.** Grepped `index.html` for `function is[A-Z]`, `function has[A-Z]`, `function.*settl`, and const-based equivalents — confirmed no dedicated settlement-state helper exists anywhere; the fix correctly follows the codebase's existing inline-check convention rather than introducing a new one.
- **Syntax.** `node --check` on both extracted `<script>` blocks — zero errors.
- **New targeted regression script (19 checks, scratchpad, not committed to the repo):** seeded rejected+unsettled, rejected+settled, approved+settled, and plain-pending bets; verified `getRejectedManualBets()` returns exactly the unsettled rejected bet; `getResolvedManualBets()` unchanged; `getStrategyLabPool('all')` still includes the settled rejected bet; the Rejeitadas DOM table shows only the unsettled bet; the Resolvidas DOM table shows neither rejected bet; zero duplicate visibility; the Pending→Rejected→(settled)→disappears-from-Rejeitadas-but-stays-in-state transition; the unrelated Remove transition unaffected. All 19 passed, identically before and after the quality-review step (no code changed as a result of it).
- **Full existing 6-suite Playwright harness re-run:** `test_opinion_validation.js` (19/19), `test_calibration_v2.js` (11/11), `test_recommendations.js` (22/22), `test_simulator.js` (26/26), `test_strategylab.js` (32/32, including explicit checks that the pool still includes the rejected bet and the production baseline still excludes it) — all pass. `test.js` shows 5 **expected** post-fix failures asserting the old buggy behaviour (not a regression; not edited, since it's ephemeral scratchpad tooling never committed to the repo).
- **Console/page errors.** Zero real errors; the only console output anywhere was the pre-existing `Failed to fetch` noise from the test harness's deliberate network blocking, confirmed identical on the unmodified suite (baseline, not caused by this fix).

---

## Remaining Work

- Nothing required to consider this fix complete.
- Everything else pre-existing and unrelated: ST-3, ST-2, the `01_Architecture.md` §3 refresh, `providerHealth` threshold monitoring, rejected-bet analytics dashboard (all already tracked in `07_Current_Status.md` → Next Priorities).

---

## Next Recommended Task

ST-3 (SHA conflict retry in `sync_server.py`) is next on the roadmap — this fix is complete, validated, and documented.

---

## Notes for the Next Session

- If a genuine second consumer of "is this bet settled" logic is ever added, revisit whether a shared helper (`isBetSettled(b)` or similar) is now justified — today it still is not, since `_lucro === null`/`!== null` remains a single, consistent, already-repeated convention across the file.
- The scratchpad Playwright test files (`test.js` and friends) now contain 5 assertions in `test.js` that encode the *pre-Phase-26.28* behaviour and will keep failing until someone updates them to expect the new (correct) behaviour — this is expected, not a sign of a real regression. None of that tooling is committed to the repository.

---

## End-of-Session Checklist

- [x] Code committed and pushed — commit pending at time of writing, see below
- [x] `07_Current_Status.md` updated
- [x] `05_Known_Issues.md` updated (`DASHBOARD-2` added as resolved)
- [x] `08_Change_Log.md` updated (Phase 26.28 entry added)
- [x] `09_Architecture_Decisions.md` — no change required (no ADR affected)
- [x] `06_Roadmap.md` — no change required (nothing referenced this work; no priority shifted)
- [x] This handover document filled and saved
- [x] Next session can start from "Next Recommended Task" without reading chat history
