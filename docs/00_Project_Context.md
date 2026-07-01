# Football Bot — Authoritative Project Context

This is the canonical reference for the project. A new conversation reading only this file should be able to understand the architecture, the design principles, and the system constraints without reading chat history or other documents.

Do not add time-sensitive information here. Current bugs, active investigations, and recent changes belong in `05_Known_Issues.md`, `07_Current_Status.md`, and `08_Change_Log.md`.

---

## Project Philosophy

These principles guide all engineering decisions. When in doubt, apply the principle over the convenience.

- **Root cause over symptom.** Fix the underlying problem, not the observable failure. Temporary workarounds accumulate into permanent technical debt.
- **Single source of truth.** Every dataset has exactly one authoritative owner. Duplicated state diverges. Choose one owner and route all reads and writes through it.
- **Minimal duplication.** The same logic in two places is two bugs waiting to happen. Extract and share.
- **Simple and deterministic.** A system that does one thing predictably is better than one that does many things conditionally. Prefer linear pipelines over complex state machines.
- **Architectural change over local patch.** A change that improves the structure prevents a class of bugs. A patch that hides a symptom hides the class too.
- **No speculative complexity.** Only build what is needed for the current requirement. Abstractions earn their place by being used at least twice.

---

## Purpose

A personal football betting assistant. A Poisson model estimates goal-scoring rates for football matches and generates value bets on over/under goals (O1.5, O2.5, O3.5) and both-teams-to-score (BTTS) markets. The project manages a real bankroll using fractional Kelly staking, records all bets, settles results automatically, and displays everything in a web dashboard.

Two categories of bet:

- **Bot picks** — generated automatically by the Python model pipeline; stored in CSV files committed to GitHub.
- **Manual bets** — entered by the user through a Scout workspace in the dashboard; stored in `cloud_state.json` on GitHub.

---

## Architecture

Three runtime components:

```
GitHub Actions (scheduled)
    └─ Python pipeline  →  picks_history.csv / picks_hoje_simplificado.csv  →  GitHub repo

Railway (always-on server)
    └─ Flask API (sync_server.py)
         ├─ GET  /load           ← reads cloud_state.json from GitHub
         ├─ POST /save           ← writes cloud_state.json to GitHub
         ├─ POST /run-settlement ← calls update_results.run_settlement_remote()
         └─ GET  /health, /

Browser (user)
    └─ index.html (single-file dashboard)
         ├─ fetches CSVs from GitHub raw URLs (bot picks)
         └─ fetches/saves cloud_state.json via Railway API (manual bets + dashboard state)
```

---

## Architecture Principles

These are the structural decisions that should not be revisited without strong reason.

**`cloud_state.json` is the single source of truth for manual bets.**  
`manual_bets.csv` is a legacy file that exists in the repo with a header row only. No active code reads bet data from it. All manual bet reads and writes go through `cloud_state.json`.

**Bot and manual bets share the same settlement engine.**  
`update_dataframe()` in `update_results.py` settles both. Manual bets are converted to a DataFrame, settled, and converted back. This prevents divergence in settlement logic.

**The League Registry is the only place where leagues are registered.**  
`src/league_registry.py` is the single source of truth for league metadata. `LEAGUE_CODE_MAP`, `BLOCKED_FOOTBALL_DATA_CODES`, `API_FOOTBALL_FALLBACK_COMPETITIONS`, and `AF_SEASON_MODELS` are all derived from it automatically. Never add league mappings directly to `update_results.py`, `config.json`, or any other file.

**The frontend is a single self-contained HTML file with no framework and no build step.**  
`index.html` contains all JavaScript inline. There is no npm, no bundler, no transpiler. All changes are made directly in this file.

**GitHub is the persistence layer.**  
All persistent data lives in files committed to the GitHub repository. The Railway server holds no local state. The browser's localStorage is a cache of `cloud_state.json`, not an independent data store.

