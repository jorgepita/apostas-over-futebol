# Session Handover

---

## Session Information

```
Date:     2026-07-21
Branch:   mls-fix-current-production-v2
Commit:   Not yet committed — all changes below are in the working tree, pending explicit user approval before commit/push (per this session's instructions)
```

---

## Session Objective

Implement a safe, architecture-consistent policy so an approved bet whose fixture is postponed, cancelled, abandoned, or persistently undiscoverable can no longer stay financially exposed indefinitely — the gap Phase 26.42's investigation flagged and deferred (Chicago Fire vs Vancouver Whitecaps, 2026-07-17). Two safeguards: automatic voiding (explicit non-played status after 48h; persistent missing-fixture after 72h with repeated-attempt evidence and a bounded rediscovery search) and a manual "Anular aposta" fallback in Live Center (24h). Both settle as the existing `P` result through the existing shared engine.

**Before proceeding to commit**, a dedicated read-only pre-commit safety audit (same session) re-verified the implementation and found three defects, all corrected within this same still-uncommitted session — see "Pre-Commit Safety Audit Correction" below. This handover describes the final, corrected state.

---

## Work Completed

### Original implementation

- **Full settlement-lifecycle audit** of `update_results.py` (`update_dataframe()`, both provider branches, `RESULT_READY_DELAY`, `KickoffUTC` handling, league routing, the manual-bet settlement bridge), `sync_server.py`, `src/config.py`, `config.json`, and the relevant `index.html` sections (Live Center, Pending, `getRiskMetrics()`, `getBankrollState()`, the pre-existing "Live Settle" quick-settle mechanism) before writing any code.
- **Status classification** (`classify_af_status()`/`classify_fd_status()` in `update_results.py`) — extends the pre-existing `AF_FINISHED_STATUS`/`FD_FINISHED_STATUS` sets with `IN_PROGRESS` (never void-eligible at any age — the crucial safety rule), `NON_PLAYED` (`PST`/`CANC`/`ABD` on API-Football; `POSTPONED`/`CANCELLED` on football-data.org — **corrected by the audit; see below**), and a default `SCHEDULED_UNKNOWN` bucket. `AWD`/`WO` deliberately left unclassified (rare, unreliable goal data).
- **Automatic void — explicit non-played status (Part 3).** Wired into `try_update_row_via_api_football()` and the football-data.org branch of `update_dataframe()`: once a `NON_PLAYED` status is observed `POSTPONED_VOID_AFTER_HOURS` (default 48h) after the row's own persisted **original** `KickoffUTC` (never overwritten while unresolved), `void_result_row()` writes `Resultado="P"` via the existing `calc_profit()`/`calc_real_profit()` plus `SettlementReason` (`postponed_timeout`/`cancelled_timeout`/`abandoned_timeout`).
- **Automatic void — persistent missing fixture (Part 4/5).** New `_evaluate_missing_fixture_void()`: a genuine `NO_MATCH` (never a provider error — that's a different reason string and never reaches this function) increments a new persisted `MissingAttempts` counter. Voids only once `MISSING_FIXTURE_VOID_AFTER_HOURS` (72h) has elapsed **and** `MissingAttempts >= missing_fixture_min_attempts` (3) **and** a bounded, forward-only, AF-only rediscovery search (`attempt_rediscovery_af()`, `+2..+14` days from original kickoff, reusing the existing per-run `(league, date)` fixture cache) also finds nothing. Found-but-finished → settles normally (`W`/`L`); found-but-not-finished → keeps waiting, counter resets to 0. `try_update_row_via_api_football()`'s three call sites inside `update_dataframe()` were consolidated into one nested helper, `_run_af_and_account()`.
- **Manual void — "Anular aposta" (Part 6/7).** New `manualVoidBet()` in `index.html`, gated by a new `voidEligible` flag on each `getLiveRows()` row (kickoff known **and** `Date.now() - kickoffMs >= MANUAL_VOID_AVAILABLE_AFTER_HOURS * 3600000`). Explicit PT-PT confirmation. Reuses `settleManualBet()`/`settleBotBet()` (both gained an optional `reason` parameter) — distinct button/entry point from the pre-existing, unrestricted, unchanged generic quick-settle `P` button.
- **Configuration (Part 12).** New `config.json["settlement"]["void_policy"]` section (`postponed_void_after_hours: 48`, `missing_fixture_void_after_hours: 72`, `manual_void_available_after_hours: 24`, `missing_fixture_min_attempts: 3`), read via a new `src.config.get_void_policy()` (defensive per-key validation, `DEFAULT_*` fallback constants). The dashboard reads the one value it needs via a new `loadVoidPolicyConfig()`, reusing the same GitHub raw-content `config.json` fetch Scout's `loadModelConfig()` already established.
- **Audit trail (Part 11).** Two additive CSV columns, `SettlementReason` and `MissingAttempts` (appended to `CSV_COLUMNS`; `SYNC_RESULT_COLUMNS` updated). Manual bets carry the same two fields as `bet['settlementReason']`/`bet['missingAttempts']`. `apply_df_results_to_manual_bets()` returns `(newly_settled, evidence_changed)` — both `run_settlement_remote()` and `main()` save `cloud_state.json` whenever `evidence_changed > 0`, not only on a new settlement or provider-health change.

### Pre-Commit Safety Audit Correction (same session, before any commit)

A dedicated read-only audit re-traced the implementation's persistence lifecycle, rediscovery cost, and status-classification safety before proceeding to commit. It found and this session corrected three defects:

1. **SUSP/INT/SUSPENDED were unsafely auto-void-eligible — genuine safety defect.** The original implementation grouped `SUSP`/`INT` (API-Football) and `SUSPENDED` (football-data.org) with `PST`/`CANC`/`ABD` under the same 48h explicit-status timeout, reasoning "a suspended/interrupted match needs the identical don't-stay-exposed-forever treatment a postponed one does." The audit's counter-scenario proved this unsafe: a match interrupted Monday, still reporting `INT`/`SUSP` on Wednesday (48h later), that legitimately resumes and finishes Friday — the original code would have auto-voided it Wednesday, incorrectly, since the match was always going to produce a real result. **Fix:** `SUSP`/`INT` removed from `AF_NON_PLAYED_STATUS`; `SUSPENDED` removed from `FD_NON_PLAYED_STATUS`. They now fall through to the pre-existing `SCHEDULED_UNKNOWN` default (never auto-void-eligible at any age; the 24h manual fallback remains available). Documented, not silently dropped, via `AF_SUSPENDED_INTERRUPTED_STATUS`/`FD_SUSPENDED_INTERRUPTED_STATUS` (not consulted by `classify_af_status()`/`classify_fd_status()` — purely so a future edit doesn't silently re-add them). `AF_VOID_REASON_BY_STATUS`/`FD_VOID_REASON_BY_STATUS` had their now-orphaned `SUSP`/`INT`/`SUSPENDED` entries removed — `interrupted_timeout` no longer occurs.
2. **`getRowWithLocalEdits()` never merged `edit.settlementReason` into the canonical row — audit-trail bug in the manual-bot bridge case.** The write side worked (`manualVoidBet()` → `settleBotBet(key, 'P', reason)` correctly set `state.localEdits[key].settlementReason`), but nothing merged it back into the row object History actually reads from — a bot pick manually voided while its CSV result was still empty (the `resultadoManual` bridge case, ADR-015) showed a correct `P` result with a blank "Motivo" line. **Fix:** `getRowWithLocalEdits()` now resolves `settlementReasonFinal` with the *exact same branch condition* `resultadoFinal` already uses — while the CSV's `Resultado` is empty, use `edit.settlementReason`; once the CSV has a real result, the CSV's own `SettlementReason` wins outright, even when blank (a normal win has no void reason to show). **Caught its own bug during fixing:** an initial fix attempt used an independent "CSV value wins whenever non-empty" fallback instead — this left a stale "Anulada manualmente" label next to a CSV-authoritative `W`, because the CSV's own (correctly blank) `SettlementReason` lost to the still-present stale local value under that logic. The regression test written for this exact scenario caught it before it shipped.
3. **`src/history.py`'s `HISTORY_COLUMNS` schema drift — found to be a pre-existing, already-active production bug, not something this phase introduced.** `HISTORY_COLUMNS` (a separate, hardcoded schema list consumed by the *daily generation* persistence path — `main.py` → `persist_history()` → `merge_into_history()` → `ensure_simple_columns()` — distinct from `update_results.py`'s `CSV_COLUMNS`, which the *settlement* engine uses) was never updated when `Placar` was added in Phase 26.19. `ensure_simple_columns()`'s reindex (`df[HISTORY_COLUMNS]`) is a hard "keep only these columns" operation — it silently stripped `Placar` from every settled row on each daily generation cycle. **Confirmed already active against real production data:** 90 of 93 settled rows in the live `picks_history.csv` had an empty `Placar` at audit time; only the 3 most recent hadn't yet been through a generation cycle. This phase's own new `SettlementReason`/`MissingAttempts` fields were exposed to the identical erasure path — tracing *their* persistence lifecycle is what surfaced the pre-existing `Placar` bug. **Fix:** `HISTORY_COLUMNS` extended to `Data, Liga, Jogo, Mercado, Odd, Stake€, Edge%, Apostada, OddReal, StakeReal€, Resultado, Placar, Lucro€, LucroReal€, KickoffUTC, SettlementReason, MissingAttempts` — an exact mirror of `CSV_COLUMNS`. A second, separate consumer, `src/pipeline.py`'s `save_all_outputs()`, reindexes to `HISTORY_COLUMNS` directly without `ensure_simple_columns()`'s add-if-missing safety net — verified it would otherwise raise `KeyError` on every generation run once the schema grew; fixed with three explicit blank-column assignments (`simple["Placar"] = ""`, etc.), matching the existing style already used for `Apostada`/`Resultado`/etc. **This fix is preventative only** — it stops future loss; it does **not** and must **not** attempt to reconstruct the ~90 already-lost historical `Placar` values (would require querying providers for old fixture data; out of scope; documented as `05_Known_Issues.md` SETTLEMENT-4).

