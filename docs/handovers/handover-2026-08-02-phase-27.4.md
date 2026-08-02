# Session Handover

---

## Session Information

```
Date:     2026-08-02
Branch:   phase-26.46-exposure-warning-current-production
Commit:   514677e8 (base — Phase 27.3, committed locally in the prior session, NOT pushed) — a new commit for Phase 27.4 was created this session on top of it — see below — but NOT pushed
```

---

## Session Objective

Phase 27.4 — remove football-data.org completely from the project while preserving every existing feature and behaviour, following a read-only dependency audit (preceding session/turn) that found it was first-attempt provider for only 6 of 22 leagues, with API-Football already providing complete, proven fallback coverage everywhere. Absolute requirements: do not redesign the settlement engine, do not split `update_dataframe()`, do not introduce a second provider, do not change business logic — only remove football-data.org and simplify. Do not push. Do not execute settlement. Do not execute generation.

---

## Work Completed

- **Task 1 (`update_results.py`):** removed `classify_fd_status()`, `should_use_api_football_fallback()`, `http_get_json_football_data()`, `fetch_matches_for_league_date()`, `_respect_fd_api_spacing()`, `_fd_last_api_call_ts`, all `FD_*` constants (`FD_MAX_RETRIES`, `FD_BASE_SLEEP`, `FD_CALL_MIN_INTERVAL`, `FD_FINISHED_STATUS`, `FD_IN_PROGRESS_STATUS`, `FD_NON_PLAYED_STATUS`, `FD_SUSPENDED_INTERRUPTED_STATUS`, `FD_VOID_REASON_BY_STATUS`), and `API_TOKEN` (the `FOOTBALL_DATA_API_KEY` read). `make_shared_runtime_state()` no longer carries `fd_matches_cache`/`blocked_fd_leagues_seen`.
- **Task 2 (routing simplification):** the ~180-line multi-branch provider-selection block inside `update_dataframe()` collapsed to one unconditional `_run_af_and_account(i, row, league_code, "API_FOOTBALL")` call per row. `_run_af_and_account()` itself — already fully generic — was **not modified**. `update_dataframe()` was **not split**. Startup gates in `run_settlement_remote()` and `main()` changed from a hard `FOOTBALL_DATA_API_KEY` check to a single hard `API_FOOTBALL_KEY` gate.
- **Task 3 (`src/league_registry.py`):** rewritten via `Write`. Removed `fd_code`/`fd_blocked` from `LeagueEntry`, `_settlement_code()`, and `BLOCKED_FOOTBALL_DATA_CODES`. Every league's internal `code` value preserved byte-for-byte (deliberate zero-behaviour-change decision — e.g. `"PL"` for premier is now an opaque historical identifier, not renamed to anything "cleaner"). `API_FOOTBALL_FALLBACK_COMPETITIONS` renamed to `API_FOOTBALL_COMPETITIONS`, built unconditionally from `af_id` (now required, not optional). All 22 leagues preserved, including MLS (`af_id=253`) and MLS Next Pro (`af_id=909`) kept fully independent.
- **Task 4 (configuration):** removed `FOOTBALL_DATA_API_KEY` from the local `.env` (untracked, gitignored per Phase 27.3), `.env.example`, and all three jobs in `.github/workflows/bot.yml` (`settlement`, `main-generation`, `topup`).
- **Task 5 (dashboard):** removed the dead 13-entry football-data.org competition-code block from `index.html`'s `LEAGUE_NORMALIZE` map (every canonical key it produced is already covered elsewhere) and the `'football-data.org'` entry from `PROVIDER_HEALTH_LABELS` (proven zero-visual-change via the existing `PROVIDER_HEALTH_LABELS[provider] || provider` fallback pattern, including for stale historical `providerHealth` records). `node --check` on the extracted script passed; `node tests/test_quant_engine_golden.js` — 285/285 passing.
- **Task 6 (repository audit):** grepped the entire repository for `football-data`, `football_data`, `FOOTBALL_DATA`, `fd_code`, `fd_blocked`, `football-data.org`, `FD provider`. Also updated `audit_settlement.py` (a standalone diagnostic script, confirmed not wired into any production entry point) to match the simplified `update_results.py` API — removed its ~90-line FD-fetch/cache/fallback block and fixed its imports/diagnostic prints. Found and disclosed, but explicitly did not fix (pre-existing, unrelated): `audit_settlement.py` imports `safe_read_manual_csv`/`MANUAL_FILE` from `update_results.py`, but neither has ever existed there — a bug predating this phase.
- **Task 7 (documentation):** updated `09_Architecture_Decisions.md` (new "Update (2026-08-02, Phase 27.4)" section on ADR-004; fixed ADR-017's status-classification matrix), `01_Architecture.md`, `02_Data_Flow.md`, `04_Backend.md`, `03_Dashboard.md`, `00_Project_Context.md`, `06_Roadmap.md`, `PROJECT_MAP.md`, `08_Change_Log.md` (new summary row + full Phase 27.4 section), `07_Current_Status.md` (header, new narrative, Next Priorities item 18), and this handover. `05_Known_Issues.md` reviewed and deliberately left unmodified — its one remaining mention (SETTLEMENT-1) is an accurate historical description of a Phase 26.18 fix, written when football-data.org was still in use; rewriting historical entries to match current architecture would misrepresent what actually shipped at the time.
- **Task 8 (testing):** `tests/test_void_policy.py` — deleted `test_fd_suspended_after_48h_remains_unresolved()` (tested the removed `fetch_matches_for_league_date()`; fully redundant with an existing AF-equivalent test) and stripped the FD-specific assertions from `test_suspended_interrupted_classification_falls_through_to_scheduled_unknown()`. `tests/test_mls_league_routing.py` — renamed `API_FOOTBALL_FALLBACK_COMPETITIONS` → `API_FOOTBALL_COMPETITIONS` (4 occurrences). Full suite re-run repeatedly through the session; final run: **418/418 passing**.
- **Task 9/10 (metrics + safety audit):** compiled below and in the session's final report.
- Reverted stray regenerated `__pycache__`/`.pyc` files (build artifacts, unrelated to this phase's diff) before finalizing.

---

## Files Modified

| File | Reason for change |
|---|---|
| `update_results.py` | Removed all football-data.org functions/constants/caches; collapsed provider-routing block to a single API-Football call; simplified startup gates. Net -447 lines. |
| `src/league_registry.py` | Removed `fd_code`/`fd_blocked`/`BLOCKED_FOOTBALL_DATA_CODES`; renamed `API_FOOTBALL_FALLBACK_COMPETITIONS` → `API_FOOTBALL_COMPETITIONS`; `af_id` now required. Registry `code` values preserved byte-for-byte. |
| `audit_settlement.py` | Diagnostic-only script (not wired into production) updated to match the simplified `update_results.py` API; removed its own FD-fetch block. |
| `.env.example` | Removed `FOOTBALL_DATA_API_KEY`; updated provider comment. |
| `.github/workflows/bot.yml` | Removed `FOOTBALL_DATA_API_KEY` secret reference from all three jobs. |
| `index.html` | Removed dead `LEAGUE_NORMALIZE` FD-code block and `PROVIDER_HEALTH_LABELS` FD entry — both proven zero-visual-change. |
| `tests/test_void_policy.py` | Deleted 1 FD-only test (redundant); stripped FD assertions from 1 shared test. |
| `tests/test_mls_league_routing.py` | Renamed import to match `league_registry.py`'s new constant name. |
| `docs/09_Architecture_Decisions.md` | ADR-004 Phase 27.4 update section; ADR-017 status matrix fix. |
| `docs/01_Architecture.md`, `docs/02_Data_Flow.md`, `docs/04_Backend.md` | Removed football-data.org component/flow/API descriptions; updated to single-provider architecture. |
| `docs/03_Dashboard.md` | Updated `providerHealth`/settlement-message descriptions for the sole-provider state. |
| `docs/00_Project_Context.md`, `docs/06_Roadmap.md`, `docs/PROJECT_MAP.md` | Fixed dead references (`get_match_result_fd()`, `BLOCKED_FOOTBALL_DATA_CODES`, FD env var, FD-based league lists/rate limits). |
| `docs/07_Current_Status.md` | Header/date updated; new Phase 27.4 narrative; new Current Development entry; Next Priorities item 18 added. |
| `docs/08_Change_Log.md` | New summary row + full "Phase 27.4" section. |

**New files:** `docs/handovers/handover-2026-08-02-phase-27.4.md` (this file).

**No files deleted.** `audit_settlement.py` was simplified in place (remains independently useful as a diagnostic tool, not wired into production).

No production runtime data files were modified — confirmed via `git diff --stat` against `cloud_state.json`, `picks_history.csv`, `picks_hoje_simplificado.csv`, `picks_hoje_github.csv`, `picks_over25.csv`, `picks_btts.csv`, `fixtures_today.csv`, `sent_state.json`, `team_alias_cache.json`, `manual_bets.csv`, `league_stats.csv`, and `data_raw/*.csv` by exact name — all show zero diff.

---

## Documentation Updated

- `docs/09_Architecture_Decisions.md` (ADR-004 Phase 27.4 update, ADR-017 fix)
- `docs/01_Architecture.md`
- `docs/02_Data_Flow.md`
- `docs/04_Backend.md`
- `docs/03_Dashboard.md`
- `docs/00_Project_Context.md`
- `docs/06_Roadmap.md`
- `docs/PROJECT_MAP.md`
- `docs/07_Current_Status.md`
- `docs/08_Change_Log.md`
- `docs/05_Known_Issues.md` — reviewed, **deliberately not modified** (see rationale above)

---

## Architectural Decisions

No new ADR. ADR-004 ("The League Registry Is the Only Location Where League Metadata Is Maintained") gained an "Update (2026-08-02, Phase 27.4)" section documenting: the audit finding that football-data.org was never architecturally required; the complete list of removed functions/constants; the registry `code`-field preservation decision; the routing simplification to one unconditional path; explicit confirmation `update_dataframe()` was not split; and the deliberate decision to leave generic dual-shape parser functions untouched. ADR-017's status-classification matrix was corrected to remove football-data.org's now-nonexistent statuses.

---

## Current Project State

**Complete, tested, and committed locally — not pushed.**

API-Football is now the sole production result provider for both generation and settlement. The bot continues to run in production unaffected by this phase (no production data touched, no generation or settlement executed this session). The backup subsystem (Phase 27.2/27.3) remains dormant and unaffected — no R2 credentials exist yet.

---

## Outstanding Issues

- None new in `05_Known_Issues.md`.
- **Pre-existing, unrelated, disclosed not fixed:** `audit_settlement.py` imports `safe_read_manual_csv`/`MANUAL_FILE` from `update_results.py`, neither of which has ever existed there — confirmed via grep this predates Phase 27.4. Out of scope for this phase (the script is diagnostic-only, not wired into production).
- **Carried over from Phase 27.3, still urgent, still unrelated:** `FOOTBALL_DATA_API_KEY`/`API_FOOTBALL_KEY` remain exposed in git history (untracked in Phase 27.3, not rewritten). Removing `FOOTBALL_DATA_API_KEY` from active configuration this phase does not undo its prior exposure — both keys should still be rotated.

---

## Validation Performed

- `python -m pytest -q` (full suite) — **418/418 passing** (419 minus the 1 deleted redundant FD test), zero regressions.
- `node tests/test_quant_engine_golden.js` — 285/285 passing (QuantEngine untouched, confirmed via `git diff --stat -- index.html` showing only the two targeted removals).
- `node --check` on the extracted `<script>` block of `index.html` — syntax OK.
- Repository-wide grep for `football-data`, `football_data`, `FOOTBALL_DATA`, `fd_code`, `fd_blocked`, `football-data.org`, `FD provider` — all dead references in source/config/tests removed; remaining documentation references are explanatory prose describing the removal itself, or historical Change Log/handover entries left untouched by design.
- `git diff --stat` against every named production data file — zero diff on all of them.
- `git status -s` reviewed in full before finalizing; stray regenerated `.pyc` files reverted (not part of this phase's diff).

---

## Remaining Work

- Await explicit approval to push this session's commit (to be created locally on top of `514677e8`, not yet pushed).
- Separately and still pending from Phase 27.3: rotate the two exposed API keys.
- No follow-up work specific to this phase — the architectural simplification is complete. A future session could consider Roadmap TD-1 (splitting `update_results.py` into modules), now a smaller undertaking with football-data.org's code removed, but this was explicitly out of scope for Phase 27.4.

---

## Next Recommended Task

Await approval to push this session's commit. Separately and urgently: rotate `FOOTBALL_DATA_API_KEY`/`API_FOOTBALL_KEY` at their respective providers — independent of the push decision, carried over from Phase 27.3.

---

## Notes for the Next Session

- API-Football is now the only external result-provider credential (`API_FOOTBALL_KEY`) referenced anywhere in the repository. Any future work touching settlement or fixture fetching should assume single-provider architecture — there is no fallback path to reason about anymore.
- The league registry's `code` field values (e.g. `"PL"`, `"PPL"`) are historical, opaque identifiers with no remaining connection to football-data.org — do not attempt to "clean them up" without checking every consumer first; they are load-bearing for settlement routing exactly as before.
- `_run_af_and_account()` and `try_update_row_via_api_football()` in `update_results.py` are now the entire result-resolution path — there is no second branch to keep in sync.

---

## End-of-Session Checklist

- [x] Code committed — **locally only, NOT pushed** (explicit instruction; commit created after this handover is saved)
- [x] `07_Current_Status.md` updated
- [x] `05_Known_Issues.md` reviewed — no entry needed
- [x] `08_Change_Log.md` updated (new Phase 27.4 section)
- [x] `09_Architecture_Decisions.md` updated (ADR-004 update, ADR-017 fix — no new ADR)
- [ ] `06_Roadmap.md` updated — reviewed and fixed (2 dead references), no priority changes
- [x] This handover document filled and saved
- [x] Next session can start from "Next Recommended Task" without reading chat history