**The Railway server has a single worker.**  
`gunicorn --workers 1` prevents concurrent GitHub API writes. Settlement is synchronous and serialised.

---

## Technologies

| Layer | Technology |
|---|---|
| Pick model | Python 3.11, pandas (Poisson model) |
| Backend server | Flask + gunicorn, hosted on Railway |
| Scheduled automation | GitHub Actions (`bot.yml`) |
| Frontend | Single HTML file (`index.html`) — all JS inline, no build step |
| Result APIs | football-data.org (EU leagues), API-Football v3 (blocked EU + non-EU) |
| Notifications | Telegram Bot API |
| Persistence | GitHub repository (file storage via GitHub Contents API) |
| Python dependencies | pandas, requests, flask, flask-cors, gunicorn, python-dotenv |

---

## Source of Truth

| Dataset | Owner | Location |
|---|---|---|
| Bot picks (today) | GitHub Actions main generation | `picks_hoje_simplificado.csv` in repo root |
| Bot picks (history) | GitHub Actions settlement | `picks_history.csv` in repo root |
| Manual bets | `cloud_state.json` → `manualBets` array | `cloud_state.json` in repo root |
| Dashboard daily fixtures | `cloud_state.json` → `footballDaily` | `cloud_state.json` in repo root |
| Dashboard history | `cloud_state.json` → `footballHistory` | `cloud_state.json` in repo root |
| Bankroll and settings | `cloud_state.json` → top-level keys | `cloud_state.json` in repo root |
| Local edits (odd real, stake real) | `cloud_state.json` → `localEdits` | `cloud_state.json` in repo root |
| Already-sent pick IDs | `sent_state.json` | `sent_state.json` in repo root |
| League performance aggregates | Settlement pipeline | `league_stats.csv` in repo root |
| Team name normalisation cache | `update_results.py` at runtime | `team_alias_cache.json` (local/Railway) |

**`manual_bets.csv` is dead.** It contains only a header row. It is not read by any active code path. Manual bets are owned exclusively by `cloud_state.json`.

---

## Backend

### GitHub Actions — `bot.yml`

Four scheduled jobs run daily:

| Time (UTC) | Job | Script |
|---|---|---|
| 07:00 | Settlement | `python update_results.py` |
| 17:00 | Main generation | `python run_main.py` |
| 22:30 | Settlement | `python update_results.py` |
| 23:00 | Top-up (non-EU leagues, late odds) | `python run_topup.py` |

All jobs can also be triggered manually via `workflow_dispatch`.

### Pick Generation — `main.py` / `run_main.py` / `run_topup.py`

1. Fetch fixtures for each configured league from football-data.org or API-Football.
2. Apply the Poisson model to estimate goal probabilities.
3. Compare model probabilities against market odds; filter by edge threshold (dynamic Kelly).
4. Deduplicate against `sent_state.json`.
5. Write new picks to `picks_hoje_simplificado.csv` and append to `picks_history.csv`.
6. Commit both CSVs to GitHub.
7. Send Telegram notification.

### Settlement Engine — `update_results.py`

Runs at 07:00 and 22:30 UTC via GitHub Actions, and on-demand via Railway `POST /run-settlement`.

**Bot pick settlement:**
- Downloads `picks_history.csv` and `picks_hoje_simplificado.csv` from GitHub.
- For each unsettled row: queries football-data.org first; falls back to API-Football if the league is blocked on FD or FD fails.
- Writes W/L/P result and profit to each row.
- Commits updated CSVs back to GitHub.

**Manual bet settlement:**
- Downloads `cloud_state.json` from GitHub.
- Converts `manualBets` array to a DataFrame using the same `update_dataframe()` engine as bot picks.
- Normalises market codes (`"Over 2.5"` → `"O2.5"`) and resolves league display names via the league registry.
- Applies W/L/P results back to the bet objects.
- Saves updated `cloud_state.json` to GitHub only if at least one new settlement occurred.

**Supported markets:** `O1.5`, `O2.5`, `O3.5`, `BTTS`