**Corrected the Chicago Fire projection.** The original report claimed the fixture was "projected to auto-void on the next real settlement run," reasoning `MissingAttempts` was "already well past the minimum from ~8 settlement runs since 2026-07-17." This was wrong: the live `picks_history.csv` has no `MissingAttempts` column at all yet (the new policy has never run against production), so the effective current value is 0. Corrected lifecycle: run 1 → 0→1, no rediscovery, no void; run 2 → 1→2, same; run 3 → 2→3, meets the minimum, triggers the bounded rediscovery search — if it also finds nothing (consistent with the prior ±10-day investigation), voids as `P`/`missing_fixture_timeout`. At the normal twice-daily cadence this is ≈1.5 days after the mechanism starts accumulating evidence, assuming every run produces a genuine `NO_MATCH`.

---

## Files Modified

| File | Reason for change |
|---|---|
| `update_results.py` | Status classification (corrected: SUSP/INT/SUSPENDED removed from `*_NON_PLAYED_STATUS`, documented via `*_SUSPENDED_INTERRUPTED_STATUS`), `void_result_row()`, `_evaluate_missing_fixture_void()`, `attempt_rediscovery_af()`, `_run_af_and_account()` refactor, `CSV_COLUMNS`/`SYNC_RESULT_COLUMNS` additions, `manual_bets_to_settlement_df()`/`apply_df_results_to_manual_bets()` bridge extension, void-policy config loading |
| `config.json` | New `settlement.void_policy` section |
| `src/config.py` | New `DEFAULT_*` constants + `get_void_policy()` |
| `src/history.py` | **Audit correction:** `HISTORY_COLUMNS` extended to mirror `CSV_COLUMNS` exactly (adds `Placar`, `SettlementReason`, `MissingAttempts`) |
| `src/pipeline.py` | **Audit correction:** `save_all_outputs()` gained explicit blank-column assignments for the 3 new `HISTORY_COLUMNS` fields, preventing a `KeyError` |
| `index.html` | `MANUAL_VOID_AVAILABLE_AFTER_HOURS` + `loadVoidPolicyConfig()`; `getLiveRows()` `voidEligible`; "Anular aposta"/"Anular" button (desktop + mobile Live Center); `manualVoidBet()`; `settleManualBet()`/`settleBotBet()` gained optional `reason` param; `settlementReasonLabel()` + History "Motivo" line; `settlementReason` propagated through `getManualRowsMerged()` and `getFilteredRealClosedRows()`; **audit correction:** `getRowWithLocalEdits()` now resolves and merges `SettlementReason` with the same branch condition as `resultadoFinal` |
| `tests/test_void_policy.py` | 28 tests (25 original + 3 new; 1 renamed/flipped — see Validation) |
| `tests/test_history_schema.py` | New — 9 tests for the `HISTORY_COLUMNS` audit correction |
| `docs/09_Architecture_Decisions.md` | New ADR-017, including a full "Correction" section covering all three audit findings and a corrected status-classification matrix |
| `docs/04_Backend.md` | §7 new subsection (classification table corrected; new paragraphs for the bridge-merge fix and the `HISTORY_COLUMNS` fix); §10 config/defaults tables updated |
| `docs/03_Dashboard.md` | §3 (`state.localEdits`) and §8 (Live Center) updated for `settlementReason`/the bridge-merge fix |
| `docs/02_Data_Flow.md` | Manual settlement flow diagram — new fields |
| `docs/05_Known_Issues.md` | New `SETTLEMENT-4` entry documenting the pre-existing `Placar`-loss bug as resolved (preventative fix, no historical reconstruction) |
| `docs/07_Current_Status.md` | Header, Overall Project Status, Completed Areas, Current Development (corrected Chicago Fire projection + audit summary), Next Priorities |
| `docs/08_Change_Log.md` | Phase 26.43 section rewritten with the audit correction; summary row updated |

