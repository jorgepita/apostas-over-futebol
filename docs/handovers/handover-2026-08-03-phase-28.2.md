# Session Handover

---

## Session Information

```
Date:     2026-08-03
Branch:   phase-26.46-exposure-warning-current-production
Commit:   ee580a37 (base, already on origin/main) — this session's Phase 28.2 changes are NOT yet committed, pending explicit approval
```

---

## Session Objective

Phase 28.2 — integrate four requested leagues (Switzerland Super League, Spain LaLiga Hypermotion / Segunda División, France Ligue 2, Portugal Liga Portugal 2 "Meu Super") as full first-class production leagues, following the documented `04_Backend.md` "Adding a new league" checklist. No shortcuts, no duplicated code, no temporary solutions, maintain backwards compatibility. Do not commit, do not push — await explicit approval.

---

## Work Completed

- **Discovery:** live API-Football `/leagues` queries found France Ligue 2 already fully integrated (`franca2`, af_id=62, registered since before this phase, `data_raw/franca2.csv` with 549 rows). Audited it for hidden gaps (dashboard, analytics, backups, standings) — none found — and did not re-add it, per explicit user confirmation, to avoid a duplicate-source-of-truth violation of ADR-004.
- Confirmed IDs for the three genuinely new leagues via live API-Football queries: Switzerland Super League (`suica`, af_id=207), Spain Segunda División (`espanha2`, af_id=141), Portugal Liga Portugal 2 (`portugal2`, af_id=95) — all `"european"` season model.
- Display names: confirmed with the user to use each competition's stable, sponsor-free name ("Segunda División", "Liga Portugal 2") rather than the sponsor-branded names in the original request ("LaLiga Hypermotion", "Liga Portugal 2 Meu Super"), matching this project's existing convention.
- Registered all 3 leagues in `src/league_registry.py`, `config.json` (`leagues`, `api_football.league_ids`, and a new `historical.seasons_by_league` override — needed because the "current" 2026/27 season had ~0 finished matches at bootstrap time).
- Discovered and closed two undocumented-but-universally-followed integration steps: `fetch_oddsapi_fixtures.py`'s `DEFAULT_LEAGUE_IDS` fallback dict, and `historical.seasons_by_league` — both now added to the `04_Backend.md` checklist.
- Built real `data_raw/{suica,espanha2,portugal2}.csv` history files via `fetch_historical.py` against live API-Football data (seasons 2024+2025; 459/935/615 rows) — force-added since `data_raw/*.csv` is gitignored by pattern (existing league files are tracked exceptions).
- Added `LEAGUE_NORMALIZE` entries to `index.html` for dashboard recognition; confirmed filter dropdowns need no change (dynamically populated from data).
- Extended 3 cosmetic, debug-log-only "EU leagues" set literals (`main.py` ×2, `src/market_rules.py`, `src/pick_generation.py`) for consistency — confirmed by reading every call site that none gate real filtering/staking/generation logic.
- Verified the full pipeline end-to-end against real code paths (not re-implementations): Poisson lambda calculation against the new history data, settlement league-ID/season-model resolution, manual-bet display-name resolution, live `/fixtures` and `/odds` availability, `league_stats.py` analytics aggregation, and dashboard `normalizeLeagueCode()` — all confirmed working, zero per-league special-casing found anywhere.
- Added `tests/test_phase28_new_leagues.py` (12 new tests). Full suite: 430/430 passing. QuantEngine golden vectors: 285/285 unchanged.
- Updated documentation: `00_Project_Context.md`, `01_Architecture.md`, `04_Backend.md`, `PROJECT_MAP.md`, `09_Architecture_Decisions.md` (ADR-004 update), `07_Current_Status.md`, `08_Change_Log.md`, this handover.

---

## Files Modified

| File | Reason for change |
|---|---|
| `src/league_registry.py` | Added 3 `LeagueEntry` rows (`suica`, `espanha2`, `portugal2`). |
| `config.json` | Added the 3 leagues to `leagues`/`api_football.league_ids`; new `historical.seasons_by_league` section. |
| `fetch_oddsapi_fixtures.py` | Added the 3 leagues to `DEFAULT_LEAGUE_IDS` (discovered required fallback dict). |
| `fetch_historical.py` | Added 3 `LEAGUE_INFO` entries used to build the history CSVs. |
| `data_raw/suica.csv`, `data_raw/espanha2.csv`, `data_raw/portugal2.csv` | New — real historical match data (2024+2025 seasons) for the Poisson model. |
| `index.html` | Added `LEAGUE_NORMALIZE` canonical + display-name entries for the 3 new leagues. |
| `main.py` | Extended 2 debug-only "EU leagues" trace sets (cosmetic, log-verbosity only). |
| `src/market_rules.py` | Extended 1 debug-only "EU leagues" set (cosmetic). |
| `src/pick_generation.py` | Extended 1 debug-only "EU leagues" set (cosmetic). |
| `tests/test_phase28_new_leagues.py` | New — 12 regression tests covering registry, config, settlement routing, and data files for the 3 new leagues. |
| `docs/00_Project_Context.md`, `docs/01_Architecture.md`, `docs/04_Backend.md`, `docs/PROJECT_MAP.md` | League counts (22→25), league lists, updated "Adding a new league" checklist, API request-volume math. |
| `docs/09_Architecture_Decisions.md` | New "Update (2026-08-03, Phase 28.2)" section on ADR-004. |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | New Phase 28.2 narrative/summary entries. |