**Settlement result keys:** Valid settled values are exactly `"W"`, `"L"`, `"P"` (uppercase, no whitespace). The settlement engine filters on these exact strings in both CSV rows and JSON bet objects.

### Railway Server — `sync_server.py`

A minimal Flask API with four endpoints. Its only job is to proxy `cloud_state.json` reads and writes through the GitHub Contents API and to trigger settlement on demand. It holds no local state. Deployed with `gunicorn --workers 1 --timeout 300`.

### League Registry — `src/league_registry.py`

Single source of truth for all league metadata. To add a league, edit only this file.

**21 registered leagues:**

EU (football-data.org): Premier League, LaLiga, Ligue 1, Serie A, Eredivisie, Championship.

EU blocked on football-data.org (API-Football direct): Primeira Liga, Bundesliga, 2. Bundesliga, Serie B, Ligue 2, Jupiler Pro League, Super Lig.

Non-EU (API-Football, calendar-year seasons): Eliteserien, Allsvenskan, Veikkausliiga, Besta deild, MLS (MLS Next Pro, af_id=909), Campeonato Brasileiro Série A, J1 League, K League 1.

**Season models:**
- `"european"` — season year = calendar year the season starts (Aug). Jan–Jun of year Y → season Y-1.
- `"calendar"` — season year = calendar year the game is played. Used for Nordic, American, Asian, and Brazilian leagues.

---

## Frontend

`index.html` is a single self-contained file with all JavaScript inline. There is no build step, no framework, and no npm.

### Pages

| Page | Purpose |
|---|---|
| Daily Picks | Today's bot picks with edge, stake, kickoff |
| Live Center | All active bets (bot + manual) that are approved and unsettled |
| Pending | Manual bets awaiting kickoff |
| Manual Bets | Scout workspace: search fixtures, run Poisson model, create/approve/reject bets |
| History | Full settled history with filtering and analytics |
| Analytics | Equity curve, drawdown, bot vs manual performance, calibration |
| Settings | Bankroll, Kelly fraction, edge thresholds |

### State Management

The dashboard maintains two state stores:

- **`state.manualBets`** — manual bets loaded from localStorage at startup, refreshed from `cloud_state.json` via Railway `/load`. Written to localStorage on every change and after settlement.
- **`state.manualBetsRemote`** — bot picks from `manual_bets.csv` (always empty; legacy path no longer used).

On startup, `boot()` calls `loadLocalState()` to hydrate from localStorage, then `rerenderAll()`, then fetches CSVs via `loadData()`. Auto-recovery from the cloud (`_doLoadCloudState()`) only runs at startup if `hasMeaningfulLocalState()` returns false.

The 60-second auto-refresh interval calls `loadData()`, which fetches picks CSVs only. It does not call `/load` and does not refresh `state.manualBets`. Manual bets are only refreshed from the cloud by explicit user actions: clicking "Load Cloud" or triggering "Run Settlement" from the dashboard.

---

## Operational Constraints

- **GitHub API as database.** Every file save requires a separate GET to fetch the current SHA before the PUT. There is no locking mechanism. Concurrent writes from GitHub Actions and Railway can produce conflicts.
- **API rate limits.** football-data.org: 10 requests/minute on the free tier (`FD_CALL_MIN_INTERVAL = 0.65s` enforced). API-Football runs on a paid subscription: 7500 requests/day and 300 requests/minute. These are deployment-level limits configured in the Railway environment — they are not hardcoded in the application and can be adjusted without changing the code.
- **Settlement is synchronous.** A single settlement run can take up to 90 seconds. The Railway gunicorn timeout is 300 seconds.
- **No build system.** The entire frontend is one HTML file. All changes are made in-place. There is no compile step and no output artefact.
- **localStorage is a cache, not a database.** Browser localStorage holds a copy of `cloud_state.json`. If it diverges from the server (e.g. settlement ran in a different browser session), the user must manually click "Load Cloud" to re-sync.
