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

Design and implement a single shared Quantitative Engine consumed by both the Python bot (`main.py` → `src/pick_generation.py`) and the JavaScript Manual Bet Scout (`index.html`), so both compute probability/edge/confidence/Kelly/fair-odds from one verified source instead of two independently-maintained implementations. Explicitly not a merge of the two decision systems — Score/Opinion/Recommendation logic must stay outside the engine, as consumers of its output.

This followed directly from an earlier investigation this session that found a claimed "the Edge Engine exists but is not connected to production" conclusion (attributed to a prior audit not recorded anywhere in this repository's documentation) did not match the actual codebase — production's own edge computation (`src/calculations.py`) was already fully integrated. That investigation is documented in this session's conversation but produced no repository change of its own; this phase is the real, separately-scoped architecture work that followed.

---

## Work Completed

- **Current-state inventory** (before any code change): traced the complete production pipeline and the Scout's JavaScript analysis path, classifying every quantitative calculation as already-shared, duplicated, differently-implemented, or missing on one side. Found a JS `mb*`-prefixed function set in `index.html`, explicitly commented `// Ported from src/calculations.py — do NOT change formulas`, that had already partially drifted (BTTS diagnostics missing, no confidence equivalent, a hardcoded `config.json` mirror).
- **Architecture evaluation**: identified that a literal single-runtime shared engine is infeasible without violating ADR-005 (no build step/framework), adding a Railway round-trip, or introducing a large new dependency (Pyodide). Presented four options plus the user's requested approach; got explicit approval for **Python canonical + verified JS mirror + golden-vector conformance testing** before writing any code.
- **Python**: added `confidence_factor()`, `fair_odds()`, `expected_value()` to `src/calculations.py`; refactored `src/market_rules.py::apply_stakes()` to call the new named `confidence_factor()` instead of an inline pandas expression (verified byte-identical before/after, both at the function level and via a full `apply_stakes()` end-to-end comparison against git `HEAD`).
- **JavaScript**: built an isolated `QuantEngine` module in `index.html` (delimited by extraction markers for testing) mirroring every Python function exactly, including a rounding-fidelity fix found only by running the conformance suite (Python's `btts_prob_diagnostics()` rounds several fields, and the *rounded* value feeds the rest of the pipeline — the JS mirror initially didn't round, which the golden-vector test caught immediately). Replaced the hardcoded `MB_HISTORY_CFG` with `loadModelConfig()`, a cached, once-per-session fetch of the real `config.json` (GitHub raw content, not Railway) with a frozen-defaults fallback. Rewrote `analyzeFixture()` to consume `QuantEngine` and extracted `classifyManualOpinion()` as a clearly separate decision-layer step.
- **Golden-vector conformance suite**: `tests/golden_vectors.json` (134 vectors generated directly from the real Python functions), `tests/test_quant_engine_golden.py` (Python), `tests/test_quant_engine_golden.js` (Node, zero dependencies, extracts and evaluates `QuantEngine` out of `index.html`). Both pass in full.
- **Validation**: full Python suite (178/178), full JS golden-vector suite (261/261 assertions), the complete existing 6-suite Playwright regression harness (5/6 fully green; `test.js` shows the same 5 pre-existing expected failures from Phase 26.28, unrelated), two new scratchpad end-to-end tests (Scout analysis with network fully blocked — 17/17; the real `config.json` happy-path fetch — 9/9).
- **Documentation**: new ADR-014, updates to `01_Architecture.md`, `03_Dashboard.md`, `04_Backend.md` (new §15), `PROJECT_MAP.md`, `07_Current_Status.md`, `08_Change_Log.md`, and this handover.

---

## Files Modified

| File | Reason for change |
|---|---|
| `src/calculations.py` | Added `confidence_factor()`, `fair_odds()`, `expected_value()` |
| `src/market_rules.py` | `apply_stakes()` now calls the named `confidence_factor()` |
| `index.html` | New `QuantEngine` module; rewritten `analyzeFixture()`; new `classifyManualOpinion()`, `loadModelConfig()`; `MB_HISTORY_CFG` → `MB_HISTORY_CFG_FALLBACK` |
| `tests/golden_vectors.json` | New — frozen conformance vectors |
| `tests/test_quant_engine_golden.py` | New — Python conformance test |
| `tests/test_quant_engine_golden.js` | New — JS conformance test (Node, no deps) |
| `tests/test_quant_engine.py` | New — unit tests for the three new Python functions |
| `docs/01_Architecture.md` | New "Shared Quantitative Engine" component; Pick Generation Flow updated; new architectural rule |
| `docs/03_Dashboard.md` | Scout's analysis step (§7 Step 2) rewritten |
| `docs/04_Backend.md` | New §15; `apply_stakes()` pseudocode updated |
| `docs/09_Architecture_Decisions.md` | New ADR-014 |
| `docs/PROJECT_MAP.md` | `calculations.py`/`tests/` entries updated |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for Phase 26.29 |
| `docs/handovers/handover-2026-07-11-quant-engine.md` | This document |

---

## Documentation Updated

- `docs/01_Architecture.md` — new component section, Pick Generation Flow trace updated, new architectural rule (§10).
- `docs/03_Dashboard.md` — Scout's quantitative analysis step rewritten to describe `QuantEngine` consumption.
- `docs/04_Backend.md` — new §15 with the full conformance-testing process and run commands; `apply_stakes()` pseudocode now shows `confidence_factor`.
- `docs/09_Architecture_Decisions.md` — new **ADR-014**, explaining why two verified implementations (not one shared runtime) is the correct architecture given ADR-005 and the no-round-trip constraint.
- `docs/PROJECT_MAP.md` — `calculations.py` and `tests/` entries updated to describe their new role.
- `docs/07_Current_Status.md`, `docs/08_Change_Log.md` — updated for Phase 26.29.
- `docs/05_Known_Issues.md` — **no change.** No issue was open for this; the phase is a proactive architecture improvement, not a bug fix, so there's nothing to move to Resolved.
- `docs/06_Roadmap.md` — **no change.** Nothing on the roadmap referenced this work or shifted priority as a result.
- `docs/00_Project_Context.md`, `docs/02_Data_Flow.md`, `docs/DEVELOPMENT_GUIDELINES.md` — **no change required.** None describe the specific quantitative-formula ownership this phase touched; `00_Project_Context.md`'s architecture summary and `02_Data_Flow.md`'s data-movement description remain accurate (no new data flow was introduced — `config.json` fetching over GitHub raw content is the same mechanism already used for picks CSVs).

---

## Architectural Decisions

**ADR-014 created** — see `docs/09_Architecture_Decisions.md`. Establishes: `src/calculations.py` is canonical; `QuantEngine` in `index.html` is a verified (not shared-source) mirror; golden-vector conformance testing is the permanent guarantee of equivalence; Score/Opinion/Recommendation/Strategy Lab logic must never be added to either engine.

---

## Current Project State

**Stable.** Bot pick generation, settlement, CSV output, and every dashboard analytical module are verified unchanged. The Scout's quantitative analysis now reads from the same formulas and the same `config.json` values as the bot.

---

## Outstanding Issues

None opened or resolved — `05_Known_Issues.md` unchanged. Pre-existing, unrelated: ST-3, ST-2 (both already on the roadmap).

---

## Validation Performed

- `python -m pytest tests/` — 178/178 passed (29 season model + 15 new QuantEngine unit tests + 134 new golden vectors).
- `node tests/test_quant_engine_golden.js` — 261/261 assertions passed.
- `apply_stakes()` end-to-end comparison: identical synthetic input run through the pre-refactor (git `HEAD`, loaded in isolation) and post-refactor code — `Stake€`/`StakeFrac` outputs byte-identical.
- Full existing 6-suite Playwright regression harness re-run: `test_opinion_validation.js` (19/19), `test_calibration_v2.js` (11/11), `test_recommendations.js` (22/22), `test_simulator.js` (26/26), `test_strategylab.js` (32/32) all pass unchanged; `test.js` shows the same 5 pre-existing expected failures from Phase 26.28 (documented there, unrelated to this phase).
- New scratchpad end-to-end tests (not committed): Scout analysis with network fully blocked (17/17 — proves the `config.json`/history fetch failure paths fall back gracefully for both O2.5 and BTTS); the real `config.json` happy-path fetch (9/9 — proves correct parsing/mapping/caching against the actual production file).
- `node --check` clean on both extracted `<script>` blocks throughout every edit.

---

## Remaining Work

- Nothing required to consider this phase complete.
- Everything else pre-existing and unrelated: ST-3, ST-2, the `01_Architecture.md` §3 refresh (Startup Flow / 60-second interval description, still on the list from a prior session), `providerHealth` threshold monitoring, rejected-bet analytics dashboard, the Phase 26.20–26.24 historical Change Log backfill (all already tracked in `07_Current_Status.md` → Next Priorities).

---

## Next Recommended Task

ST-3 (SHA conflict retry in `sync_server.py`) is next on the roadmap — this phase is complete, validated, and documented.

---

## Notes for the Next Session

- **If a formula in `src/calculations.py` is ever changed**, follow the process in `04_Backend.md` §15: change Python first, regenerate `tests/golden_vectors.json`, update `QuantEngine` in `index.html` to match, then re-run both conformance suites before considering the change complete. Skipping this reopens exactly the silent-drift risk this phase closed.
- **`QuantEngine` must stay pure.** No `state` reference, no DOM access, no `fetch()` calls, no Score/Opinion/Recommendation logic — that's what makes it extractable and testable in an isolated Node context without a browser.
- The `QUANT_ENGINE_START`/`QUANT_ENGINE_END` marker comments in `index.html` are load-bearing for `tests/test_quant_engine_golden.js` — don't remove or rename them without updating that test's extraction logic.
- The scratchpad end-to-end Playwright tests used for validation this session (`test_quant_engine_scout_e2e.js`, `test_quant_engine_config_fetch.js`) are not committed to the repository, consistent with this project's established pattern for ad hoc browser tests — only `tests/test_quant_engine_golden.py`/`.js` (the permanent conformance guard) and `tests/test_quant_engine.py` (unit tests) are committed.

---

## End-of-Session Checklist

- [x] Code committed and pushed — commit pending at time of writing, see below
- [x] `07_Current_Status.md` updated
- [x] `05_Known_Issues.md` — no change required (nothing opened or resolved)
- [x] `08_Change_Log.md` updated (Phase 26.29 entry added)
- [x] `09_Architecture_Decisions.md` updated (ADR-014 created)
- [x] `06_Roadmap.md` — no change required (nothing referenced this work; no priority shifted)
- [x] This handover document filled and saved
- [x] Next session can start from "Next Recommended Task" without reading chat history
