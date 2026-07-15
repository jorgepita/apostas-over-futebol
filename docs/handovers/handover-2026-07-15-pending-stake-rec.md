# Session Handover

---

## Session Information

```
Date:     2026-07-15
Branch:   main
Commit:   Not committed — user explicitly requested no commit/push this session.
          Working tree has uncommitted changes to index.html + docs/ (see Files Modified).
```

---

## Session Objective

Two phases, same session, same feature thread:

- **Phase 26.36:** Implement the Task 2 design review from the prior session (StakeReal-zero-guard investigation): the Pending page's "Stake" column for bot picks shows the raw model stake, but after Phase 26.33/26.35 the operationally relevant comparison is "Stake rec." (what was recommended) vs "Stake Real" (what was actually staked). Pure UX/display change — explicitly no changes to bankroll, settlement, persistence, exposure calculation, StakeReal behaviour, or any recommendation algorithm.
- **Phase 26.37 (immediate follow-up, same session):** correct a wording flaw Phase 26.36 introduced — the desktop table's shared column header was renamed to "Stake rec.", but that header also sits above manual rows, which have no recommendation concept. Revert the desktop header wording only (back to "Stake"); the underlying value and mobile label are unaffected.

---

## Work Completed

- Re-verified the initialization workflow and confirmed the repo was fully in sync with `origin/main` (no drift since the prior session's commit `74286934`) before making any change.
- Traced every place the Pending table obtains its displayed Stake value: `getPendingRows()` (`index.html`) is the single source; its only consumers are `renderPendingQueue()` (desktop table) and `buildPendingCardHtml()` (mobile card) — both purely presentational. No KPI, exposure, or bankroll calculation reads `.stake` from this function (confirmed by grepping every call site of `getPendingRows()` — the others only read `.length`).
- Confirmed `getPendingRows()` builds two structurally disjoint row shapes: `manualRows` (`.stake = b.stake`, the bet's own entered stake — manual bets have no model/recommended/real split) and `botRows` (`.stake` was `r._stakeModeloNum`, the raw model stake). Only the `botRows` branch needed to change.
- Implemented the fix: `botRows`' mapping now computes `computeRecommendedStake(r).value` per row and uses it as `.stake` — reusing the exact same function Daily Picks and the Phase 26.33/26.35 approval auto-fill already call, with no new implementation. `manualRows` is completely untouched.
- Renamed the desktop table's shared `<th>Stake</th>` to `<th>Stake rec.</th>` (as explicitly instructed, accepting that this single shared header technically describes a "recommendation" concept that doesn't exist for the manual rows sharing the same column — flagged in Additional Observations below).
- Improved on that for the mobile card: added a per-row `stakeLabel` local (`'Stake rec.'` for `_type === 'bot'`, unchanged `'Stake'` for `_type === 'manual'`) — the mobile card is therefore more semantically precise than the desktop table, which can't easily be made row-conditional without a more invasive table restructure (out of scope, "desktop layout unchanged" constraint).
- Wrote a new targeted Playwright script (`pwtest/test_pending_stake_rec.js`, 19 checks) covering: desktop header rename, a bot pick that followed the recommendation exactly (Stake rec. === Stake Real), a bot pick with a deliberate override (Stake rec. ≠ Stake Real, real value untouched), an unapproved bot pick correctly absent from Pending, the manual row's `stake` completely unchanged, desktop cell text matching the underlying value, the mobile card's per-row label, Daily Picks' underlying `_stakeModeloNum` untouched, exposure/bankroll unaffected, `state.manualBets` byte-identical, History rendering without error, and Pending's date-ascending sort preserved. All 19 pass.
- Ran the full existing 9-suite Playwright regression harness (adding Phase 26.35's `test_stakereal_zero_guard.js` to the 8-suite set used last session) — all pass, zero console/page errors.
- Ran the full Python test suite — 186/186 passed, unchanged (no Python file touched).
- Updated `docs/08_Change_Log.md` (new Phase 26.36 entry), `docs/07_Current_Status.md`, and `docs/03_Dashboard.md` — the Pending section was previously incomplete (documented only the manual-bet half of `getPendingRows()`; the bot-pick half was entirely undocumented, a pre-existing gap flagged but not fixed last session). Since this phase directly changes behaviour inside that function, the section was rewritten to describe both halves properly, not just patched for the new Stake rec. detail.

**Phase 26.37 (same session, immediate follow-up):**
- Reverted the desktop table's `<th>Stake rec.</th>` back to `<th>Stake</th>` — the header is shared by both row types in one table, and "Stake rec." mislabels manual rows, which have no recommendation concept. Value logic untouched: `botRows`' `.stake` is still `computeRecommendedStake(r).value`; `manualRows`' `.stake` is still `b.stake`.
- Confirmed the mobile card's per-row `stakeLabel` (introduced in Phase 26.36: `'Stake rec.'` for bot, `'Stake'` for manual) already implemented exactly the target behaviour — no change needed there, per the task's own instruction ("No change required unless a simpler implementation naturally reuses the same logic").
- Extended the inline comment above `botRows`' mapping to explain the desktop-header-vs-mobile-label distinction for future readers.
- Updated the existing targeted Playwright script (`pwtest/test_pending_stake_rec.js`) in place — its header assertion now checks for plain "Stake" (not "Stake rec."), since the script verifies current intended behaviour, not a frozen snapshot of Phase 26.36. All 19 checks still pass.
- Re-ran the full 9-suite Playwright regression harness and the full Python test suite — all pass, zero regressions.
- Updated `docs/08_Change_Log.md` (new Phase 26.37 entry), `docs/07_Current_Status.md`, `docs/03_Dashboard.md` (Pending section's header/label description corrected), and this handover.

---

## Files Modified

Net state after both phases (26.36 then 26.37, same session):

| File | Reason for change |
|---|---|
| `index.html` | `getPendingRows()`'s `botRows` mapping — `.stake` sourced from `computeRecommendedStake(r).value` instead of `r._stakeModeloNum` (26.36, unchanged by 26.37); desktop header ends this session as `<th>Stake</th>` (26.36 renamed it to "Stake rec.", 26.37 reverted the wording); `buildPendingCardHtml()` has a per-row `stakeLabel` (`'Stake rec.'` bot / `'Stake'` manual — introduced 26.36, unchanged by 26.37) |
| `docs/08_Change_Log.md` | New Phase 26.36 entry, then new Phase 26.37 entry |
| `docs/07_Current_Status.md` | Header, narrative paragraphs (one per phase), "Completed Areas" bullet, "Current Development" narrative — updated for both phases |
| `docs/03_Dashboard.md` | Pending page section rewritten (26.36) to cover both bot and manual row types (previously incomplete), then corrected (26.37) to describe the final header/label wording |
| `docs/handovers/handover-2026-07-15-pending-stake-rec.md` | This document — updated in place to cover both phases rather than forking a second handover for the same-session follow-up |

`05_Known_Issues.md`, `09_Architecture_Decisions.md`, `06_Roadmap.md`, `01_Architecture.md`, `04_Backend.md`, `PROJECT_MAP.md` — **no change required.** No open issue was fixed (this was a design-review finding, not a filed bug), no ADR introduced, no roadmap priority shifted, no backend/repository-structure file touched.

---

## Documentation Updated

- `docs/08_Change_Log.md` — summary table rows + full sections for Phase 26.36 and Phase 26.37.
- `docs/07_Current_Status.md` — header, narrative (one paragraph per phase), "Completed Areas", "Current Development".
- `docs/03_Dashboard.md` — Pending page section, extended to cover both row types and the new Stake rec. source (26.36), then corrected for the final header/label wording (26.37).

---

## Architectural Decisions

None. `getPendingRows()` already computed derived display fields from merged row data; this changes which already-existing function supplies one field (`.stake` for bot rows). `computeRecommendedStake()` itself is untouched; no new dependency, call pattern, or persistence path was introduced.

---

## Current Project State

**Stable.** The Pending page's bot-row "Stake" value shows exactly the figure `computeRecommendedStake()` produces (the same figure the approval auto-fill uses or would use), directly comparable to "Stake Real." The desktop column header reads plain "Stake" (semantically correct for both row types it displays); the mobile card's per-row label still says "Stake rec." for bot rows and "Stake" for manual rows. All validation (19 targeted checks re-run and passing against the final Phase 26.37 state, full 9-suite regression harness, full Python suite) passes. **Not committed or pushed** — per explicit instruction both phases this session.

---

## Outstanding Issues

None opened or resolved. This phase implemented a design-review recommendation from the prior session, not a filed Known Issue.

---

## Validation Performed

Run once after Phase 26.36, then again in full after Phase 26.37's header-wording revert:

- **Syntax:** `node --check` on both extracted `<script>` blocks of `index.html` — clean, both phases.
- **Playwright, targeted script (19 checks, scratchpad, not committed — `pwtest/test_pending_stake_rec.js`, updated in place after 26.37 to assert the current header text "Stake" instead of "Stake rec."):** see Work Completed above for the full scenario list. All 19 pass against the final Phase 26.37 state.
- **Full existing 9-suite Playwright regression harness:** all 9 suites pass completely, zero console/page errors — re-run after Phase 26.37.
- **`python -m pytest tests/`:** 186/186 passed, unchanged — run after both phases.
- **`git diff --stat`:** confirms only `index.html` changed for the code portion of each phase. (`pytest` regenerates `src/__pycache__/calculations.cpython-314.pyc` as a side effect each time — reverted with `git checkout` after both runs, same pre-existing repo quirk noted in the prior handover.)

---

## Remaining Work

None — complete as scoped, not committed per instruction.

---

## Next Recommended Task

ST-3 (SHA conflict retry in `sync_server.py`) remains next on the roadmap — unrelated to this session's changes.

Separately, worth a future repository-hygiene session: add `__pycache__/` to `.gitignore` (noted in the prior handover, still unaddressed — `pytest` keeps regenerating a tracked `.pyc` file every session).

---

## Notes for the Next Session

- **This session's changes were NOT committed or pushed** — the user explicitly instructed "Do not commit. Do not push." (both Phase 26.36 and Phase 26.37). `index.html` and the three docs files listed above have uncommitted working-tree changes as of the end of this session, on top of the already-committed Phase 26.35 changes (commit `74286934`, pushed).
- **The shared-column labelling caveat flagged after Phase 26.36 is now resolved.** That handover note observed the desktop `<th>` read "Stake rec." even though manual rows below it show a plain entered stake — Phase 26.37, in the same session, reverted the desktop header wording to plain "Stake" specifically to close this gap. No caveat remains: the desktop header is neutral/correct for both row types; the mobile card's per-row label remains precise (`'Stake rec.'` bot / `'Stake'` manual).
- The `pwtest` Playwright harness used this session lives in a prior session's scratchpad directory, not this session's own — consistent with every prior session's Playwright validation in this repository (not committed to the repository, per established convention).
- `docs/03_Dashboard.md`'s Pending section was previously incomplete (only documented the manual-bet half of `getPendingRows()`) — this was flagged as an observation in an earlier session's handover but not fixed then, since documentation was restricted to that session's own Task 1. It was fixed in Phase 26.36 because that phase's actual code change lives inside the function that section describes, then kept current through Phase 26.37.
- Repeated from the prior handover, still unaddressed: `pytest` regenerates a tracked `src/__pycache__/*.pyc` file every run; `__pycache__/` is still not gitignored. Worth a future repository-hygiene session.

---

## End-of-Session Checklist

- [ ] Code committed and pushed — **intentionally not done**, per explicit user instruction (both phases this session)
- [x] `07_Current_Status.md` updated
- [x] `05_Known_Issues.md` — no change required (no issue filed, resolved, or affected)
- [x] `08_Change_Log.md` updated (Phase 26.36 entry, then Phase 26.37 entry, both added)
- [x] `09_Architecture_Decisions.md` — no change required (no architectural decision introduced)
- [x] `06_Roadmap.md` — no change required (no priority shifted)
- [x] This handover document updated in place to cover both phases
- [x] Next session can start from "Next Recommended Task" without reading chat history
