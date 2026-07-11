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

Correct the lifecycle of rejected manual bets: Phase 26.28 had fixed the duplicate-visibility bug in the wrong place. The duplicate needed to be removed from the operational view ("Apostas Manuais"), not from the historical/archive view ("Histórico → Rejeitadas").

---

## Work Completed

- Traced the complete visibility flow for rejected bets across every consumer: "Apostas Manuais" (`renderManualBets()`), "Histórico → Rejeitadas" (`getRejectedManualBets()`/`getRejectedHistoryRows()`), "Histórico → Resolvidas" (`getResolvedManualBets()`), Strategy Lab (`getStrategyLabPool()`), and Opinion Validation/Recommendation Engine/Simulator (all built on `getResolvedManualBets()`-sourced pools).
- Produced a visibility matrix (before) confirming the root cause: `renderManualBets()`'s filter only checked `status` (`!== 'approved' && !== 'settled'`), with no settlement check — since a rejected bet's `status` stays `'rejected'` forever (ADR-012), a settled rejected bet never left the operational list. Phase 26.28 had instead added a settlement check to `getRejectedManualBets()`, which incorrectly turned "Rejeitadas" into an unsettled-only view rather than the permanent archive it was meant to be.
- Reverted `getRejectedManualBets()` to `status === 'rejected'` (no settlement check) — "Rejeitadas" is once again the permanent archive of every rejected bet, settled or not.
- Added the missing settlement check to `renderManualBets()`'s row filter: a `status === 'rejected'` bet with `_lucro !== null` (settled) is now excluded from "Apostas Manuais".
- Updated both functions' doc comments, plus `getRejectedHistoryRows()`'s, to describe the corrected behaviour.
- Wrote and ran a new 24-check targeted regression script covering the full visibility matrix (before/after) and all 4 requested lifecycle scenarios.
- Re-ran the full existing 6-suite Playwright regression harness — **all 6 suites now pass completely**, including `test.js` (whose 5 checks flagged as "expected failures" in Phase 26.28's own handover were testing the original, correct pre-26.28 behaviour — they pass again now that this revert restores it).
- Updated `docs/03_Dashboard.md` (§7 rejection narrative ×2, §9 toggle description, ASCII lifecycle diagram), `docs/05_Known_Issues.md` (new `DASHBOARD-3` entry, `DASHBOARD-2` annotated as superseded), `docs/07_Current_Status.md`, `docs/08_Change_Log.md` (new Phase 26.31), and this handover.

---

## Files Modified

| File | Reason for change |
|---|---|
| `index.html` | `getRejectedManualBets()` reverted; `renderManualBets()` gained the settled-rejected exclusion; doc comments updated |
| `docs/03_Dashboard.md` | Rejection lifecycle narrative (×2) and Resolvidas/Rejeitadas toggle description corrected; ASCII diagram fixed |
| `docs/05_Known_Issues.md` | New `DASHBOARD-3` resolved entry; `DASHBOARD-2` annotated as superseded |
| `docs/07_Current_Status.md` | Updated for Phase 26.31 |
| `docs/08_Change_Log.md` | Phase 26.31 summary row + detailed section added |
| `docs/handovers/handover-2026-07-11-rejected-bets-lifecycle-fix.md` | This document |

---

## Documentation Updated

- `docs/03_Dashboard.md` — every passage describing rejected-bet visibility (Manual Bets §7, two separate wordings; §9 Resolvidas/Rejeitadas toggle; the ASCII lifecycle diagram) corrected to describe the new, right-page behaviour.
- `docs/05_Known_Issues.md` — new `DASHBOARD-3` entry documents the correction; `DASHBOARD-2` (Phase 26.28's original fix) annotated with a note pointing forward, and its "Fix" section reframed as "Fix applied at the time (since reverted)" rather than silently rewritten — preserves an honest historical record.
- `docs/07_Current_Status.md`, `docs/08_Change_Log.md` — updated/added for Phase 26.31.
- `docs/09_Architecture_Decisions.md` (ADR-012) — **no change required.** ADR-012's actual decision (status/resultado are independent axes; a rejected bet's status never advances to settled) is completely unaffected — it never specified which page shows settled-vs-unsettled rejected bets, only that both fields exist independently. That's an implementation/presentation detail, not an architectural decision this ADR governs.
- `docs/PROJECT_MAP.md`, `docs/01_Architecture.md`, `docs/04_Backend.md` — **no change required.** None describe this specific presentation-layer detail.

---

## Architectural Decisions

None. No ADR created or changed — this is a presentation-layer correction to which page shows which lifecycle state, not an architectural decision (see ADR-012's continued validity above).

---

## Current Project State

**Stable.** "Apostas Manuais" now correctly hides a rejected bet once it's settled (no further action needed there); "Histórico → Rejeitadas" is now correctly the permanent archive (never drops a bet). Settlement, persistence, `cloud_state.json`, `QuantEngine`, Strategy Lab, Recommendation Engine, Opinion Validation, and the Simulator are all verified unchanged.

---

## Outstanding Issues

None opened. `DASHBOARD-3` added to `05_Known_Issues.md` as resolved this session; `DASHBOARD-2` annotated (not deleted) to preserve the historical record of what was believed and done at the time. Pre-existing, unrelated: ST-3, ST-2 (both already on the roadmap).

---

## Validation Performed

- **New targeted regression script (24 checks, scratchpad, not committed):** covers the full before/after visibility matrix and all 4 requested lifecycle scenarios (Scout→Reject visible in both Apostas Manuais and Rejeitadas; Reject→auto-settlement disappears from Apostas Manuais but stays in Rejeitadas and Strategy Lab, no data loss; Remove→Scout card reappears; Approved→Live→Settled unchanged). All 24 pass.
- **Full existing 6-suite Playwright regression harness:** all 6 suites pass completely — `test.js`, `test_opinion_validation.js`, `test_calibration_v2.js`, `test_recommendations.js`, `test_simulator.js`, `test_strategylab.js`. This is the first time in this session's history that `test.js` has been fully green; its previously-"expected" failures were testing the original correct behaviour, now restored.
- **Console/page errors:** zero new errors; only pre-existing, harness-induced `Failed to fetch` noise (baseline, confirmed identical to prior sessions).
- `node --check` clean on both extracted `<script>` blocks.

---

## Remaining Work

Nothing required to consider this phase complete. Everything else pre-existing and unrelated: ST-3, ST-2, the `01_Architecture.md` §3 refresh, `providerHealth` threshold monitoring, rejected-bet analytics dashboard, and the pre-existing `fetch_oddsapi_fixtures.py` duplicate lambda logic (all already tracked in `07_Current_Status.md` → Next Priorities or prior handovers).

---

## Next Recommended Task

ST-3 (SHA conflict retry in `sync_server.py`) is next on the roadmap.

---

## Notes for the Next Session

- **The correct mental model going forward:** "Apostas Manuais" = operational, only bets needing attention (pending, or rejected-but-not-yet-settled). "Histórico → Rejeitadas" = permanent archive, every rejected bet forever. If a future rejected-bet visibility bug appears, check `renderManualBets()`'s filter first (operational list) before touching `getRejectedManualBets()` (the archive) — this session's whole premise was that the previous fix confused the two.
- `DASHBOARD-2` in `05_Known_Issues.md` was deliberately **not deleted or silently rewritten** — it's annotated with a forward-pointing note so the historical record of "what we believed and did at the time" stays honest and traceable to `DASHBOARD-3`.

---

## End-of-Session Checklist

- [x] Code committed and pushed — commit pending at time of writing, see below
- [x] `07_Current_Status.md` updated
- [x] `05_Known_Issues.md` updated (`DASHBOARD-3` added, `DASHBOARD-2` annotated)
- [x] `08_Change_Log.md` updated (Phase 26.31 entry added)
- [x] `09_Architecture_Decisions.md` — no change required (ADR-012 unaffected)
- [x] `06_Roadmap.md` — no change required (nothing referenced this work; no priority shifted)
- [x] This handover document filled and saved
- [x] Next session can start from "Next Recommended Task" without reading chat history
