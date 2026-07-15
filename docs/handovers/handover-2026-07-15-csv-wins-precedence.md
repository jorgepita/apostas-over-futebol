# Session Handover

---

## Session Information

```
Date:     2026-07-15
Branch:   main
Commit:   9b1c007d "fix(picks): automated settlement always wins over stale manual
          override" — committed and pushed, merged into origin/main as 4a685708
```

---

## Session Objective

Fix a design flaw identified by a prior session's read-only investigation: a bot pick's manual result override (`localEdits.resultadoManual`) permanently took precedence over `picks_history.csv`'s own `Resultado`, even after automated settlement later determined the real result. Flip the precedence so automated settlement always wins once it exists, keep the manual override working exactly as before for fixtures automated settlement never resolves, and verify every downstream consumer (History, bankroll, ROI, Strategy Lab, Opinion Validation, Recommendation Engine, Simulator).

---

## Root Cause

`getRowWithLocalEdits()` computed:
```js
const resultadoFinal = ['W', 'L', 'P'].includes(resultadoManual) ? resultadoManual : resultadoBase;
```
A valid `resultadoManual` always won, with no reconciliation once the CSV later got a real result. For the fixture that originally prompted the investigation ("Huntsville City vs Crown Legacy", 2026-06-21) this was benign — the CSV never got a result at all, so the override was legitimately bridging a genuine automated-settlement gap.

A systematic scan of all 12 historical `resultadoManual` overrides against the current `picks_history.csv` (performed this session, before writing any code) found this was **not only theoretical**: two real bets had a manual override that disagreed with the automated result that arrived afterward, and the dashboard was silently showing the stale, wrong one:

| Fixture | Manual override (stale, was shown) | Automated CSV result (now available, correct) |
|---|---|---|
| Saint Etienne vs Nice (2026-05-26, real stake €1 @ 1.7) | W, +€0.70 | L, −€1.00 |
| Nice vs Saint Etienne (2026-05-29, real stake €1 @ 2.0) | P, €0.00 | W, +€1.00 |

Both are real, `apostada: true` bets with real money entered — this was a genuine, live bankroll/ROI misstatement, not a cosmetic issue.

A secondary instance of the same class of bug was found in `getDailyRowsMerged()`'s cross-file reconciliation (which borrows a result from `picks_history.csv` when a row's own daily-CSV cell is empty): its gate (`enriched._resultKey === 'pending' && found`) was already satisfied-away by a manual override, so it silently skipped even when history had a real, possibly-conflicting result.

---

## Implementation

**Investigation before writing code (per instruction):** grepped every occurrence of `resultadoManual` (4 total: default initializer, the read/precedence site, and 2 write sites — the History-page dropdown and `settleBotBet()`/"Live Settle") and every consumer of the resulting `_resultKey`/`_resultadoFinal`. Confirmed:
- The precedence logic exists in exactly one place (`getRowWithLocalEdits()`), consumed identically by every downstream reader (History, bankroll, ROI aggregation, `getRiskMetrics()`, Live/Pending classification) — none of them independently re-implement any precedence logic, so fixing this one function is sufficient for all of them.
- `getDailyRowsMerged()` has one secondary consumer with an equivalent gap (see Root Cause above).
- Strategy Lab, Opinion Validation, the Recommendation Engine, and the Simulator are **entirely unaffected** — traced their data-source functions and confirmed all four operate exclusively on settled **manual bets** (`state.manualBets`, own `resultado` field, everything gated on `b.hadAnalysis === true`), a completely disjoint data model from bot picks' `localEdits.resultadoManual`.

