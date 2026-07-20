# Session Handover

---

## Session Information

```
Date:     2026-07-20 – 2026-07-21
Branch:   main
Commit:   Not yet committed — all changes below are in the working tree, pending explicit user approval before commit/push (per this session's instructions)
```

---

## Session Objective

Implement a safe, architecture-consistent fix for a production settlement failure: every current senior MLS bet (bot and manual) was stuck unsettled because `src/league_registry.py` queried API-Football's MLS Next Pro competition instead of senior MLS. A prior read-only investigation established the root cause. An initial implementation pass fixed the settlement collision but misread the generation requirement (treating MLS Next Pro as settlement-only); this was corrected within the same still-uncommitted session — the final architecture makes MLS and MLS Next Pro two fully independent, first-class leagues throughout the entire pipeline.

---

## Work Completed

- **Root cause confirmed and settlement routing fixed.** `src/league_registry.py`'s `"mls"` entry had `af_id=909` (`af_name="MLS Next Pro"`) while `config.json`'s `api_football.league_ids.mls` correctly held `253` — a two-source divergence unique to MLS among all 21 leagues at the time (verified via an automated comparison of every league's registry `af_id` against its `config.json` value). Restored `"mls"` to `af_id=253`, `af_name="Major League Soccer"`.
- **MLS Next Pro established as a distinct, fully first-class league (corrected mid-session).** New `REGISTRY` entry `"mls_next_pro"` (`name="MLS Next Pro"`, `af_id=909`, `season_model="calendar"`). An initial pass left it deliberately absent from `config.json` (settlement-routing only); this was wrong — generating MLS Next Pro picks was always intentional, the defect was only that it shared MLS's canonical identity. Corrected by registering `mls_next_pro` everywhere a generating league needs to be registered:
  - `config.json`: `leagues.mls_next_pro` and `api_football.league_ids.mls_next_pro = 909`.
  - `fetch_oddsapi_fixtures.py`: `DEFAULT_LEAGUE_IDS`, `LEAGUE_INFO_EXT`, and the `summer_leagues` calendar-season set in `season_for_date()`.
  - `main.py`: `NON_EU_TOPUP_LEAGUES` (23:00 UTC late-odds top-up run now covers it, same as MLS).
  - `fetch_historical.py`: `LEAGUE_INFO` and `summer_leagues` (for future manual history refreshes).
  - `data_raw/mls_next_pro.csv`: a **real** history file (535 finished matches, seasons 2025–2026) fetched live from API-Football — without this, `process_league_fixtures()` would silently skip the league every day regardless of every config change above.
- **Historical collision audit, minimal migration (unchanged conclusion, re-verified after activating generation).** All 21 `"MLS"`-labelled `picks_history.csv` rows and 20 `"mls"`-liga `cloud_state.json["manualBets"]` entries individually inspected. 28 already-settled rows (14+14, genuine reserve-team fixtures) left untouched — activating MLS Next Pro generation does not change this conclusion; already-settled data is still not mass-migrated. Exactly one unresolved, deterministically-identifiable row (`picks_history.csv`, `"Huntsville City vs Crown Legacy"`, 2026-06-21 — both clubs exist only in MLS Next Pro) relabelled `MLS` → `MLS Next Pro`. Its `cloud_state.json["localEdits"]` key was re-keyed (`...|mls|...` → `...|mls_next_pro|...`) to keep its existing `resultadoManual: "P"` bridge (ADR-015) from being orphaned — required because `index.html`'s `LEAGUE_NORMALIZE` mirror had no `"mls next pro"` entry and would otherwise compute a different pick key than the CSV's new `Liga` string. 6 unresolved manual bets + 3 unresolved bot-pick rows already correctly carried senior-MLS identity and needed no data change.
- **Removed the dangerous fixture-generation fallback (unchanged from the initial pass).** `fetch_oddsapi_fixtures.py::fetch_fixtures_for_league_date()` no longer retries a zero-fixture response via `search_league_id_by_api()` — a configured canonical ID (now present for **both** MLS and MLS Next Pro) is authoritative; zero fixtures for a date is logged, never substituted, for either league. `search_league_id_by_api()` left defined but disconnected, with a comment against reconnecting it.
- **Fixed manual kickoff display.** `getManualRowsMerged()` never propagated `kickoffUTC` onto its merged row objects at all. Fixed by adding `kickoffUTC: cleanString(b.kickoffUTC || '')` to the merged local-row object, plus a new `resolveManualKickoff(b)` helper (`b.kickoffUTC || findFixtureKickoff(...)`) used at all four manual-kickoff call sites (`getPendingRows()`, `getLiveRows()`, `getPendingCount()`). Bot-row kickoff handling untouched. Backend settlement was never affected (it already read `bet.get('kickoffUTC')` directly) — display/classification-only gap.
- **Dashboard distinction confirmed.** `index.html`'s `LEAGUE_NORMALIZE` mirror was already fixed (previous pass) so `"MLS"` and `"MLS Next Pro"` normalize to different internal codes (`mls` / `mls_next_pro`) and never collapse. A dedicated Playwright script confirmed this live, plus that both leagues appear as two distinct entries in the data-driven league filter list.
- **End-to-end pipeline proof, live and read-only.** (1) Fixture-fetch independence: called `fetch_fixtures_for_league_date()` live for both league IDs across 7 consecutive dates — confirmed zero-MLS-fixtures does not disable MLS Next Pro (2026-07-22: MLS=0, MLS Next Pro=1), and both leagues have fixtures simultaneously with zero team overlap (2026-07-23: 15 MLS + 2 MLS Next Pro; 2026-07-26: 14 + 7). (2) Pick-generation independence: called `process_league_fixtures()` directly (no CSV writes, no upload, no Telegram) for one real fixture per league on the same date — both independently produced real Poisson-lambda-based, positive-edge pick candidates from their own genuine `data_raw/*.csv` history.
- **Postponed-match assessment (read-only, live API, no settlement write, unchanged from the initial pass).** Under the corrected `af_id=253` routing: St. Louis City vs Sporting Kansas City → `FT`, 3-2 (Over 2.5 → W). Nashville SC vs Atlanta United FC → `FT`, 1-0 (Over 2.5 → L). Los Angeles Galaxy vs Los Angeles FC → `FT`, 0-3 (Over 2.5 → W). Chicago Fire vs Vancouver Whitecaps → not found in API-Football's schedule within a ±10-day window of its stored kickoff — consistent with genuine postponement; `update_dataframe()` confirmed by code inspection to have no path that could settle this incorrectly. No postponed-fixture lifecycle implemented — assessed and explicitly deferred as a separate follow-up.
- **Regression tests.** `tests/test_mls_league_routing.py` (23 tests — routing, `get_api_football_league_id()`, bot/manual routing parity for both leagues, independent/simultaneous fixture-fetch mocks, generation-config presence for `mls_next_pro`, topup-set membership, non-MLS-league regression guard) and `tests/test_fixture_fetch_no_substitution.py` (3 tests) — both new this session. 2 tests added to `tests/test_season_model.py` (`MLS_ID` corrected 909→253, `MLS_NEXT_PRO_ID` added). One test that had (incorrectly) asserted `mls_next_pro`'s absence from generation config was replaced with one asserting its active presence. Full existing Python suite: **216/216 passing**.
- **Documentation.** ADR-004's Update section rewritten to describe the final, correct architecture (both leagues independent and actively generating) rather than the intermediate settlement-only framing, including an explicit note about the mid-session requirement correction. `05_Known_Issues.md` SETTLEMENT-3 corrected. `08_Change_Log.md`'s Phase 26.42 section substantially rewritten with the corrected fix description, the live end-to-end verification evidence, and the requirement-clarification note. `07_Current_Status.md`, `04_Backend.md` §8, and `PROJECT_MAP.md` all corrected from "21 leagues + 1 settlement-only entry" to "22 leagues, all actively generating."

---

## Files Modified

| File | Reason for change |
|---|---|
| `src/league_registry.py` | Restored `"mls"` to `af_id=253`; added distinct, fully active `"mls_next_pro"` entry (`af_id=909`) |
| `config.json` | Added `mls_next_pro` to `leagues` and `api_football.league_ids` (909) — makes it an actively-generating league |
| `fetch_oddsapi_fixtures.py` | Added `mls_next_pro` to `DEFAULT_LEAGUE_IDS`, `LEAGUE_INFO_EXT`, `summer_leagues`; removed the zero-fixture silent-substitution retry in `fetch_fixtures_for_league_date()` |
| `fetch_historical.py` | Added `mls_next_pro` to `LEAGUE_INFO` and `summer_leagues`, for future manual history refreshes |
| `main.py` | Added `mls_next_pro` to `NON_EU_TOPUP_LEAGUES` |
| `data_raw/mls_next_pro.csv` | New — 535 real finished matches (seasons 2025–2026), fetched live via `fetch_historical.py`, required for Poisson lambda projection |
| `picks_history.csv` | One row (`Huntsville City vs Crown Legacy`, line 42) relabelled `MLS` → `MLS Next Pro` — Liga column only, no result data touched |
| `cloud_state.json` | Re-keyed the matching `localEdits` entry (`...|mls|...` → `...|mls_next_pro|...`) to preserve its manual-result bridge |
| `index.html` | Added `kickoffUTC` propagation to `getManualRowsMerged()`'s local rows; new `resolveManualKickoff()` helper used in `getPendingRows()`/`getLiveRows()`/`getPendingCount()`; `LEAGUE_NORMALIZE` gained `mls_next_pro` entries |
| `tests/test_season_model.py` | `MLS_ID` corrected 909→253; `MLS_NEXT_PRO_ID` added; test functions for both |
| `tests/test_mls_league_routing.py` | New/rewritten — 23 tests covering registry routing, independent generation, simultaneous fixtures, topup inclusion, manual-bet routing for both leagues |
| `tests/test_fixture_fetch_no_substitution.py` | New — 3 tests covering the removed fallback |
| `docs/09_Architecture_Decisions.md` | ADR-004 Update section rewritten for the corrected, final architecture |
| `docs/05_Known_Issues.md` | SETTLEMENT-3 corrected; DASHBOARD-6 unchanged from the initial pass |
| `docs/08_Change_Log.md` | Phase 26.42 section substantially rewritten |
| `docs/07_Current_Status.md` | Header, Current Development narrative, League registry line, Pick generation line corrected to "22 leagues, both active" |
| `docs/04_Backend.md` | §8 League Registry subsection rewritten; "21 leagues" counts updated to 22 |
| `docs/PROJECT_MAP.md` | "21 + settlement-only" framing corrected to "22 leagues, all active" in three places |

---

## Documentation Updated

- `docs/09_Architecture_Decisions.md`
- `docs/05_Known_Issues.md`
- `docs/08_Change_Log.md`
- `docs/07_Current_Status.md`
- `docs/04_Backend.md`
- `docs/PROJECT_MAP.md`

`docs/03_Dashboard.md` (kickoff-display sections, from the initial pass — still accurate, no further change needed), `docs/01_Architecture.md`, `docs/02_Data_Flow.md`, `docs/06_Roadmap.md`, and `docs/00_Project_Context.md` reviewed and found not to need (further) changes.

---

## Architectural Decisions

**ADR-004 extended, not superseded; no new ADR.** The MLS/MLS Next Pro collision was a violation of ADR-004's own single-source-of-truth principle; the fix restores compliance. The Update section now states the final, correct principle: a supported competition has an explicit canonical identity and authoritative provider mapping; a registry entry alone gives settlement identity, and a matching `config.json` entry is what activates generation — both were added for `mls_next_pro`. A configured canonical league ID must never be silently substituted for a different competition on a zero-result response. Both points remain the same "no two diverging sources of truth" reasoning ADR-004 (and ADR-001) already establish.

---

## Current Project State

**Stable — fix implemented, corrected, tested, and documented; not yet committed.** All changes are in the working tree per this session's explicit instruction to wait for approval before committing or pushing. The full Python test suite (216 tests) and the relevant Playwright regression scripts pass with zero regressions. Both MLS and MLS Next Pro are confirmed, via live data, to independently and simultaneously fetch fixtures and generate pick candidates.

---

## Outstanding Issues

- None newly opened. `05_Known_Issues.md`'s Open Issues section remains empty.
- A residual, explicitly-deferred gap: no dedicated postponed-fixture lifecycle exists (Chicago Fire vs Vancouver Whitecaps degrades safely to "stays open" but a fixture rescheduled far from its original date may not be automatically rediscovered by the current date-window search). Recommended as a separate follow-up phase.
- A second, minor residual gap: the Manual Bets tab's own row table (`renderManualBets()`) still calls `findFixtureKickoff()` directly rather than `resolveManualKickoff()` — same latent weakness as the fixed Pending/Live Center gap, left out of scope since the task named only those two pages.
- `tools/analyse_edge.py` (a standalone, non-scheduled calibration-research script) was deliberately not extended to cover `mls_next_pro` — it already covers only a hand-picked subset of leagues, not full coverage, so this is not a gap relative to its existing scope.

---

## Validation Performed

- Full Python test suite: 216/216 passing (`python -m pytest tests/ -v`).
- Live, read-only verification that `fetch_fixtures_for_league_date()` fetches MLS (253) and MLS Next Pro (909) fully independently across 7 real dates, including a zero-MLS/nonzero-MLS-Next-Pro date and two simultaneous-fixtures dates.
- Live, read-only (no CSV/upload/Telegram side effects) verification that `process_league_fixtures()` produces real candidate picks for both leagues from their own real historical data on the same date.
- Scratchpad Playwright scripts (not committed): manual-kickoff-display script (7 checks, all passing) and a new dashboard-league-distinction script (8 checks, all passing — confirms normalization/pick-keys/filter-list never collapse the two leagues).
- Full pre-existing manual-bet-lifecycle Playwright suite (14 checks) and render-dispatcher sanity check re-run against the modified `index.html` — all passing, zero page errors, zero regressions.
- No live `/run-settlement` call and no live `main.py`/`run_topup.py` execution was made — no production CSV, `cloud_state.json` (beyond the one deliberate historical re-key), GitHub, or Telegram side effects occurred this session.

---

## Remaining Work

- Await explicit user approval, then commit and push.
- After deployment, monitor the next scheduled generation run (17:00 UTC) to confirm MLS Next Pro picks are actually generated and committed under their correct `MLS Next Pro` identity.
- After deployment, monitor the next scheduled or on-demand settlement run to confirm the four known senior-MLS cases (and the two additional rejected-but-settling bets) settle with the exact results this session's read-only verification predicted.
- Consider a dedicated follow-up phase for postponed-fixture lifecycle handling if Chicago Fire vs Vancouver Whitecaps (or a similar case) recurs.

---

## Next Recommended Task

Commit and push this fix (pending user approval), then monitor the next generation run to confirm MLS Next Pro picks are generated under the correct identity, and the next settlement run to confirm the four known MLS cases resolve as predicted.

---

## Notes for the Next Session

- The fix intentionally does **not** touch the shared settlement engine (`update_dataframe()`), ADR-002/ADR-009's bot/manual parity, QuantEngine, or the H1/H2/H3 render dispatcher — all confirmed unaffected by design and by regression testing.
- `mls_next_pro` is now a real, fully active, permanent league — registered in both `src/league_registry.py` and `config.json`, with its own real `data_raw/mls_next_pro.csv` history file. It will generate picks starting the next scheduled `main.py` run.
- A mid-session correction happened here: an initial implementation registered `mls_next_pro` for settlement purposes only, deliberately excluded from generation. This was wrong and was corrected before commit — see ADR-004's Update section and this handover for the reasoning. If similar "should X also generate picks?" ambiguity comes up for a future league, confirm with the user before assuming settlement-only is sufficient.
- The Playwright test scripts used this session live only in the scratchpad directory (`C:\Users\jjpit\AppData\Local\Temp\claude\...\scratchpad`), per this project's established convention — none are part of the committed repository.
- Do not reconnect `search_league_id_by_api()` as an automatic fallback in `fetch_oddsapi_fixtures.py` without first re-reading ADR-004's update section — that is exactly the mechanism that caused this incident.

---

## End-of-Session Checklist

- [ ] Code committed and pushed — **intentionally not done; awaiting explicit user approval per this session's instructions**
- [x] `07_Current_Status.md` updated
- [x] `05_Known_Issues.md` updated (SETTLEMENT-3 corrected, DASHBOARD-6 unchanged, both Resolved)
- [x] `08_Change_Log.md` updated (Phase 26.42 rewritten)
- [x] `09_Architecture_Decisions.md` updated (ADR-004 Update section rewritten)
- [ ] `06_Roadmap.md` updated — not touched; no roadmap-level priority changed this session
- [x] This handover document rewritten and saved
- [x] Next session can start from "Next Recommended Task" without reading chat history
