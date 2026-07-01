# Project Map

This document answers **"Where should I look?"** rather than "How does it work?". For architecture and implementation detail, see `01_Architecture.md`, `03_Dashboard.md`, and `04_Backend.md`.

---

## Repository Overview

```
/
├── index.html                   ← The entire frontend application
├── sync_server.py               ← Railway Flask API (the backend)
├── main.py                      ← Pick generation entry point
├── update_results.py            ← Settlement engine
├── run_main.py                  ← GitHub Actions: orchestrates main generation
├── run_topup.py                 ← GitHub Actions: top-up run for non-EU leagues
├── fetch_oddsapi_fixtures.py    ← Phase 1: fetch fixtures and odds from API-Football
├── config.json                  ← Model and runtime configuration
├── requirements.txt             ← Python dependencies
├── runtime.txt                  ← Python version for Railway
├── Procfile                     ← Railway process definition
├── CLAUDE.md                    ← Workflow instructions for Claude sessions
│
├── src/                         ← Python library modules
├── docs/                        ← Project documentation
├── data_raw/                    ← Historical match data by league (CSV)
├── tests/                       ← Automated tests
├── tools/                       ← One-off analysis and maintenance scripts
├── debug/                       ← Debug output files (not committed as data)
├── archive/                     ← Retired code and old approaches
├── cloud-api/                   ← Unused Node.js prototype (not active)
│
├── picks_history.csv            ← Settled bot picks (all time)
├── picks_hoje_github.csv        ← Today's picks for the dashboard
├── picks_hoje_simplificado.csv  ← Today's picks for settlement
├── picks_over25.csv             ← Active O2.5 picks
├── picks_btts.csv               ← Active BTTS picks
├── fixtures_today.csv           ← Fixture data produced by Phase 1
├── cloud_state.json             ← Manual bets (single source of truth)
├── sent_state.json              ← Telegram deduplication state
├── team_alias_cache.json        ← Cached team name aliases from API-Football
│
└── .github/
    └── workflows/
        └── bot.yml              ← All GitHub Actions schedules and triggers
```

---

## Directory Responsibilities

### `src/`

Python library modules used by the generation and settlement pipelines. No script that runs directly lives here — only importable modules.

| Module | Responsibility |
|---|---|
| `league_registry.py` | Single source of truth for all 21 league definitions |
| `config.py` | Reads `config.json` with defaults; exposes typed constants |
| `calculations.py` | Poisson probability calculations |
| `pick_generation.py` | Kelly staking, edge filtering, pick selection |
| `pipeline.py` | Output file writing (`save_all_outputs()`) |
| `market_rules.py` | Market result calculation (O2.5, BTTS, etc.) |
| `history.py` | Historical match data loading and processing |
| `data_loader.py` | CSV loading helpers |
| `integrations.py` | External API wrappers (football-data.org, API-Football) |
| `league_stats.py` | Per-league statistics aggregation |
| `output_utils.py` | Output formatting helpers |
| `state.py` | Shared runtime state across modules |
| `utils.py` | General utility functions |
| `runtime.py` | Runtime environment helpers |

### `docs/`

The complete documentation system. See `docs/README.md` for the reading order and update rules. The `docs/handovers/` subdirectory holds end-of-session handover documents.

### `data_raw/`

Historical match result CSVs, one file per league. These are the training data for the Poisson model. Filenames map to league names (e.g. `premier.csv`, `espanha.csv`). Modified only when new historical data is fetched.

### `tests/`

Automated tests. Currently contains `test_season_model.py` which validates season year resolution for calendar-year leagues (MLS, Nordic). Add new tests here when covering new settlement logic.

### `tools/`

One-off maintenance and analysis scripts. Not part of any automated pipeline. Run manually when needed. Examples: `analyse_edge.py`, `fetch_brazil_history.py`, `validate_brasil.py`.

### `debug/`

Temporary output files from debugging sessions. Not committed as production data. Safe to ignore and safe to delete.

### `archive/`

Retired code. Not imported or executed by any active code path. Do not edit.

### `cloud-api/`

An old Node.js prototype that predates `sync_server.py`. Not active. Not deployed. Safe to ignore.

### `.github/workflows/`

Contains `bot.yml`, the single workflow file that defines all scheduled and manually triggered GitHub Actions runs.

---

## Important Files