---

## Documentation Updated

- `docs/09_Architecture_Decisions.md` (new ADR-017 + "Correction" section)
- `docs/04_Backend.md`
- `docs/03_Dashboard.md`
- `docs/02_Data_Flow.md`
- `docs/05_Known_Issues.md` (new `SETTLEMENT-4`)
- `docs/07_Current_Status.md`
- `docs/08_Change_Log.md`

`docs/01_Architecture.md`, `docs/06_Roadmap.md`, `docs/PROJECT_MAP.md`, `docs/00_Project_Context.md` reviewed and found not to need changes — no component/file/directory/navigation structure changed.

---

## Architectural Decisions

**New ADR-017**, including a same-session "Correction" section. "Approved unresolved wagers cannot remain exposed indefinitely; qualifying non-played wagers are eventually voided as P under configurable timeout rules, with a controlled manual fallback — but a suspended/interrupted match is not one of the qualifying statuses, since it commonly resumes under the same fixture ID." Explicitly does not split the shared settlement engine (extends ADR-002/ADR-009's reuse principle to voids) and explicitly keeps the three timeout values in `config.json` rather than as hardcoded module constants (extends ADR-010). The "Do Not Revert" section now explicitly warns against re-adding `SUSP`/`INT`/`SUSPENDED` to the 48h auto-void bucket without a fundamentally different mechanism and a fresh safety analysis.

---

## Current Project State

**Stable — feature implemented, audited, corrected, tested, documented; not yet committed.** All changes are in the working tree per this session's explicit instruction to wait for approval before committing or pushing. Full Python suite (253 tests) and all Playwright regression scripts (existing + new) pass with zero regressions. No production data (CSVs, `cloud_state.json`) was touched or altered this session — all verification (including the `HISTORY_COLUMNS` fix) used isolated temporary files or monkeypatched paths, never the real repository files.

---

## Outstanding Issues

- None newly opened.
- **Not live-verified:** whether Chicago Fire vs Vancouver Whitecaps actually voids as (now correctly) projected depends on ≈3 real settlement runs (≈1.5 days) observing genuine `NO_MATCH` each time — recommend monitoring the first several settlement runs after deployment, not just the first one.
- **Historical `Placar` reconstruction is explicitly deferred, not resolved.** The ~90 already-affected rows in `picks_history.csv` still have an empty `Placar`. This session's fix is preventative only. A separate, explicitly-approved data-repair task would be required to reconstruct them (would need to query providers for old fixture data).
- **Deliberately non-configurable:** `MISSING_FIXTURE_MIN_ATTEMPTS` (3) and the rediscovery window (`+2..+14` days) are fixed constants in `update_results.py`, not `config.json` values — reasoned in ADR-017 as search-cost/evidence-count bounds rather than policy thresholds.
- The manual-void button's desktop label is the shorter "Anular" (space-constrained action column) while the mobile card uses the fuller "Anular aposta" — both trigger the identical confirmation text and mutation; a judgment call, not dictated by the brief.

---

## Validation Performed

- Full Python test suite: **253/253 passing** (`python -m pytest tests/ -v`) — 216 pre-existing + 28 in `tests/test_void_policy.py` (25 original + `test_fd_suspended_after_48h_remains_unresolved`, `test_suspended_interrupted_very_old_fixture_still_never_auto_voids`, `test_suspended_interrupted_classification_falls_through_to_scheduled_unknown`; the original `test_suspended_interrupted_after_threshold_becomes_p` renamed/flipped to `test_suspended_interrupted_after_48h_remains_unresolved`) + 9 new in `tests/test_history_schema.py`.
- `test_history_schema.py` specifically covers: `HISTORY_COLUMNS`/`CSV_COLUMNS` set-equality (guards the next drift), `ensure_simple_columns()` legacy-row tolerance, `merge_into_history()` realistic round-trips preserving `Placar`/`SettlementReason`/`MissingAttempts`, a legacy row with none of the new columns at all, `save_all_outputs()` not raising `KeyError`, a **3-run `MissingAttempts` lifecycle routed through the actual `load_history()`/`update_dataframe()`/`merge_into_history()` cycle** (not just `update_dataframe()` in isolation — this is the exact path the audit found could independently erase the counter), and `SettlementReason`/`Placar` surviving a simulated generation cycle immediately after a void.
- `node --check` on the extracted `index.html` script block (clean, zero syntax errors) — re-run after the `getRowWithLocalEdits()` fix.
- Playwright: `sanity_check.js` (zero page errors), `test_manual_void.js` (15/15, re-run), new `test_settlementreason_bridge.js` (17/17 — the full bridge lifecycle: void → PT-PT confirmation → localStorage-persistence-equivalent reload → later CSV-authoritative settlement correctly overriding both the result *and* the reason per ADR-015), plus the full pre-existing 7-script regression set — all re-run, all passing.
- JS golden-vector conformance suite: 285/285 assertions passing — confirms `QuantEngine` untouched.
- `save_all_outputs()`/`merge_into_history()` verified directly (ad hoc scripts, not just pytest) against realistic `combo`/`existing`-history DataFrames to confirm no `KeyError` and correct column preservation before writing the formal regression tests.
- No `/run-settlement` call, no live `main.py`/`run_topup.py` execution, no production `cloud_state.json`/`picks_history.csv`/`picks_hoje*.csv` write this session — every test used a temp file or monkeypatched path.
- `__pycache__/*.pyc` artifacts regenerated by running pytest were reverted to `HEAD` after every test run (final `git status` below is clean of them).

---

## Remaining Work

- Await explicit user approval, then commit and push.
- After deployment, monitor the first several settlement runs (not just the next one) to confirm: (a) normal FT/AET/PEN settlement is unaffected across all leagues; (b) a genuinely suspended/interrupted match is never auto-voided, only ever reachable via manual void; (c) `Placar` now survives generation cycles for newly-settled rows; (d) the Chicago Fire vs Vancouver Whitecaps pick's `MissingAttempts` accumulates as expected and it eventually voids (or is found via rediscovery) after ≈3 runs, not the first one.
- Consider a separate, explicitly-approved follow-up task if historical `Placar` reconstruction for the ~90 affected rows is ever wanted.
- Consider, in a future session, whether `MISSING_FIXTURE_MIN_ATTEMPTS`/the rediscovery window should become configurable if real-world usage suggests the fixed defaults are miscalibrated.

---

## Next Recommended Task

Commit and push this fix (pending user approval), then monitor the first several settlement runs to confirm the automatic void safeguards — including the SUSP/INT correction and the `HISTORY_COLUMNS` fix — behave as designed against live provider data.

---

## Notes for the Next Session

- This feature intentionally does **not** touch the shared settlement engine's core matching/decision logic, `RESULT_READY_DELAY`, `QuantEngine`, the H1/H2/H3 render dispatcher, or the MLS/MLS Next Pro routing fix (Phase 26.42) — all confirmed unaffected by design and by regression testing, including after the audit correction.
- **Do not re-add `SUSP`/`INT`/`SUSPENDED` to `AF_NON_PLAYED_STATUS`/`FD_NON_PLAYED_STATUS`** without re-reading ADR-017's "Correction" section — that is exactly the mechanism the pre-commit audit found unsafe.
- **`HISTORY_COLUMNS` in `src/history.py` must be kept as an exact mirror of `CSV_COLUMNS` in `update_results.py`.** If `CSV_COLUMNS` ever gains another settlement-written field, add it to `HISTORY_COLUMNS` in the same position too — `tests/test_history_schema.py::test_history_columns_matches_canonical_csv_columns` will fail loudly if this is forgotten, which is the point.
- The new `_run_af_and_account()` helper inside `update_dataframe()` is a `nonlocal`-closure function over the surrounding loop's counters — keep it inside `update_dataframe()`'s scope.
- `MANUAL_VOID_AVAILABLE_AFTER_HOURS` in `index.html` is a `let`, not a `const` — intentionally mutated once by `loadVoidPolicyConfig()`. Do not convert it to `const`.
- `getRowWithLocalEdits()`'s `settlementReasonFinal` resolution must stay tied to the *same* branch condition as `resultadoFinal` (which source produced the currently-displayed result), never an independent "non-empty wins" fallback — the latter shape was tried, was wrong, and is exactly what `test_settlementreason_bridge.js`'s final block (CSV-wins-over-stale-manual-reason) guards against regressing to.
- The Playwright test scripts used this session live only in the scratchpad `pwtest` directory from a prior session (`...\97225357-5c90-464c-855d-7bae1695dec3\scratchpad\pwtest`), which this session reused (local `node_modules`/Playwright/Chromium already set up there) — per this project's established convention, none of this is part of the committed repository.
- `git status` may show `__pycache__/*.pyc` files as modified after running pytest — these are pre-existing tracked bytecode artifacts (the repo's `.gitignore` has `__pycache__/` but doesn't retroactively untrack already-tracked files), unrelated to this session's actual changes. This session reverted them to `HEAD` after every test run; the final `git status` below is clean of them.

---

## End-of-Session Checklist

- [ ] Code committed and pushed — **intentionally not done; awaiting explicit user approval per this session's instructions**
- [x] `07_Current_Status.md` updated (including the corrected Chicago Fire projection)
- [x] `05_Known_Issues.md` updated (new `SETTLEMENT-4`, resolved/preventative)
- [x] `08_Change_Log.md` updated (Phase 26.43 section rewritten with the audit correction)
- [x] `09_Architecture_Decisions.md` updated (ADR-017 + "Correction" section)
- [x] `06_Roadmap.md` reviewed — no change needed
- [x] This handover document rewritten and saved
- [x] Next session can start from "Next Recommended Task" without reading chat history