**Fix applied (`index.html`):**
1. `getRowWithLocalEdits()` — `resultadoFinal` now prefers a valid CSV `resultadoBase` whenever one exists; `resultadoManual` is only consulted when the CSV cell is empty/invalid.
2. `getDailyRowsMerged()` — the reconciliation condition changed from `enriched._resultKey === 'pending' && found` to `!ownCsvResult && found` (checking the row's own raw CSV cell directly), so history's real result now wins even when a manual override had already filled this row's own gap.

**Cleanup decision:** evaluated automatic deletion of stale `resultadoManual` values and rejected it. `getRowWithLocalEdits()` runs on effectively every render; mutating `state.localEdits` from inside it would make a pure "compute merged row" function silently stateful (risking `markDirty()`/cloud-save cascades triggered by rendering rather than user action), and would destroy the exact audit trail that made finding the two conflicts above possible. Per the task's own stated fallback ("if automatic cleanup introduces any risk, simply ignore the override"), the stale values are left in place in `cloud_state.json["localEdits"]` — present, but never read again once the CSV has a real result. Recorded as ADR-015.

---

## Files Modified

| File | Reason for change |
|---|---|
| `index.html` | `getRowWithLocalEdits()` precedence flipped (CSV wins); `getDailyRowsMerged()`'s cross-file reconciliation condition changed to check the row's own raw CSV cell instead of the post-override `_resultKey` (16 lines changed, 2 functions) |
| `docs/03_Dashboard.md` | `state.localEdits` schema note extended with the new precedence rule |
| `docs/09_Architecture_Decisions.md` | New ADR-015 |
| `docs/05_Known_Issues.md` | New `DASHBOARD-4` resolved entry |
| `docs/08_Change_Log.md` | New Phase 26.34 entry (summary row + full section) |
| `docs/07_Current_Status.md` | Header, two new narrative paragraphs, "Completed Areas" bullet, ADR count corrected (13 → 15, was already stale before this session) |
| `docs/handovers/handover-2026-07-15-csv-wins-precedence.md` | This document |

`01_Architecture.md`, `04_Backend.md`, `06_Roadmap.md`, `PROJECT_MAP.md`, `02_Data_Flow.md` — **no change required.** Grepped each for `resultadoManual`/`getRowWithLocalEdits`/`getDailyRowsMerged` — zero matches; none of these documents describe this mechanism, so none are now stale.

---

## Documentation Updated

- `docs/03_Dashboard.md` — `state.localEdits` schema entry, new precedence-rule note.
- `docs/09_Architecture_Decisions.md` — new **ADR-015** (precedence decision + the explicit no-automatic-cleanup reasoning).
- `docs/05_Known_Issues.md` — new **DASHBOARD-4** resolved entry.
- `docs/08_Change_Log.md` — summary table row + full Phase 26.34 section (root cause, investigation, fix, files, validation, impact).
- `docs/07_Current_Status.md` — header, "Overall Project Status" narrative (2 new paragraphs for 26.34), "Completed Areas" bullet, "Current Development" narrative, ADR count fix.

---

## Architectural Decisions

**ADR-015 added** — "A Bot Pick's Manual Result Override (`resultadoManual`) Is a Temporary Bridge; Automated Settlement Always Wins Once It Exists." This is a genuine precedence-rule reversal from the implicit prior design (manual override wins permanently) plus an explicit, reasoned decision not to auto-delete stale overrides — both constrain future implementation choices the way an ADR is meant to, so this qualifies per the project's own ADR criteria, unlike Phase 26.33 which didn't.

---

## Current Project State

**Stable.** Automated settlement (`picks_history.csv` / `picks_hoje_simplificado.csv`) is now unconditionally the final source of truth for a bot pick's result once it exists, in both the primary precedence check and the daily/history cross-file reconciliation. The two historical misstatements are corrected in the running dashboard logic (verified against the real, current `cloud_state.json`/`picks_history.csv` — see Validation below); no data migration was performed or needed. Committed as `9b1c007d` and pushed to `origin/main` (merged as `4a685708`) later in the same session.

---

## Outstanding Issues

None opened. `DASHBOARD-4` added to `05_Known_Issues.md` as resolved this session.

---

## Validation Performed

- **Syntax:** `node --check` on both extracted `<script>` blocks — clean.
- **Playwright, targeted script (10 checks, scratchpad, not committed — `pwtest/test_csv_wins_precedence.js`), covering every scenario the task specified:**
  1. CSV empty + `resultadoManual = W` → dashboard shows W (bridge intact).
  2. CSV later becomes L → dashboard now shows L (CSV wins over the stale manual W).
  3. Bankroll/profit updates using L (`_lucroRealLocal` recomputed correctly: −€10.00 for a €10 stake).
  4. ROI/History aggregation row (`getFilteredRealClosedRows()`) reflects L / −€10.00.
  5. Strategy Lab's manual-bet pool builds and is demonstrably sourced only from `state.manualBets` (unaffected by the bot-pick change).
  6/7. Recommendation Engine / Simulator's `window._opnSimCache` builds normally from the same disjoint manual-bet pool — unaffected.
  8. A fixture with **only** ever a manual settlement (CSV never resolves) still shows its manual result exactly as before — confirmed no regression to the bridge behaviour.
- **Verified directly against real production data** (current `cloud_state.json` + `picks_history.csv`, loaded into the real running app, not synthetic rows): "Saint Etienne vs Nice" now resolves to `L` / −€1.00 (was `W` / +€0.70); "Nice vs Saint Etienne" now resolves to `W` / +€1.00 (was `P` / €0.00); "Huntsville City vs Crown Legacy" still correctly resolves to `P` (CSV genuinely still empty, `_lucroRealLocal` still `null` since no real stake was ever entered for it) — confirming the fix corrects exactly the two real misstatements while leaving the legitimate bridge case byte-for-byte unaffected.
- **Full existing 7-suite Playwright regression harness** (the 6 standing suites — `test.js`, Opinion Validation, Recommendations, Simulator, Strategy Lab, Calibration v2 — plus Phase 26.33's approval-default test): all 7 pass completely, zero console/page errors.
- **`python -m pytest tests/`:** 186/186 passed, unchanged — no Python file was touched.
- **`git diff --stat`:** confirms only `index.html` changed (16 lines) for the code portion of this phase.

---

## Remaining Work

None for this task — complete as scoped. Committed and pushed (see Session Information above).

---

## Next Recommended Task

ST-3 (SHA conflict retry in `sync_server.py`) remains next on the roadmap — unrelated to this session's change.

---

## Notes for the Next Session

- **This session's changes were committed and pushed** (`9b1c007d`, merged as `4a685708`) after the user explicitly requested it later in the same session — per the standing git safety policy, a commit is never made without an explicit request, which is exactly what happened here.
- **A subsequent project-closure review** (same session, after this handover was first written) re-verified the full 8-suite Playwright regression harness and the Python suite against the actual pushed state (both fully green), confirmed no debug code/TODOs/dead functions were introduced, and corrected this handover's and the sibling Phase 26.33 handover's "uncommitted" language, which had gone stale the moment the user asked for commit+push. No code changed during that review — documentation-only correction.
- The two historically-misstated bets (Saint Etienne vs Nice, Nice vs Saint Etienne) are corrected by this fix automatically the next time `index.html` loads with current data — no separate data-repair action is needed or was performed.
- `resultadoManual` values for those two bets **remain** in `cloud_state.json["localEdits"]` — inert, by design (see ADR-015). If a future session ever wants to purge genuinely-dead overrides, that would be a new, separate decision requiring its own risk analysis; this session deliberately did not do that.
- If a future change ever needs to distinguish "resolved by automated settlement" from "resolved by manual bridge" in the UI (e.g., a small badge), the raw signal already exists: compare the row's own CSV `Resultado` cell (or the history-reconciliation source) against `_resultadoFinal` — no new field would be needed.
- **Follow-up verification (same session, post-commit):** the user asked for explicit confirmation that no other place in the repo reads `resultadoManual` directly and could bypass the new precedence. Repo-wide grep confirmed exactly 4 code sites total, all in `index.html` — the fixed precedence site, a default initializer, a write-only dropdown handler, and `settleBotBet()`'s read, which is only a manual-vs-manual idempotency guard (never compares against the CSV, has no bearing on what's displayed). No other file — Python, JS, or otherwise — references the field. Confirmed safe.
- **Side-finding from that grep, not yet acted on:** `dashboard_state.json` (repo root) is a tracked file holding a `localEdits`-shaped structure, with 534 commits between 2026-03-15 and 2026-04-26 and none since — it predates the current `cloud_state.json` architecture (ADR-001, 2026-06-28) and is referenced by zero code in the current codebase (not `index.html`, not any Python file, not any GitHub workflow). It appears to be dead, orphaned data from a design that was superseded, analogous to the already-documented "`manual_bets.csv` is dead" precedent (ADR-001) — just never formally called out anywhere. It cannot affect this fix (nothing reads it), so no action was taken this session, but it's worth a deliberate cleanup/deletion decision in a future session if repository hygiene is revisited (similar in spirit to Phase 26.26).

---

## End-of-Session Checklist

- [x] Code committed and pushed — `9b1c007d`, merged as `4a685708`
- [x] `07_Current_Status.md` updated
- [x] `05_Known_Issues.md` updated (`DASHBOARD-4` added)
- [x] `08_Change_Log.md` updated (Phase 26.34 entry added)
- [x] `09_Architecture_Decisions.md` updated (ADR-015 added)
- [x] `06_Roadmap.md` — no change required (no priority shifted, confirmed via grep)
- [x] This handover document filled and saved
- [x] Next session can start from "Next Recommended Task" without reading chat history