| File | Purpose | Typical reason to edit |
|---|---|---|
| `index.html` | The entire frontend — all HTML, CSS, and JavaScript inline | Any dashboard change |
| `sync_server.py` | Railway Flask API: `/load`, `/save`, `/run-settlement`, `/health` | Adding an endpoint, changing settlement trigger, fixing GitHub integration |
| `update_results.py` | Settlement engine: `update_dataframe()`, `run_settlement_remote()` | Settlement logic fix, new market support, API routing change |
| `main.py` | Pick generation: reads `fixtures_today.csv`, applies Poisson model, writes outputs | Pick generation logic, staking changes |
| `fetch_oddsapi_fixtures.py` | Phase 1: fetches fixtures and odds from API-Football, writes `fixtures_today.csv` | Fixture fetch logic, shortlist algorithm, API quota management |
| `run_main.py` | GitHub Actions orchestrator: runs Phase 1 then Phase 2, sends Telegram | Changing generation schedule or Telegram message format |
| `run_topup.py` | Top-up run for non-EU leagues at 23:00 UTC | Non-EU league scheduling |
| `config.json` | Model parameters: edge thresholds, Kelly fraction, bankroll, API limits | Tuning model behaviour, changing rate limits |
| `src/league_registry.py` | 21 league definitions — names, codes, season models, API IDs | Adding or modifying a league |
| `src/config.py` | Typed constants loaded from `config.json` | Adding a new configurable parameter |
| `requirements.txt` | Python dependencies | Adding or updating a dependency |
| `runtime.txt` | Python version declaration for Railway (`python-3.11.13`) | Python version upgrade |
| `Procfile` | Railway process: gunicorn command, port, timeout, worker count | Changing server configuration |
| `.github/workflows/bot.yml` | All scheduled and triggered GitHub Actions | Changing run times, adding a new workflow step |
| `CLAUDE.md` | Workflow instructions for Claude sessions | Updating the session workflow |

---

## Frontend Map

Everything lives in `index.html`. There are no separate JS or CSS files.

| Concern | Location |
|---|---|
| Global application state | `const state = { ... }` near the top of the `<script>` block |
| Startup sequence | `boot()` function |
| Full re-render | `rerenderAll()` — calls all page sub-renders |
| Page renders | `renderDailyPicks()`, `renderLiveCenter()`, `renderPending()`, `renderManualBets()`, `renderHistory()`, `renderAnalytics()`, `renderBankroll()` |
| Cloud load / save | `_doLoadCloudState()`, `_reloadManualBetsFromCloud()`, `saveCloudState()` |
| localStorage | `loadLocalState()`, `saveLocalState()`, `markDirty()` |
| Event handlers | Defined inline via `onclick`, `oninput`, `onchange` in the render functions |
| Live/Pending filter logic | `getLiveRows()`, `getPendingRows()` |
| Scout workspace (manual bet creation) | Inside `renderManualBets()` |
| Poisson calculation (client-side) | Called from Scout workspace, uses `state.fixtures` |

For the complete frontend reference, read `docs/03_Dashboard.md`.

---

## Backend Map

| Concern | File | Function / section |
|---|---|---|
| Flask application and routes | `sync_server.py` | Top-level route definitions |
| GitHub API calls | `sync_server.py` | `github_request()` |
| Settlement trigger | `sync_server.py` | `POST /run-settlement` → calls `run_settlement_remote()` |
| Settlement engine | `update_results.py` | `update_dataframe()`, `run_settlement_remote()` |
| Manual bets conversion | `update_results.py` | `manual_bets_to_settlement_df()` |
| API-Football result queries | `update_results.py` | `get_match_result_af()` |
| football-data.org result queries | `update_results.py` | `get_match_result_fd()` |
| League routing (which API to use) | `src/league_registry.py` | `BLOCKED_FOOTBALL_DATA_CODES`, `API_FOOTBALL_FALLBACK_COMPETITIONS` |
| Pick generation orchestration | `run_main.py` | Top-level script |
| Phase 1 — fixture fetch | `fetch_oddsapi_fixtures.py` | `main()` |
| Phase 2 — Poisson model | `main.py` | `main()` |
| Output file writing | `src/pipeline.py` | `save_all_outputs()` |
| Telegram notifications | `run_main.py`, `run_topup.py` | Telegram send blocks |
| Configuration access | `src/config.py` | Module-level constants |

For the complete backend reference, read `docs/04_Backend.md`.

---

## Data Files