**No production runtime data file was modified** — `cloud_state.json`, `picks_history.csv`, `picks_hoje*.csv`, `picks_over25.csv`, `picks_btts.csv`, `fixtures_today.csv`, `sent_state.json`, `team_alias_cache.json`, `league_stats.csv`, and every pre-existing `data_raw/*.csv` show zero diff.

---

## Documentation Updated

- `docs/00_Project_Context.md`
- `docs/01_Architecture.md`
- `docs/04_Backend.md`
- `docs/PROJECT_MAP.md`
- `docs/09_Architecture_Decisions.md` (ADR-004 update — no new ADR)
- `docs/07_Current_Status.md`
- `docs/08_Change_Log.md`
- `docs/05_Known_Issues.md` — reviewed, no entry needed (no open issue found or created)
- This handover

---

## Architectural Decisions

No new ADR. ADR-004 ("The League Registry Is the Only Location Where League Metadata Is Maintained") gained an "Update (2026-08-03, Phase 28.2)" section documenting: the Ligue 2 duplicate-request finding and audit; the three new leagues' identifiers and season model; the two previously-undocumented integration steps (`DEFAULT_LEAGUE_IDS`, `historical.seasons_by_league`) discovered and now closed; and the deliberate decision not to populate the confirmed-dead `LEAGUE_INFO_EXT` dict.

---

## Current Project State

**Complete, tested, and validated — not committed, pending explicit approval** (per the session's instructions: "Do not commit. Do not push. Await explicit approval.").

---

## Outstanding Issues

- None new in `05_Known_Issues.md`.
- No regressions found in any existing feature.

---

## Validation Performed

- `python -m pytest -q` (full suite) — **430/430 passing** (418 pre-existing + 12 new), zero regressions.
- `node tests/test_quant_engine_golden.js` — 285/285 passing (QuantEngine untouched).
- `node --check`-equivalent syntax validation on the extracted `<script>` block of `index.html` — OK.
- Live, real API-Football queries (`/leagues`, `/fixtures`, `/odds`) for all 3 new leagues — confirmed correct IDs, season coverage, real upcoming fixtures, and odds availability timing.
- `compute_lambdas()` run directly against the new `data_raw/espanha2.csv` — produced sane Poisson lambda values.
- `update_results.get_api_football_league_id()`, `api_football_season_from_date()`, `_resolve_liga_display_name()` — the real settlement functions — called directly for all 3 leagues, all resolved correctly.
- `src/league_stats.py::update_league_stats()` run against a synthetic history file (scratch-only) containing rows for all 3 new leagues — correct, generic aggregation confirmed.
- Real `index.html` booted (served over a temporary local HTTP server, all data fetched live from production Railway/GitHub URLs) with `normalizeLeagueCode()` checks for all 3 new leagues — 7/7 assertions passed, zero JS console errors, no layout regression (screenshot-verified).
- `git status`/`git diff --stat` confirmed zero diff on every production runtime data file.

---

## Remaining Work

- Await explicit approval to commit and push.
- The three new leagues will start contributing real picks once the next scheduled generation run (17:00 UTC) processes them — no further action needed, they're already correctly wired into `config.json["leagues"]`, which the main generation loop reads unconditionally.
- Odds for the Spain/Portugal fixtures checked during validation were not yet posted (pre-season timing, ~1-2 weeks before kickoff) — expected to populate naturally as kickoff approaches; the existing zero-odds filter (generic, no per-league logic) already handles this.

---

## Next Recommended Task

Await approval to commit. After committing, monitor the first live 17:00 UTC generation run to confirm the 3 new leagues produce picks (or correctly produce none, if no fixture clears the edge/odds filters that day) exactly like every other league — no special action should be required.

---

## Notes for the Next Session

- France Ligue 2 was requested in this phase but found already fully integrated before this phase began — do not re-investigate it as if it were new.
- `data_raw/*.csv` is gitignored by pattern (`.gitignore:17`); every tracked file in that directory (old and new) is a deliberate `git add -f` exception. Don't be alarmed that `git status` doesn't show new `data_raw/*.csv` files as untracked-and-ignored — they were force-added and are already staged.
- The `DEFAULT_LEAGUE_IDS` dict in `fetch_oddsapi_fixtures.py` and `config.json["historical"]["seasons_by_league"]` are now part of the documented "Adding a new league" checklist (`04_Backend.md`) — a gap found during this phase's audit that had been silently followed correctly for every prior league addition but never written down.
- `the_odds_api`/`sport_keys` in `config.json` is dead configuration (zero Python references, confirmed via repository-wide grep; `mls_next_pro` — a fully active league — has no entry there either). Do not add new leagues to it; do not treat its absence as a gap.

---

## End-of-Session Checklist

- [ ] Code committed and pushed — **NOT done, per explicit instruction: await approval**
- [x] `07_Current_Status.md` updated
- [x] `05_Known_Issues.md` reviewed — no entry needed
- [x] `08_Change_Log.md` updated (new Phase 28.2 section)
- [x] `09_Architecture_Decisions.md` updated (ADR-004 update — no new ADR)
- [ ] `06_Roadmap.md` — not reviewed this session (no roadmap-priority change resulted from this phase)
- [x] This handover document filled and saved
- [x] Next session can start from "Next Recommended Task" without reading chat history