| File | Purpose | Producer | Consumer |
|---|---|---|---|
| `cloud_state.json` | Manual bets — single source of truth | Browser (via Railway `/save`) | Browser (via Railway `/load`), settlement (`update_results.py`) |
| `picks_history.csv` | All settled bot picks | Settlement engine (`update_results.py`) | Dashboard History page |
| `picks_hoje_github.csv` | Today's active picks for the dashboard | `src/pipeline.py` | Dashboard Daily Picks page |
| `picks_hoje_simplificado.csv` | Today's active picks for settlement | `src/pipeline.py` | Settlement engine (`update_results.py`) |
| `picks_over25.csv` | Unsettled O2.5 picks | `src/pipeline.py` | Settlement engine |
| `picks_btts.csv` | Unsettled BTTS picks | `src/pipeline.py` | Settlement engine |
| `fixtures_today.csv` | Fixture data with odds and lambdas | `fetch_oddsapi_fixtures.py` | `main.py` (Phase 2), Dashboard Scout |
| `sent_state.json` | Telegram deduplication state | `run_main.py`, `run_topup.py` | `run_main.py`, `run_topup.py` |
| `team_alias_cache.json` | API-Football team name aliases | `update_results.py` | `update_results.py` |
| `manual_bets.csv` | Legacy file — header row only, not active | — | — |
| `data_raw/*.csv` | Historical match results by league | Manual fetch / `fetch_historical.py` | `src/history.py` |
| `league_stats.csv` | Aggregated per-league stats | `src/league_stats.py` | Dashboard Analytics |

---

## Configuration Files

| File | What belongs there |
|---|---|
| `config.json` | Model parameters: edge thresholds, Kelly fraction, bankroll amounts, Poisson decay, API rate limits, shortlist sizes. **Committed to the repository.** |
| `src/config.py` | Typed Python constants that load from `config.json` with fallback defaults. Add a `DEFAULT_` constant here when adding a new `config.json` key. |
| `runtime.txt` | Python version for Railway (`python-3.11.13`). |
| `Procfile` | Railway process command (`gunicorn sync_server:app ...`). |
| Railway environment variables | `GITHUB_TOKEN`, `TELEGRAM_TOKEN`, `CHAT_ID`, `API_FOOTBALL_KEY`, `FOOTBALL_DATA_API_KEY`. Never committed to the repository. |
| `.github/workflows/bot.yml` | GitHub Actions schedule crons, secrets references, workflow steps. |

---

## Development Entry Points

**When modifying the dashboard (frontend):**
→ `index.html` — all logic is inline
→ `docs/03_Dashboard.md` — rendering model, state, localStorage reference

**When modifying settlement:**
→ `update_results.py` — settlement engine
→ `src/league_registry.py` — API routing per league
→ `sync_server.py` — settlement trigger endpoint
→ `docs/04_Backend.md` — backend reference

**When modifying pick generation:**
→ `main.py` — Phase 2 entry point
→ `src/pick_generation.py` — staking and selection logic
→ `src/calculations.py` — Poisson calculations
→ `fetch_oddsapi_fixtures.py` — Phase 1, fixture fetch

**When modifying persistence (cloud state):**
→ `sync_server.py` — `/load` and `/save` endpoints
→ `update_results.py` — `run_settlement_remote()` reads and writes cloud state
→ `docs/09_Architecture_Decisions.md` — ADR-001, ADR-003, ADR-008

**When modifying the Telegram integration:**
→ `run_main.py` — send block for new picks
→ `run_topup.py` — send block for top-up picks
→ `update_results.py` — settlement notification (if added)

**When modifying league metadata:**
→ `src/league_registry.py` — the only place league data lives
→ `config.json` — display name and API-Football ID sections
→ `docs/09_Architecture_Decisions.md` — ADR-004

**When modifying configuration:**
→ `config.json` — add the key and default value
→ `src/config.py` — add the typed constant with a `DEFAULT_` fallback

**When modifying the GitHub Actions schedule:**
→ `.github/workflows/bot.yml`

---

## Files That Should Rarely Be Modified

These files reflect stable decisions. Modify only when there is a structural reason — and update the corresponding documentation in the same session.

| File | Why it is stable |
|---|---|
| `src/league_registry.py` | 21 leagues are defined and working. Change only to add a league or fix a metadata error. |
| `Procfile` | Gunicorn configuration is fixed. `--workers 1` is intentional (ADR-003). |
| `runtime.txt` | Python version. Change only for a deliberate upgrade. |
| `requirements.txt` | Dependencies are minimal and stable. Add only when a new library is genuinely needed. |
| `docs/00_Project_Context.md` | Permanent project context. Changes only if the project scope changes. |
| `docs/01_Architecture.md` | Component map. Changes only if a component is added or removed. |
| `docs/09_Architecture_Decisions.md` | ADR repository. New entries only; existing entries are not revised without overriding them. |
| `data_raw/*.csv` | Historical training data. Modified only when fetching new history for a league. |
| `CLAUDE.md` | Session workflow instructions. Changes only if the development workflow changes. |
