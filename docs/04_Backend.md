# Backend

This document describes the Football Bot backend in technical detail. For system architecture overviews, data flow diagrams, and component interaction maps, see `01_Architecture.md` and `02_Data_Flow.md`. For frontend documentation, see `03_Dashboard.md`. This document focuses exclusively on the backend.

---

## 1. Backend Overview

The backend consists of two runtime components operating in parallel: a scheduled batch pipeline running on GitHub Actions and an always-on API server running on Railway.

**The backend owns:**
- Pick generation: Poisson modelling, edge detection, Kelly staking, CSV output.
- Settlement: querying result APIs, writing W/L/P to bet records, computing profit.
- GitHub persistence: reading and writing all persistent files via the GitHub Contents API.
- Telegram notifications: sending pick summaries and alerts after generation.
- The `cloud_state.json` synchronisation bridge between browser and GitHub.

**The backend does not own:**
- The user session or browser state. `localStorage` belongs to the frontend.
- Odds data: odds are pulled from API-Football at generation time and stored in CSVs; the backend does not cache or maintain them.
- Display logic. The backend knows nothing about how data is presented.

**Responsibilities by component:**

| Component | Runs on | Trigger | Primary responsibility |
|---|---|---|---|
| Pick generation | GitHub Actions | 17:00 UTC daily | Generate O2.5 and BTTS picks; upload CSVs |
| Top-up generation | GitHub Actions | 23:00 UTC daily | Add late-odds non-EU picks |
| Settlement | GitHub Actions | 07:00 and 22:30 UTC | Resolve open picks; update CSVs |
| Flask API | Railway | Always-on | Sync `cloud_state.json`; trigger on-demand settlement |

---

## 2. Runtime Components

### Railway (Flask API server)

Always-on Flask service deployed on Railway's shared infrastructure. Its only job is to act as a proxy between the browser and GitHub. It holds no local state.

- **Purpose:** Browser CORS bridge for `cloud_state.json`. GitHub's API requires a token; Railway holds the token so the browser does not.
- **Interactions:** Browser → Railway → GitHub Contents API → GitHub.
- **Lifecycle:** Always running. Restarts automatically on crash or deploy.

### Flask (web framework)

Flask handles HTTP request routing inside Railway. `flask-cors` allows cross-origin requests from any domain. `gunicorn` serves Flask in production.

- **Purpose:** Route HTTP requests to handler functions.
- **Session:** None. Flask is configured with no session management.

### gunicorn (WSGI server)

Gunicorn wraps Flask. Configured with `--workers 1 --timeout 300`.

- **Purpose:** Production WSGI server. Provides process-level isolation from Flask's development server.
- **Single worker:** The single worker is intentional. Multiple workers would allow concurrent writes to `cloud_state.json` via the GitHub Contents API, producing SHA conflicts.
- **Timeout:** 300 seconds matches the maximum settlement duration (~90 seconds typical, ~180 seconds worst-case).
- **Port:** 10000.

### GitHub Actions (scheduled automation)

GitHub-hosted runners execute the Python pipeline on a cron schedule. Each run is a fresh ephemeral environment: Ubuntu, Python 3.11, all requirements installed from scratch.

- **Purpose:** Scheduled execution of pick generation and settlement.
- **Lifecycle:** Started by schedule or `workflow_dispatch`; exits after the script finishes.
- **Permissions:** `contents: write` — required to commit updated CSVs.
- **Secret injection:** `GITHUB_TOKEN`, `TELEGRAM_TOKEN`, `CHAT_ID`, `API_FOOTBALL_KEY`, `FOOTBALL_DATA_API_KEY` are injected as environment variables from GitHub repository secrets.

### GitHub API (persistence layer)

All persistent files are stored in the `jorgepita/apostas-over-futebol` repository. Reads and writes use the GitHub Contents API (`https://api.github.com/repos/...`).

- **Purpose:** Database substitute. Provides versioned, durable storage with no infrastructure cost.
- **Interactions:** Both Railway and GitHub Actions use the Contents API. The browser reads CSVs via the raw URL (`https://raw.githubusercontent.com/...`), bypassing the API.

### football-data.org (result API)

Used exclusively for settlement of EU leagues with active support.

- **Purpose:** Query match results for Premier League, LaLiga, Ligue 1, Serie A, Eredivisie, Championship.
- **Lifecycle:** Called during settlement only. Not called during generation.
- **Limitations:** Free plan, 10 requests/minute. Rate enforced by `FD_CALL_MIN_INTERVAL = 0.65s`.

### API-Football (fixtures and result API)

Used for two distinct purposes: fixture shortlisting and odds fetching during generation, and result settlement for blocked/non-EU leagues.

- **Purpose (generation):** Fetch upcoming fixtures for all 22 leagues; fetch O2.5 and BTTS odds for shortlisted fixtures.
- **Purpose (settlement):** Settle results for leagues blocked on football-data.org (Bundesliga, Primeira Liga, Super Lig, etc.) and all non-EU leagues (MLS, J1 League, etc.).
- **Paid plan:** 7500 requests/day, 300 requests/minute. Limits are Railway environment configuration, not hardcoded.
- **Base URL:** `https://v3.football.api-sports.io`. Configurable via `API_FOOTBALL_BASE` environment variable.

### Telegram (notifications)

Used exclusively for outbound notifications after pick generation.

- **Purpose:** Send new picks to the user's Telegram bot chat after each generation run.
- **Deduplication:** `sent_state.json` tracks which pick IDs have been sent. Picks already in `sent_state.json` are not re-sent.
- **Lifecycle:** Called at the end of the generation pipeline. Not called during settlement.
- **Configuration:** `TELEGRAM_TOKEN` and `CHAT_ID` environment variables.

---

## 3. Railway Service

### Deployment

Railway deploys from the `main` branch of the repository. The start command is:

```
gunicorn sync_server.py:app --workers 1 --timeout 300 --bind 0.0.0.0:10000
```

Railway restarts the service automatically on crash or on any new deploy triggered by a push to `main`.

### Startup

At module load time, `sync_server.py`:
1. Reads `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_BRANCH` from environment.
2. Raises `RuntimeError` immediately if `GITHUB_TOKEN` is missing — a misconfigured service fails loudly on startup rather than silently on first request.
3. Initialises a `requests.Session` with Authorization, Accept, and User-Agent headers pre-set.

### Request lifecycle

```
Browser sends HTTP request
      │
      ▼
gunicorn (worker process)
      │
      ▼
Flask routing → handler function
      │
      ├─ GET /load: github_request("GET") → json.loads → jsonify
      ├─ POST /save: json.loads(body) → github_request("GET" for SHA) → github_request("PUT")
      └─ POST /run-settlement: import update_results.run_settlement_remote() → execute
      │
      ▼
JSON response to browser
```

`github_request()` has a 15-second timeout. If the GitHub API does not respond within 15 seconds, the request raises an exception and returns HTTP 500.

### Why the backend is stateless

The Railway service holds no in-process state between requests. Each request reads from GitHub and writes to GitHub. This means:
- The service can restart at any time without data loss.
- There are no in-memory caches to invalidate.
- Multiple deploys can happen safely.
- There is no session state, no database connection, no temporary files.

The statelessness is the reason `cloud_state.json` is re-fetched from GitHub on every `/load` and re-written on every `/save`, rather than being cached in memory.

---

## 4. API Endpoints

### GET /

**Purpose:** Service discovery and sanity check.

**Request:** No parameters.

**Response:**
```json
{
  "ok": true,
  "service": "apostas-dashboard-sync",
  "endpoints": ["/health", "/load", "/save", "/run-settlement"],
  "repo": "jorgepita/apostas-over-futebol",
  "branch": "main"
}
```

**Side effects:** None.

**Caller:** Manual testing, monitoring systems.

---

### GET /health

**Purpose:** Health probe for Railway uptime monitoring.

**Request:** No parameters.

**Response:**
```json
{
  "ok": true,
  "service": "apostas-dashboard-sync",
  "time": "2026-06-29T10:00:00+00:00"
}
```

**Side effects:** None.

**Caller:** Railway health check; browser cloud status check.

---

### GET /load

**Purpose:** Download the current `cloud_state.json` from GitHub and return its contents as JSON.

**Request:** No parameters.

**Response:** The parsed JSON object from `cloud_state.json`. Returns `{}` if the file does not exist (404) or is empty.

**Side effects:** One GitHub Contents API GET request. Reads `cloud_state.json` from the `main` branch.

**Caller:** Browser — on startup (auto-recovery), on "Load Cloud" button, after `POST /run-settlement`.

**Error:** Returns HTTP 500 with `{"error": "..."}` if the GitHub request fails.

---

### POST /save

**Purpose:** Write a new version of `cloud_state.json` to GitHub.

**Request body:**
```json
{
  "content": { /* full cloud_state object */ },
  "message": "update cloud state"
}
```

**Response (normal):**
```json
{
  "success": true,
  "sha": "abc123..."
}
```

**Response (a duplicate manual bet was dropped — Phase 26.19, ADR-013):**
```json
{
  "success": true,
  "sha": "abc123...",
  "duplicatesRemoved": 1
}
```

**Side effects:**
1. If `content.manualBets` is present, `_dedupe_manual_bets()` scans it for two-or-more bets sharing the same `(data, liga, jogo, mercado)` identity — normalised via the exact same `_resolve_liga_display_name()` / `_normalize_market_code()` helpers the settlement engine uses — and keeps only the earliest occurrence per identity. This is the authoritative, server-side duplicate guard; the frontend already prevents this in normal use (see `03_Dashboard.md` §7), but a race between two tabs or a stale local save could otherwise still produce a duplicate record in `cloud_state.json`.
2. One GitHub Contents API GET request to fetch the current SHA.
3. One GitHub Contents API PUT request to write the new (possibly deduplicated) content.

The GET for SHA is required. The GitHub Contents API rejects PUT requests for existing files without a matching SHA. This is the mechanism that prevents overwriting concurrent changes.

**Caller:** Browser — triggered by `saveCloudState()` after any state mutation, with a 4-second debounce. When the response carries `duplicatesRemoved > 0`, `saveCloudState()` calls `_reloadManualBetsFromCloud()` so `state.manualBets` matches what was actually persisted instead of silently keeping the dropped duplicate in memory.

**Error:** Returns HTTP 500 with `{"error": "..."}` if either GitHub request fails (e.g. SHA conflict, network timeout).

---

### POST /run-settlement

**Purpose:** Trigger a full settlement run from the browser. Settles both bot picks and manual bets synchronously.

**Request body:** None required.

**Response (normal — provider returned real data, whether or not anything matched):**
```json
{
  "ok": true,
  "updated": 3,
  "ignored": 12,
  "duration": 47.2
}
```

**Response (provider failure — Phase 26.18):** if a provider (API-Football or football-data.org) rejected a request this run (bad plan/quota/auth/network/server error — see §7 "Provider error handling") and nothing settled as a result, two extra fields are added so the caller can tell a real provider outage apart from a genuinely empty result:
```json
{
  "ok": true,
  "updated": 0,
  "ignored": 21,
  "duration": 5.1,
  "provider_errors": [
    {
      "provider": "api-football",
      "endpoint": "https://v3.football.api-sports.io/fixtures?league=909&season=2026&date=2026-07-04",
      "request": {"league": 909, "season": 2026, "date": "2026-07-04"},
      "category": "PLAN_LIMIT",
      "message": "plan: Free plans do not have access to this season, try from 2022 to 2024.",
      "retryable": false,
      "timestamp": "2026-07-06T12:00:00+00:00"
    }
  ],
  "settlement_aborted": true,
  "abort_provider": "api-football",
  "abort_category": "PLAN_LIMIT",
  "abort_reason": "plan: Free plans do not have access to this season, try from 2022 to 2024."
}
```
`provider_errors` is present whenever at least one provider error occurred this run, even if other picks still settled successfully via a different league/provider (`updated > 0`) — in that case `settlement_aborted` is omitted since settlement did produce results. `settlement_aborted` (plus `abort_provider`/`abort_category`/`abort_reason`) only appears when `updated === 0` **and** a provider error occurred — this is what lets the dashboard show "⚠ Settlement unavailable" instead of the misleading "No matches to settle." (see `03_Dashboard.md` §8). When `provider_errors` is absent and `updated === 0`, that is a genuine empty result and "No matches to settle." is correct.

**Side effects:**
1. Downloads `picks_history.csv` and `picks_hoje_simplificado.csv` from GitHub to a temporary directory.
2. Runs settlement on both files via `update_dataframe()`.
3. Uploads updated CSVs to GitHub.
4. Downloads `cloud_state.json` from GitHub.
5. Runs settlement on `manualBets` via `update_dataframe()`.
6. If any manual bets were newly settled, or if any provider was contacted this run (success or failure — see §7): uploads updated `cloud_state.json` to GitHub, the latter to persist `providerHealth`.
7. Cleans up the temporary directory.

**Caller:** Browser — "Run Settlement" button in the Live Center.

**Timeout risk:** Settlement can take up to ~90 seconds under normal load. The gunicorn timeout is 300 seconds. The endpoint will block the HTTP connection for the entire duration.

**Error:** Returns HTTP 500 with `{"ok": false, "error": "..."}` if any step fails.

---

## 5. GitHub Integration

### Why GitHub is the persistence layer

GitHub provides versioned, durable, zero-cost storage with a well-documented API. The project has no budget for a dedicated database. GitHub is already required for the pick pipeline (CSVs are committed by GitHub Actions), so using it for `cloud_state.json` too means the entire system has one storage backend.

All persistent state can be inspected and recovered directly from the repository. Every write is a commit with a timestamp and message.

### Contents API

All reads and writes use the GitHub Contents API:

```
GET  https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}
PUT  https://api.github.com/repos/{owner}/{repo}/contents/{path}
```

**Authentication:** `Authorization: Bearer {GITHUB_TOKEN}` header.

### File reads

```python
def get_file_from_github(path: str) -> tuple[str | None, str | None]:
    resp = SESSION.get(github_contents_url(path), params={"ref": GITHUB_BRANCH})
    if resp.status_code == 404:
        return None, None
    data = resp.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    sha = data["sha"]
    return content, sha
```

The response body contains the file contents as base64-encoded string and a SHA hash of the current version. Reads always return the current SHA alongside the content.

### File writes

```python
def put_file_to_github(path: str, content_text: str, message: str, sha=None):
    payload = {
        "message": message,
        "content": base64.b64encode(content_text.encode("utf-8")).decode("utf-8"),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    resp = SESSION.put(github_contents_url(path), json=payload)
    resp.raise_for_status()
    return resp.json()
```

**SHA requirement:** For an existing file, the PUT must include the current file SHA. GitHub rejects the request with HTTP 409 (Conflict) if the SHA does not match the current HEAD. This is the OCC (optimistic concurrency control) mechanism.

**New files:** Omitting `sha` from the payload creates a new file. If the file already exists, GitHub returns HTTP 422.

### SHA handling

The standard save flow is:
1. GET the file to obtain the current SHA.
2. PUT the new content with the SHA.

If another process writes the file between step 1 and step 2, the PUT will fail with HTTP 422 (SHA mismatch). Railway does not retry on SHA conflict — the error propagates to the caller as HTTP 500.

### Conflict handling

SHA conflicts can occur when GitHub Actions settlement and Railway settlement run simultaneously. The single gunicorn worker prevents concurrent Railway requests, but it does not prevent a GitHub Actions run from writing while Railway is mid-save.

Expected conflict rate is very low (GitHub Actions runs at 07:00 and 22:30 UTC; Railway settlement is user-triggered). No automatic conflict resolution is implemented.

---

## 6. Pick Generation Pipeline

The generation pipeline runs in two phases. Phase 1 (`fetch_oddsapi_fixtures.py`) fetches fixtures and odds from API-Football and produces `fixtures_today.csv`. Phase 2 (`main.py`) reads `fixtures_today.csv`, applies the Poisson model, and produces all pick CSVs.

### Phase 1 — Fixture shortlisting and odds fetching (`fetch_oddsapi_fixtures.py`)

```
For each league in config.json:
    For each date in [today … today + days_ahead]:
        GET /fixtures (API-Football, league_id, season, date)
        For each fixture:
            Filter past fixtures
            Load data_raw/{league_key}.csv (league match history)
            Compute lambdas via Poisson model
            Score fixture: score = lam_t + min(lam_h, lam_a) * 0.75
        Keep top N per league per day (shortlist_per_league_per_day = 4)

Global deduplication by fixture_id

Global shortlist with per-league guarantee:
    Pass 1: guarantee each league ≥ 2 slots (in descending score order)
    Pass 2: fill remaining capacity from highest-scored candidates
    Total shortlist: up to 80 fixtures (shortlist_total = 80)

For each shortlisted fixture:
    GET /odds (API-Football, fixture_id)
    Extract best O2.5 odd and best BTTS odd

Write fixtures_today.csv (semicolon-delimited)
Upload fixtures_today.csv to GitHub
```

**Lambda computation:** For each fixture, `compute_lambdas()` computes `lam_home` and `lam_away` from the last `window` (12) home and away games using exponential decay `decay = 0.88`. When a team has fewer than `min_games_home` (8) or `min_games_away` (8) games in the history file, the league average is used as a fallback.

**Lambda boost:** A per-league `lambda_boost` multiplier (default 1.12) inflates the raw lambdas to account for systematic underestimation. Calendar-year leagues (Brazil, Japan, Korea, Scandinavia, Iceland) use `lambda_boost = 1.00` because the model performs better calibrated on those leagues.

**Odds extraction:** For each shortlisted fixture, the `/odds` API returns bookmaker odds. O2.5 odds are extracted from markets matching "Over/Under 2.5" across all bookmakers. BTTS odds are extracted from "Both Teams to Score / Yes" markets. The highest valid odd in range (`O2.5: 1.10–8.00`, `BTTS: 1.20–3.50`) is kept.

**Rate limiting:** `API_CALL_MIN_INTERVAL = 0.28s` between requests. Additional `sleep_between_requests = 0.35s` between fixture fetches per league.

### Phase 2 — Poisson model and pick generation (`main.py` via `src/pick_generation.py`)

```
Load fixtures_today.csv → state.fixtures
Filter to date window [today … today + days_ahead - 1]

For each league:
    process_league_fixtures():
        For each fixture:
            Compute lam_home, lam_away via Poisson
            Compute P(O2.5): sum of P(total_goals >= 3) using Poisson PMF
            Compute P(BTTS): calibrated Poisson (btts_probability_adjustment = 0.885)
            Market odd from fixtures_today.csv
            edge = model_prob - (1 / market_odd)
            Generate O2.5 pick if edge in [edge_min, edge_max]
            Generate BTTS pick if edge in [edge_min, edge_max]

apply_market_rules(rows25, bankroll, rules, "O2.5"):
    Filter by odds bounds (max 2.20 for O2.5)
    Filter by edge bounds (edge_min=0.0075, edge_max=0.15)
    Apply BTTS calibration penalties (for BTTS only)

apply_fixture_market_lock():  (src/pipeline.py — ADR-018, Policy A fixture-level market lock)
    Reject any candidate whose fixture already has a DIFFERENT market
    persisted in picks_history.csv. Runs on the concatenated O2.5+BTTS
    candidate set, BEFORE dedupe_correlated_picks() below, so a fixture with
    no prior history is completely unaffected. Shared verbatim by both the
    main and top-up runs (same main() function, same call site).

dedupe_correlated_picks():
    Cross-market selection: groups the SURVIVING candidates by fixture
    (Date+League+HomeTeam+AwayTeam, no Market) and keeps exactly one row per
    fixture — Edge DESC → KellyTrue DESC → ProbModel DESC → Odd DESC. For a
    never-before-recommended fixture this picks between O2.5 and BTTS exactly
    as it always has; for an already-locked fixture, apply_fixture_market_lock()
    has already reduced the group to at most one candidate.

limit_picks_per_day():
    max_picks_per_day = 12
    max_picks_global = 36

apply_stakes(rows, bankroll, rules, market):
    Kelly fraction: kelly_true = (edge / (odd - 1)) × kelly_fraction (0.18)
    Confidence: confidence_factor(edge) = clip(edge / 0.10, 0, 1) — src/calculations.py (Phase 26.29)
    Stake€ = min(kelly_true × kelly_fraction × confidence_factor(edge) × bankroll, cap_frac × bankroll)
    Daily aggregate cap: daily_cap_frac × bankroll (0.12)

add_rank_fields():
    Adds rank by edge within each day × market group

save_all_outputs():
    picks_over25.csv         — only O2.5, semicolon-delimited
    picks_btts.csv           — only BTTS, semicolon-delimited
    picks_hoje.csv           — combined, semicolon-delimited
    picks_hoje_github.csv    — combined, comma-delimited (dashboard-facing)
    picks_hoje_simplificado.csv — settlement format (Data/Liga/Jogo/Mercado columns)

persist_history():
    merge_into_history(): append new picks to picks_history.csv, deduplicate
    update_league_stats(): recompute league_stats.csv from picks_history.csv

process_notifications():
    Load sent_state.json
    For each new pick not already in sent_state: send via Telegram
    Save updated sent_state.json

upload_outputs():
    Upload all 5 output CSVs + picks_history.csv to GitHub via Contents API
```

### Top-up mode (`run_topup.py`)

The top-up run at 23:00 UTC is identical to the main run with two differences:
1. Only processes non-EU leagues: `mls`, `brasil`, `japao`, `coreia`, `noruega`, `suecia`, `finlandia`, `islandia`.
2. Uses `_append_csv()` instead of overwriting: new picks are appended to the existing CSVs, with deduplication by `(Date, HomeTeam, AwayTeam, Market)`.

This design allows EU picks (generated at 17:00) to survive the top-up run at 23:00.

---

## 7. Settlement Engine

### Overview

Settlement is implemented in `update_results.py`. The core function, `update_dataframe()`, processes any DataFrame with the standard CSV column schema. It is called identically for bot picks and manual bets — the settlement logic is shared.

**Settlement constant:**
- `RESULT_READY_DELAY = timedelta(hours=2, minutes=15)` — a pick is not attempted until 2h15m after its kickoff.
- `FD_FINISHED_STATUS = {"FINISHED"}` — football-data.org status indicating a completed match.
- `AF_FINISHED_STATUS = {"FT", "AET", "PEN"}` — API-Football status codes indicating a completed match.
- `MATCH_MIN_TOTAL_SCORE = 140` — minimum combined team name similarity score for a fixture match to be accepted.
- `MATCH_MIN_SIDE_SCORE = 62` — minimum per-side similarity score (each team must score at least this individually).

### Bot pick settlement

**GitHub Actions flow (`main()` in `update_results.py`):**

```
Read picks_history.csv (local, from checkout)
Read picks_hoje_simplificado.csv (local, from checkout)

shared_state = make_shared_runtime_state()

update_dataframe(history_df, "history", shared_state)
    → writes W/L/P + Lucro€ to history rows
history_df.to_csv(HISTORY_FILE)

_persist_league_stats(HISTORY_FILE, LEAGUE_STATS_FILE, "league_stats.csv")
    → update_league_stats(HISTORY_FILE, LEAGUE_STATS_FILE): recomputes per-league aggregates
    → upload_csv_to_github(LEAGUE_STATS_FILE, "league_stats.csv"): persists immediately
      (Phase 26.44 fix — see ADR/Known Issues: previously computed locally only,
      discarded on the ephemeral runner, never actually reaching GitHub)
    → both steps share one try/except: a computation or upload failure here is
      logged and skipped, never allowed to abort the history/daily settlement
      that already succeeded above

update_dataframe(daily_df, "daily", shared_state)
    → writes W/L/P + Lucro€ to daily rows

sync_daily_from_history(daily_df, history_df)
    → copies settled results from history into daily (catchup)

daily_df.to_csv(DAILY_FILE)

save_team_alias_cache(shared_state)
    → writes learned team name mappings to team_alias_cache.json

upload_csv_to_github(HISTORY_FILE, "picks_history.csv")
upload_csv_to_github(DAILY_FILE, "picks_hoje_simplificado.csv")
```

**Railway flow (`run_settlement_remote()`):**

Same logic, but runs entirely in a `tempfile.TemporaryDirectory`. Files are downloaded from GitHub at the start and uploaded at the end. No local filesystem state is kept.

### Manual bet settlement

Manual bets are settled using the same `update_dataframe()` as bot picks — **including rejected bets**: neither `manual_bets_to_settlement_df()` nor `update_dataframe()` filters by lifecycle `status`, so a rejected bet whose fixture has finished is settled in exactly the same run, by exactly the same code, as an approved one (see ADR-012). The bridge is:

1. `manual_bets_to_settlement_df(manual_bets)` — converts the JSON bet objects from `cloud_state.json` to a DataFrame with the standard CSV column schema (including `Placar`, round-tripped from `bet['placar']` so an already-settled bet's final score survives across runs; and `KickoffUTC`, read from `bet['kickoffUTC']` — see the frontend note below and ADR referenced in `05_Known_Issues.md` SETTLEMENT-2).
2. `update_dataframe(manual_df, "manual", shared_state)` — settles the DataFrame rows using the same API queries and matching logic. Both write sites (`try_update_row_via_api_football()` and the football-data.org branch) write `Placar` (`"{home_goals}-{away_goals}"`) alongside `Resultado` and `Lucro€` — the same fact bot pick CSV rows now also carry.
3. `apply_df_results_to_manual_bets(manual_bets, manual_df)` — writes `resultado`, `lucro`, and `placar` back from the settled DataFrame into the original bet dicts. **`status` is only advanced to `'settled'` if it was not already `'rejected'`** — a rejected bet keeps `status: 'rejected'` forever, even after this call populates its settlement result. This is the one deliberate behavioural asymmetry in an otherwise identical settlement path (ADR-012).
4. If any bets were newly settled: `save_cloud_state_to_github(cloud_state, message)`.

### `update_dataframe()`

The core settlement function. Takes a DataFrame, iterates each row, and applies results in-place.

**Row processing flow:**

```
For each row:
    1. ALREADY_DONE: Resultado in {W, L, P} → skip (recalculate LucroReal€ if possible)
    2. INVALID_ROW: missing Data/Liga/Jogo, or Odd ≤ 1.01, or Stake€ ≤ 0 → skip
    3. KICKOFF_TOO_EARLY: skipped entirely if KickoffUTC is empty; otherwise
       now < kickoffUTC + 2h15m → skip (see Known Issues SETTLEMENT-2 — until
       Phase 26.32, manual bets never had KickoffUTC populated at all, so this
       gate silently never applied to them)
    4. UNSUPPORTED_MARKET: Mercado not in {O1.5, O2.5, O3.5, BTTS} → skip
    5. FUTURE_DATE: pick date > today (Lisbon timezone) → skip
    6. MISSING_LEAGUE_MAP: Liga not in LEAGUE_CODE_MAP → skip
    7. BAD_GAME_FORMAT: Jogo does not contain " vs " → skip

    8. Provider selection:
       if league_code in BLOCKED_FOOTBALL_DATA_CODES:
           → try_update_row_via_api_football() [direct]
       else:
           → fetch_matches_for_league_date() [football-data.org]
           if FD fetch succeeds:
               find_best_fixture_match()
               if match found:
                   check kickoff + RESULT_READY_DELAY
                   check status in FD_FINISHED_STATUS
                   compute resultado = market_result(market, home_goals, away_goals)
                   write Resultado, Lucro€, LucroReal€
               else if league has AF fallback:
                   → try_update_row_via_api_football() [fallback]
           else (FD error) if league has AF fallback:
               → try_update_row_via_api_football() [fallback]
```

### Market normalisation (manual bets)

Manual bets from the dashboard UI store market codes in various formats. `_normalize_market_code()` maps any representation to the canonical `SUPPORTED_MARKETS` code:

| Input | Output |
|---|---|
| `"Over 2.5"`, `"OVER25"`, `"O25"` | `"O2.5"` |
| `"Over 1.5"`, `"OVER15"`, `"O15"` | `"O1.5"` |
| `"Over 3.5"`, `"OVER35"`, `"O35"` | `"O3.5"` |
| `"BTTS"`, `"BothTeamsToScore"`, `"Yes"` | `"BTTS"` |

### League resolution (manual bets)

Manual bets store the league as the internal config key (`"mls"`, `"finlandia"`) from the Scout UI, or as a free-text display name. `_resolve_liga_display_name()` converts any form to the display name used by `LEAGUE_CODE_MAP`:

1. If the raw string is already in `LEAGUE_CODE_MAP` (it is a display name): return as-is.
2. If the raw string is an internal config key (e.g. `"mls"`): look up `REGISTRY_BY_KEY`, return the `name` field.
3. Case-insensitive match against `LEAGUE_CODE_MAP` keys.
4. If no match found: return the raw string (will fail `MISSING_LEAGUE_MAP` check in `update_dataframe()`).

### API selection

The settlement provider decision tree:

```
Is league_code in BLOCKED_FOOTBALL_DATA_CODES?
    YES → API-Football direct (no FD attempt)
    NO  → football-data.org first
              → success + match found → settle via FD
              → success + no match + league has AF fallback → API-Football fallback
              → FD fetch error (403/429/other) + league has AF fallback → API-Football fallback
              → no AF fallback → skip
```

**football-data.org retries:** `FD_MAX_RETRIES = 4`, base sleep `1.5s`, exponential backoff on 429.
**API-Football retries:** `AF_MAX_RETRIES = 4`, base sleep `1.2s`, exponential backoff on 429.

### Result calculation

```python
def market_result(market: str, home_goals: int, away_goals: int) -> str:
    total = home_goals + away_goals
    if market == "O1.5": return "W" if total >= 2 else "L"
    if market == "O2.5": return "W" if total >= 3 else "L"
    if market == "O3.5": return "W" if total >= 4 else "L"
    if market == "BTTS": return "W" if home_goals >= 1 and away_goals >= 1 else "L"
    return None
```

Push (`"P"`) is never generated automatically. It is written manually by the user for voided bets.

### Profit calculation

```python
def calc_profit(resultado: str, stake: float, odd: float) -> float:
    if resultado == "W": return round(stake * (odd - 1.0), 2)
    if resultado == "L": return round(-stake, 2)
    if resultado == "P": return 0.0
```

`Lucro€` uses the model stake and model odd.
`LucroReal€` uses the user-entered `StakeReal€` and `OddReal` (only computed if `Apostada` is truthy and both real fields are present).

**Final score (`Placar`, Phase 26.19).** Alongside `Resultado` and `Lucro€`, both settlement write sites also write `Placar` — `f"{home_goals}-{away_goals}"` (e.g. `"2-1"`) — from the exact fixture data already used to compute `market_result()`. This is a plain additive column in `CSV_COLUMNS`: existing rows without it (from before this phase) read back as `""` via `ensure_columns()`, and it is written going forward for both bot picks and manual bets. It exists primarily to support the manual bet Rejected History view (`03_Dashboard.md` §9), which needs the actual final score as an analytical field, but is populated identically for bot picks since the settlement engine is shared (ADR-002/ADR-009) — no bot-pick-specific code was added.

### Team name matching

Fixture matching uses a multi-stage pipeline:

1. **Exact canonical match:** both teams normalise to the same canonical pair → accept.
2. **Scored fuzzy match:** `score_fixture_match()` computes `home_similarity + away_similarity + bonus`:
   - `similarity_score()` uses `SequenceMatcher` + Jaccard set similarity + substring checks.
   - Bonus of +10 per team for exact canonical match.
   - Accept if `total ≥ MATCH_MIN_TOTAL_SCORE (140)` AND `home_score ≥ 62` AND `away_score ≥ 62`.
3. **Team alias learning:** When a high-confidence match (`score ≥ 94`) is found, the raw name → canonical name mapping is saved to `team_alias_cache.json` for future runs.
4. **Date-minus-1 fallback:** For late-kickoff US/Asian fixtures where the API uses UTC dates, the previous calendar day is also fetched if no match is found.

### Provider error handling (Phase 26.18)

**Background:** in July 2026, the API-Football subscription lapsed to the Free plan. API-Football responded to every `/fixtures` request with HTTP 200 and an empty `response: []`, but with a non-empty `errors.plan` field explaining the season wasn't covered. `update_dataframe()` had no way to tell that apart from "no games today" — every currently-open pick in a non-EU league (which routes through API-Football, either directly or as a football-data.org fallback) came back `NO_MATCH`, and the dashboard reported "No matches to settle." even though the provider never actually looked at a single fixture. This was root-caused via a temporary, read-only audit of the live pipeline (no code or data changed) that traced the failure to `fetch_api_football_fixtures_for_league_date()` returning `([], "")` for every request. Fixing the subscription made settlement work immediately with no code change — proving the settlement/matching logic itself was never broken.

**What changed:** both API clients now validate a response *before* treating it as a real (possibly empty) result:

- **API-Football:** `api_football_get()` inspects the `errors` field of every HTTP 200 response. If it contains anything meaningful (checked via `_extract_meaningful_errors_field()`), it raises `ProviderError` instead of returning the response — this is what catches the plan/quota/auth rejection that used to masquerade as zero fixtures.
- **Both providers:** genuine HTTP failures (401/403/429/5xx) are classified via `classify_provider_error(status_code, message_text)`, which prefers the message body's content (`"plan"`/`"season"` → `PLAN_LIMIT`, `"quota"`/`"rate limit"` → `QUOTA_EXCEEDED`, `"token"`/`"auth"` → `AUTHENTICATION`, ...) and falls back to the HTTP status code when the body carries no usable text.
- Every failure — the new `ProviderError` path and the pre-existing HTTP-error paths — is normalized into one record shape (`build_provider_error()`): `{provider, endpoint, request, category, message, retryable, timestamp}`, printed via `log_provider_error()` (a `[API-FOOTBALL]` / `[FOOTBALL-DATA.ORG]` block with endpoint/category/message — always on, not gated behind `UPDATE_RESULTS_DEBUG`), and appended to `shared_state["provider_errors"]`.
- Successes are tracked too, via `record_provider_success(shared_state, provider)` — this is what lets `update_provider_health()` tell "this provider failed this run" apart from "this provider wasn't used this run".

**Existing return-value contracts are unchanged.** `fetch_api_football_fixtures_for_league_date()` and `fetch_matches_for_league_date()` still return `(fixtures_or_None, reason_string)` / raise the same exception types as before for every pre-existing failure path (`"HTTP {code}"`, `"OTHER"`, `"NO_LEAGUE_ID"`); `update_dataframe()`'s precheck/matching/decision logic was not touched. The only new *behavioural* difference is the specific "HTTP 200 + meaningful `errors`" case, which previously produced `([], "")` (silently treated as a real empty result) and now produces `(None, "PROVIDER_ERROR")` (treated as a failed fetch, same code path as any other provider failure).

**Settlement summary:** `build_settlement_result()` (called by both `run_settlement_remote()` and `main()`) adds `provider_errors` to the response whenever any were recorded this run, and additionally sets `settlement_aborted` / `abort_provider` / `abort_category` / `abort_reason` when `updated == 0` — see §4 `POST /run-settlement` for the exact response shape. `pick_primary_provider_error()` prefers a non-retryable error (PLAN_LIMIT/AUTHENTICATION/INVALID_REQUEST — a retry won't fix these) over a retryable one (QUOTA_EXCEEDED/NETWORK/SERVER_ERROR) when choosing which one to surface.

**Provider health persistence:** `update_provider_health()` writes `cloud_state.json["providerHealth"]` — `{provider: {status, consecutiveFailures, lastError, lastSuccessAt, lastCheckedAt}}` — so the failure state survives across the stateless Railway server's requests (per ADR-003) without a second persistence file (per ADR-008's spirit; see ADR-011). A provider's `status` flips from `"ok"` to `"warning"` after `PROVIDER_HEALTH_WARNING_THRESHOLD` (2) consecutive runs where it failed at least once, and resets to `"ok"` on the next run where it succeeds at least once. Providers not contacted in a given run keep their previous entry untouched. `cloud_state.json` is saved whenever a provider was contacted this run (success or failure), even if zero bets were newly settled — this is the run where a provider health change is most important to persist.

### Postponed/cancelled/missing-fixture voiding (Phase 26.43 — see ADR-017)

**Problem this closes:** before this phase, a fixture that never reached `FT`/`AET`/`PEN` stayed unresolved forever, regardless of *why* — a postponed match, a cancelled one, or one the settlement lookup simply could never locate (the concrete case: Chicago Fire vs Vancouver Whitecaps, 2026-07-17, flagged by the Phase 26.42 investigation) all looked identical to "still to be played". Real-money exposure had no path to closure.

**Status classification** (`classify_af_status()` / `classify_fd_status()` in `update_results.py`) extends the existing `AF_FINISHED_STATUS`/`FD_FINISHED_STATUS` sets with three more buckets, checked in this priority order:

| Bucket | API-Football statuses | football-data.org statuses | Void-eligible? |
|---|---|---|---|
| `FINISHED` (pre-existing) | `FT`, `AET`, `PEN` | `FINISHED` | Settles normally — never a void candidate |
| `IN_PROGRESS` | `1H`, `HT`, `2H`, `ET`, `BT`, `P`, `LIVE` | `IN_PLAY`, `PAUSED` | Never — the crucial safety rule (a status must not become `P` merely because it isn't `FT`) |
| `NON_PLAYED` | `PST`, `CANC`, `ABD` | `POSTPONED`, `CANCELLED` | Yes — after `POSTPONED_VOID_AFTER_HOURS` since original kickoff |
| `SCHEDULED_UNKNOWN` (default) | `NS`, `TBD`, `SUSP`, `INT`, anything unrecognised | `SCHEDULED`, `TIMED`, `SUSPENDED`, anything unrecognised | Never automatically — only the 24h manual fallback applies |

**`SUSP`/`INT`/`SUSPENDED` are deliberately *not* void-eligible at any age**, and fall through to the same default `SCHEDULED_UNKNOWN` bucket as `NS`/`TBD` — a pre-commit safety audit corrected this from an earlier version of the classification that grouped them with `PST`/`CANC`/`ABD`, after finding it could void a wager whose match was suspended/interrupted but still going to legitimately resume and finish (e.g. interrupted Monday, resumes and finishes Friday — the 48h mark lands mid-week). Unlike `PST`/`CANC`/`ABD` (each a reasonably final "this fixture will not complete" determination per API-Football's own semantics), a suspended/interrupted match commonly resumes under the *same* fixture ID. `AF_SUSPENDED_INTERRUPTED_STATUS`/`FD_SUSPENDED_INTERRUPTED_STATUS` document this explicitly in `update_results.py` (not consulted by the classifiers — purely so a future edit doesn't silently re-add them to `*_NON_PLAYED_STATUS`). The 24h manual fallback remains available for a suspended/interrupted fixture the user knows the real bookmaker has already voided. See ADR-017's "Correction" section for the full reasoning. `AWD`/`WO` (technical loss/walkover) are deliberately left unclassified (too rare, unreliable goal data) — they remain open, reachable only via manual void.

**Automatic void — explicit non-played status (Part 3):** inside `try_update_row_via_api_football()` and the football-data.org branch of `update_dataframe()`, once a fixture is matched but its status is `NON_PLAYED`, the row's own persisted `KickoffUTC` (the **original** scheduled kickoff — never overwritten while a pick remains unresolved) is compared against `POSTPONED_VOID_AFTER_HOURS` (default 48h). Below the threshold, behaviour is unchanged (skip, `NOT_FINISHED`). At/above it, `void_result_row()` writes `Resultado="P"`, `Placar=""`, `Lucro€="0.0"` (reusing the existing `calc_profit()`/`calc_real_profit()` — no new financial arithmetic) plus `SettlementReason` (`postponed_timeout`/`cancelled_timeout`/`abandoned_timeout`, mapped from the specific status).

**Automatic void — persistent missing fixture (Part 4/5):** a genuine `NO_MATCH` (fixtures fetched successfully; team-name matching found nothing — never a provider error, which is a different reason string and never reaches this path) increments a persisted `MissingAttempts` counter on the row. `_evaluate_missing_fixture_void()` only proceeds to void once **all** of: `MISSING_FIXTURE_VOID_AFTER_HOURS` (default 72h) has elapsed since original kickoff; `MissingAttempts >= missing_fixture_min_attempts` (default 3); and a final, bounded rediscovery search (`attempt_rediscovery_af()` — AF only, forward-only, `+2..+14` days from original kickoff, reusing `fetch_api_football_fixtures_for_league_date()`'s own per-run `(league, date)` cache so multiple mature candidates in the same league share requests) also finds nothing. If rediscovery finds the fixture already finished, it settles normally (`W`/`L`, `SettlementReason` stays blank — this is a real result, not a void). If it finds the fixture not yet finished, the bet keeps waiting and `MissingAttempts` resets to 0. Only if rediscovery finds nothing does the row void as `P` with `SettlementReason="missing_fixture_timeout"`.

`try_update_row_via_api_football()`'s three call sites inside `update_dataframe()` were consolidated into one nested helper, `_run_af_and_account()`, which is also the single place the missing-fixture safeguard is invoked — so it applies identically regardless of which fallback path produced the `NO_MATCH`.

**Manual void (Part 6/7):** a Live Center-only fallback ("Anular aposta" — `manualVoidBet()` in `index.html`), available on any still-unresolved approved bet once `manual_void_available_after_hours` (default 24h) has passed since its own original kickoff — gated purely on elapsed time, independent of provider status. Requires an explicit PT-PT confirmation and writes the identical `P` result plus `SettlementReason="manual_void"`, through the same `settleManualBet()`/`settleBotBet()` mutation the pre-existing generic quick-settle `P` button already used (that button remains unrestricted and unchanged — it never stamps a reason, and is a different entry point for a different purpose: "I already know the result" vs. "the real bookmaker already voided this").

**Manual bets — evidence must survive across runs.** `manual_bets_to_settlement_df()`/`apply_df_results_to_manual_bets()` bridge `SettlementReason`/`MissingAttempts` exactly like `Placar`/`KickoffUTC` (Phase 26.19/26.32). `apply_df_results_to_manual_bets()` now returns `(newly_settled, evidence_changed)` — both `run_settlement_remote()` and `main()` save `cloud_state.json` whenever `evidence_changed > 0`, even if nothing newly settled and provider health didn't change, because `MissingAttempts` must persist for the safeguard to ever mature for a manual bet.

**Configuration (Part 12):** all three hour thresholds plus the missing-fixture attempt minimum live in `config.json["settlement"]["void_policy"]`, read via `src.config.get_void_policy()` (defensive per-key validation, falling back to a `DEFAULT_*` constant in `src/config.py` on anything missing/invalid/non-positive) — the same pattern every other config-driven value in this project already uses (ADR-010). The dashboard reads the one value it needs (`manual_void_available_after_hours`) via `loadVoidPolicyConfig()` in `index.html`, reusing the same GitHub raw-content `config.json` fetch Scout's `loadModelConfig()` already established — not a second config-loading mechanism, not a Railway round-trip.

**Audit-trail merge for the manual-bot bridge case (pre-commit audit correction).** `getRowWithLocalEdits()` (`index.html`) resolves `SettlementReason` with the exact same branch condition it already uses for `resultadoFinal` — if the CSV has a real result (`W`/`L`/`P`), the CSV's own `SettlementReason` wins (even when blank, e.g. a normal win); only while the CSV cell is still empty does `edit.settlementReason` (the local manual-void bridge, set by `manualVoidBet()`) apply. This is deliberately *not* an independent "non-empty value wins" fallback — an initial fix attempt used that shape and was caught by its own regression test showing a stale "Anulada manualmente" reason persisting next to a CSV-authoritative `W`. Every downstream consumer (`getFilteredRealClosedRows()`, History's "Motivo" line) reads the already-merged `SettlementReason` off the row object — no special-casing needed at the read site.

**`picks_history.csv` schema drift — a pre-existing bug this phase's audit found already active in production.** `src/history.py`'s `HISTORY_COLUMNS` — a separate, hardcoded schema list consumed by `load_history()`/`ensure_simple_columns()`/`merge_into_history()` (the path `main.py`'s daily generation calls via `persist_history()` — not `update_results.py`'s settlement engine) — was never updated when `Placar` was added (Phase 26.19). `ensure_simple_columns()`'s reindex (`df[HISTORY_COLUMNS]`) silently stripped `Placar` from every settled row on each daily generation cycle; confirmed against real production data (90 of 93 settled rows in the live file had an empty `Placar` at audit time). `SettlementReason`/`MissingAttempts` were exposed to the identical erasure path. Fixed by adding all three fields to `HISTORY_COLUMNS`, plus explicit blank-column assignments in `src/pipeline.py`'s `save_all_outputs()` — a second, separate consumer that reindexes to `HISTORY_COLUMNS` directly (no add-if-missing safety net) and would otherwise raise `KeyError` on every generation run once the schema grew. **Preventative only** — does not reconstruct already-lost historical `Placar` values (see `05_Known_Issues.md`).

See ADR-017 for the full reasoning (including the "Correction" section covering all three points above), `tests/test_void_policy.py` for the void-policy regression suite, and `tests/test_history_schema.py` for the schema-drift regression suite.

---

## 8. League Registry

`src/league_registry.py` is the single source of truth for all league metadata. All settlement routing structures are automatically derived from it.

### Structure

```python
@dataclass(frozen=True)
class LeagueEntry:
    key: str            # config.json internal key (e.g. "premier")
    name: str           # CSV display name (e.g. "Premier League")
    country: str        # 3-char ISO (e.g. "ENG")
    fd_code: str | None # football-data.org code; None = no FD coverage
    fd_blocked: bool    # True = FD exists but returns 403; bypass FD
    af_country: str     # API-Football /leagues?country= value
    af_name: str        # API-Football competition name for fuzzy match
    af_id: int | None   # Hardcoded AF league ID; skips /leagues API call
    season_model: str   # "european" or "calendar"
```

### Automatically derived structures

| Structure | Derived from | Consumed by |
|---|---|---|
| `LEAGUE_CODE_MAP` | All entries → `{name: settlement_code}` | `update_dataframe()` — maps CSV "Liga" column to settlement routing code |
| `BLOCKED_FOOTBALL_DATA_CODES` | Entries where `fd_blocked=True` OR `fd_code=None` | `should_use_api_football_fallback()` — routes to API-Football directly |
| `API_FOOTBALL_FALLBACK_COMPETITIONS` | All entries → `{code: {country, name, af_id}}` | `get_api_football_league_id()` and `fetch_api_football_fixtures_for_league_date()` |
| `AF_SEASON_MODELS` | Entries with `af_id` → `{af_id: season_model}` | `api_football_season_from_date()` |
| `REGISTRY_BY_KEY` | All entries → `{key: LeagueEntry}` | `_resolve_liga_display_name()` in manual bet settlement |

### Season models

**`"european"` (default):** The season year is the calendar year the season starts (August). Games in January–June belong to the previous year's season. Example: a game on 2026-02-15 → season 2025.

**`"calendar"`:** The season year is the calendar year the game is played. Used for: Eliteserien, Allsvenskan, Veikkausliiga, Besta deild, MLS, MLS Next Pro, Campeonato Brasileiro, J1 League, K League 1.

```python
def api_football_season_from_date(date_str, league_id=None, shared_state=None) -> int:
    model = AF_SEASON_MODELS.get(league_id, "european")
    if model == "calendar":
        return year
    return year if month >= 7 else year - 1
```

### Hardcoded AF league IDs

When `af_id` is set in the registry entry, `get_api_football_league_id()` returns it directly without making an API call to `/leagues`. This saves one API request per league per settlement run.

### Adding a new league

1. Add a `LeagueEntry` row to `REGISTRY` in `src/league_registry.py`.
2. Add the league to the `leagues` section of `config.json`.
3. Add the league ID to the `api_football.league_ids` section of `config.json`.
4. Place a history CSV for the league at `data_raw/{key}.csv`.

That is all. `LEAGUE_CODE_MAP`, `BLOCKED_FOOTBALL_DATA_CODES`, `API_FOOTBALL_FALLBACK_COMPETITIONS`, `AF_SEASON_MODELS`, and `REGISTRY_BY_KEY` are all regenerated automatically on the next import.

**Do not** add league mappings to `update_results.py`, `config.json` (beyond the two sections above), or any other file.

### Registering two genuinely distinct competitions that share a colloquial name

`fetch_oddsapi_fixtures.py` (Phase 1 fixture fetch) never imports `league_registry.py` — it decides which leagues to fetch fixtures for purely from `config.json`'s `leagues` / `api_football.league_ids` sections (steps 2–3 above). A `REGISTRY` entry therefore only gives a competition a settlement identity; both a registry entry *and* a `config.json` entry are required for it to actively generate picks. Senior MLS (`"mls"`, `af_id=253`) and MLS Next Pro (`"mls_next_pro"`, `af_id=909`) are genuinely distinct API-Football competitions that both happen to be branded "MLS" colloquially — both are fully registered in both places (Phase 26.42, see ADR-004 update), so each is independently and simultaneously eligible for fixture fetching, generation, and settlement. Keeping them as two registry entries with two `af_id`s is what prevents the settlement engine from ever querying one competition's fixtures for a bet placed on the other; it is not a mechanism for excluding either one from generation.

### Fixture-generation league IDs must never be silently substituted

Prior to Phase 26.42, `fetch_oddsapi_fixtures.py::fetch_fixtures_for_league_date()` retried a zero-fixture response by fuzzy-searching API-Football's `/leagues` for a name match against the configured league's short name — intended as an auto-discovery fallback, but capable of silently resolving to a *different* competition whenever the configured (correct) ID legitimately had no fixtures for that date. This produced a real production incident: MLS Next Pro fixtures were substituted for senior MLS and mislabelled `"MLS"` for weeks, undetected (see `05_Known_Issues.md` SETTLEMENT-3). This fallback has been removed: a configured canonical league ID (from `config.json` or `DEFAULT_LEAGUE_IDS`) is now authoritative, and a zero-fixture response for a date means no fixtures that day, never "try a different competition." `search_league_id_by_api()` remains defined as a general-purpose lookup but is not called from the per-date fetch path — do not reconnect it as an automatic fallback.

---

## 9. External APIs

### football-data.org

**Purpose:** Primary settlement source for EU leagues: Premier League (`PL`), LaLiga (`PD`), Ligue 1 (`FL1`), Serie A (`SA`), Eredivisie (`DED`), Championship (`ELC`).

**Authentication:** `X-Auth-Token: {FOOTBALL_DATA_API_KEY}` header.

**Usage (settlement only):**
```
GET https://api.football-data.org/v4/competitions/{code}/matches?dateFrom={date}&dateTo={date}
```
Returns all matches for the league on the given date. Settlement iterates rows from the CSV and looks up the matching fixture by team name.

**Fallback behaviour:** On HTTP 403 (access blocked), the league is routed to API-Football fallback. On HTTP 429 (rate limit), exponential backoff is applied for up to `FD_MAX_RETRIES = 4` attempts.

**Limitations:** 10 requests/minute on the free plan. `FD_CALL_MIN_INTERVAL = 0.65s` enforced by `_respect_fd_api_spacing()`. Cache per `(league_code, date)` pair within a single settlement run to avoid redundant requests.

---

### API-Football

**Purpose:**
1. **Fixture fetching (generation):** `fetch_oddsapi_fixtures.py` calls `/fixtures` for all 22 leagues to build the shortlist. Calls `/odds` for each shortlisted fixture to get O2.5 and BTTS odds.
2. **Settlement:** Used for all EU-blocked leagues and all non-EU leagues. Also used as a fallback when football-data.org fails or returns no match.

**Authentication:** `x-apisports-key: {API_FOOTBALL_KEY}` header.

**Base URL:** `https://v3.football.api-sports.io`. Configurable via `API_FOOTBALL_BASE`.

**Key endpoints:**

| Endpoint | Usage | Called by |
|---|---|---|
| `/fixtures?league={id}&season={year}&date={date}` | Fixture data for a league on a date | `fetch_oddsapi_fixtures.py`, `update_results.py` |
| `/odds?fixture={id}` | Market odds for a specific fixture | `fetch_oddsapi_fixtures.py` |
| `/leagues?country={c}&season={year}` | Look up league ID by country + name | `update_results.py` (when `af_id` is not set) |

**Fallback behaviour:** On HTTP 429, exponential backoff for up to `AF_MAX_RETRIES = 4` attempts. On other HTTP errors, classifies as `"HTTP {code}"` reason and routes to fallback logic. On date mismatch (late-kickoff UTC games), retries with `date - 1 day`.

**Limitations (paid plan):** 7500 requests/day, 300 requests/minute. Configured via Railway environment variables. `AF_CALL_MIN_INTERVAL = 0.50s` enforced by `_respect_af_api_spacing()`. In `fetch_oddsapi_fixtures.py`, an additional `sleep_seconds_between_fixture_requests = 0.35s` sleep is applied between fixture requests.

---

### Telegram Bot API

**Purpose:** Send pick summaries to the user after each generation run.

**Authentication:** Bot token in URL: `https://api.telegram.org/bot{TOKEN}/sendMessage`.

**Usage:** `process_notifications()` builds a Telegram message from the new picks and calls `_send_in_chunks()` to stay within the 4096-character message limit. One message per market (O2.5, BTTS) if picks exist.

**Deduplication:** `sent_state.json` stores a set of pick IDs already sent. Each pick ID is `{league}|{home_team}|{away_team}|{market}|{date}`. Picks already in the set are skipped. The set is persisted after each run.

**Failure behaviour:** Telegram errors are caught and printed. A Telegram failure does not abort the pipeline — picks are still generated and committed.

---

### GitHub Contents API

**Purpose:** All persistent file reads and writes.

**Authentication:** `Authorization: Bearer {GITHUB_TOKEN}` or `Authorization: token {GITHUB_TOKEN}` (both formats used in different callers).

**Key operations:**

| Operation | Endpoint | When |
|---|---|---|
| Read file content + SHA | `GET /repos/{owner}/{repo}/contents/{path}?ref={branch}` | Before every write; on `/load` |
| Write file | `PUT /repos/{owner}/{repo}/contents/{path}` (body: base64 content + SHA + message) | After settlement, generation, save |

**Error handling:** HTTP 404 returns `None, None` (file does not exist). HTTP 422 means SHA mismatch (concurrent write conflict). Other errors propagate as exceptions.

---

## 10. Configuration

### `config.json` (code configuration)

`config.json` is checked into the repository. It is loaded at startup by `src/config.py:load_config()` and consumed by all pipeline scripts.

**Key sections:**

| Section | Key fields | Purpose |
|---|---|---|
| `run` | `days_ahead`, `mode`, `max_picks_per_day`, `max_picks_global` | Pipeline run parameters |
| `bankroll` | `over25`, `btts` | Bankroll amount per market for Kelly sizing |
| `history` | `window`, `decay`, `min_games_home`, `min_games_away`, `lambda_boost` | Poisson model parameters |
| `history.league_lambda_boost` | Per-league overrides | Disables boost for specific leagues |
| `rules.over25` / `rules.btts` | `edge_min`, `edge_max`, `kelly_fraction`, `cap_frac`, `daily_cap_frac` | Market rules and staking parameters |
| `calibration` | `btts_probability_adjustment` | Global BTTS probability scaling factor (0.885) |
| `api_football` | `league_ids`, `shortlist_total`, `shortlist_per_league_per_day`, `sleep_seconds_between_fixture_requests`, `use_api_football_for_btts_odds` | API-Football behaviour |
| `league_overrides` | Per-league rule overrides | Fine-tune edge thresholds for specific leagues |
| `leagues` | Per-league `name` and `country` | Display names and country codes |
| `settlement.void_policy` | `postponed_void_after_hours`, `missing_fixture_void_after_hours`, `manual_void_available_after_hours`, `missing_fixture_min_attempts` | Postponed/cancelled/missing-fixture void thresholds (Phase 26.43, ADR-017) — read via `src.config.get_void_policy()` |
| `the_odds_api` | Sport keys, regions, markets | The Odds API config (legacy, kept for reference) |

### Default values (`src/config.py`)

Hardcoded defaults used when a config key is absent:

| Constant | Value |
|---|---|
| `DEFAULT_MAX_PICKS_PER_DAY` | 12 |
| `DEFAULT_MAX_PICKS_GLOBAL` | 36 |
| `DEFAULT_KELLY_FRACTION` | 0.18 |
| `DEFAULT_CAP_FRAC` | 0.04 |
| `DEFAULT_DAILY_CAP_FRAC` | 0.12 |
| `DEFAULT_MAX_ODD_O25` | 2.20 |
| `DEFAULT_MAX_ODD_BTTS` | 2.30 |
| `DEFAULT_BTTS_PROBABILITY_ADJUSTMENT` | 0.885 |
| `DEFAULT_POSTPONED_VOID_AFTER_HOURS` | 48 |
| `DEFAULT_MISSING_FIXTURE_VOID_AFTER_HOURS` | 72 |
| `DEFAULT_MANUAL_VOID_AVAILABLE_AFTER_HOURS` | 24 |
| `DEFAULT_MISSING_FIXTURE_MIN_ATTEMPTS` | 3 |

### Environment variables

All secrets and deployment-specific settings are environment variables, not in `config.json`.

| Variable | Where set | Consumed by |
|---|---|---|
| `GITHUB_TOKEN` | Railway env, GitHub Actions secrets | `sync_server.py`, `update_results.py`, `fetch_oddsapi_fixtures.py`, `src/integrations.py` |
| `GITHUB_OWNER` | Railway env (default: `jorgepita`) | `sync_server.py` |
| `GITHUB_REPO` | Railway env (default: `apostas-over-futebol`) | `sync_server.py` |
| `GITHUB_BRANCH` | Railway env (default: `main`) | `sync_server.py` |
| `FOOTBALL_DATA_API_KEY` | Railway env, GitHub Actions secrets | `update_results.py` |
| `API_FOOTBALL_KEY` | Railway env, GitHub Actions secrets | `update_results.py`, `fetch_oddsapi_fixtures.py` |
| `API_FOOTBALL_BASE` | Railway env (default: `https://v3.football.api-sports.io`) | `fetch_oddsapi_fixtures.py` |
| `TELEGRAM_TOKEN` | GitHub Actions secrets | `src/pipeline.py` |
| `CHAT_ID` | GitHub Actions secrets | `src/pipeline.py` |
| `UPDATE_RESULTS_DEBUG` | Set to `1` to enable verbose settlement logging | `update_results.py` |

**Values that belong in config rather than hardcoded:**
- API rate limits (`shortlist_total`, `sleep_seconds_between_fixture_requests`) — live in `config.json` under `api_football`.
- Bankroll amounts — live in `config.json` under `bankroll`.
- Kelly fraction and edge thresholds — live in `config.json` under `rules`.
- GitHub coordinates (`owner`, `repo`, `branch`) — live in Railway environment variables.

---

## 11. Persistent Files

| File | Owner | Producer | Consumers | Write frequency | Read frequency |
|---|---|---|---|---|---|
| `picks_hoje_simplificado.csv` | GitHub Actions | `main.py` (via `save_all_outputs()`); `run_topup.py` (append) | `update_results.py` (settlement) | Once per generation run | Once per settlement run |
| `picks_hoje_github.csv` | GitHub Actions | `main.py` (via `save_all_outputs()`); `run_topup.py` (append) | Browser (daily picks) | Once per generation run | Every 60 seconds (dashboard) |
| `picks_btts.csv` | GitHub Actions | `main.py` (via `save_all_outputs()`); `run_topup.py` (append) | Browser (daily BTTS picks) | Once per generation run | Every 60 seconds (dashboard) |
| `picks_history.csv` | GitHub Actions | `update_results.py` (settlement); `main.py` (via `persist_history()`) | `update_results.py`, browser (history page) | Twice daily (settlement) + once daily (generation) | Twice daily (settlement) + every 60 seconds (dashboard) |
| `cloud_state.json` | Railway (browser-initiated) | `sync_server.py POST /save`; `update_results.py` (manual settlement; provider health) | `sync_server.py GET /load`; `update_results.py` (manual settlement); browser (via Railway) | On every user state change (debounced 4s); after manual settlement; whenever a settlement run contacts any provider (`providerHealth`, even with 0 newly-settled bets — see §7) | On dashboard startup; on "Load Cloud"; after settlement |
| `fixtures_today.csv` | GitHub Actions | `fetch_oddsapi_fixtures.py` | `main.py` (pick generation); browser (Scout kickoff lookup) | Once per generation run | Once per generation pipeline; on demand from browser |
| `picks_history.csv` | GitHub Actions | `update_results.py` (settlement); `main.py` (via `persist_history()`) | `update_results.py`; browser; `src/league_stats.py` | Multiple times daily | Multiple times daily |
| `league_stats.csv` | GitHub Actions | `src/league_stats.update_league_stats()` (regenerates), uploaded via `_persist_league_stats()` (settlement, `update_results.py::main()`) or `upload_outputs()` (generation, `main.py`) — see Phase 26.44/ADR notes below | Browser (Analytics → "Desempenho por Liga") | After every settlement (`main()`, 07:00/22:30 UTC) + generation (`main.py`, 17:00 UTC + 23:00 UTC top-up) run | On dashboard startup |
| `sent_state.json` | GitHub Actions | `src/state.save_sent_state()` | `src/state.load_sent_state()` | After each generation run | Before each generation run |
| `team_alias_cache.json` | Railway / GitHub Actions | `save_team_alias_cache()` (after settlement) | `load_team_alias_cache()` (at settlement start) | After settlement when new aliases are learned | At settlement start |
| `data_raw/{league_key}.csv` | Manual / external | External (football-data.org historical download, `fetch_historical.py`) | `fetch_oddsapi_fixtures.py`; `main.py` (via `src/pick_generation.py`) | Infrequent (manual refresh) | Every generation run, per league |
| `picks_over25.csv` | GitHub Actions | `main.py` (via `save_all_outputs()`) | Not consumed by settlement or dashboard directly | Once per generation run | Rarely |
| `picks_hoje.csv` | GitHub Actions | `main.py` (via `save_all_outputs()`) | Not consumed by settlement or dashboard directly | Once per generation run | Rarely |

**Derived-file persistence invariant (Phase 26.44).** `league_stats.csv` is a *derived* production artifact — recomputed from `picks_history.csv` — not user input. Whenever a production path regenerates it via `update_league_stats()`, that regeneration must also be uploaded to GitHub in the same run; a local-only write on an ephemeral GitHub Actions runner has zero durable effect. Before this phase, both production call sites (`update_results.py::main()`'s settlement path and `main.py`'s generation path, via `src/pipeline.py::persist_history()`) recomputed the file locally but never uploaded it, leaving it frozen at a 2026-05-24 snapshot for ~2 months of continuous settlement/generation activity — see `05_Known_Issues.md` (resolved) and ADR update below. `update_results.py::run_settlement_remote()` (the Railway on-demand "Executar Resolução" path) does **not** call `update_league_stats()` at all and is unaffected by this fix — `league_stats.csv` is only ever refreshed by the two scheduled GitHub Actions paths above, consistent with how it worked (when it worked) before this phase.

A narrow, read-only audit for the same pattern elsewhere found `sent_state.json` and `team_alias_cache.json` are *also* written locally-only with no GitHub upload call in either writer (`src/state.save_sent_state()`, `update_results.py::save_team_alias_cache()`) — both files' last commits (`b7b4f5c4` and `ce963111` respectively) predate or coincide with `league_stats.csv`'s own last commit, suggesting a repeated pattern rather than an isolated omission. **Not fixed in this phase** — explicitly out of scope; flagged here for a future, separately-scoped investigation. Unlike `league_stats.csv`, neither file is directly user-visible in the dashboard, so the practical impact (if any) is different and needs its own assessment before a fix is designed.

---

## 12. Error Handling

### GitHub fails

**During settlement (GitHub Actions):** If `upload_csv_to_github()` fails, the exception propagates and the GitHub Actions job fails. The local files (in the checked-out workspace) are left with the updated results. The next run will re-read the local stale CSVs.

**During settlement (Railway / `run_settlement_remote()`):** If the download or upload fails, the function raises and the HTTP response is HTTP 500. The tempdir is cleaned up. No partial results are written.

**During generation:** If `upload_csvs_to_github()` fails, the job prints a warning and continues. Picks are generated locally but not committed. The next generation run will overwrite them.

**SHA conflict:** GitHub returns HTTP 422. The exception propagates. The caller receives HTTP 500. The file on GitHub is unchanged.

### Railway fails

If Railway is down or slow, all browser operations that require Railway (`/load`, `/save`, `/run-settlement`) fail with network errors. The browser shows the cloud status as "unavailable". The 60-second CSV auto-refresh continues unaffected (it reads from GitHub raw URLs, not Railway).

### football-data.org fails

**HTTP 403:** The league is routed to API-Football fallback if it has one (`API_FOOTBALL_FALLBACK_COMPETITIONS`). If it does not, the pick is skipped.

**HTTP 429:** Exponential backoff for up to 4 retries (1.5s, 3s, 4.5s, 6s). After 4 failures, propagates exception. The cache prevents re-fetching the same league+date.

**Other errors:** Marked as `"OTHER"` in the cache. If the league has an API-Football fallback, it is used. Otherwise the pick is skipped.

**Every one of the above (Phase 26.18):** in addition to the existing skip/fallback behaviour (unchanged), the failure is classified (`classify_provider_error()`) and recorded as a normalized provider error — see §7 "Provider error handling".

### API-Football fails

**HTTP 429:** Exponential backoff for up to 4 retries. After all retries exhausted, the pick is skipped with reason `"AF_429"`.

**No fixtures found:** Picks for that league on that date are skipped. The settlement run reports `no_match_found` count in the summary log.

**No match found:** Tried the previous calendar day (date-minus-1 fallback for late UTC kickoffs). If still no match: pick is skipped.

**During generation (`fetch_oddsapi_fixtures.py`):** League is skipped with a `[FIXTURE SKIP]` log line. The remaining leagues continue.

**HTTP 200 with a meaningful `errors` field (Phase 26.18):** previously indistinguishable from "no fixtures today" — API-Football returns 200 with an empty `response` and puts the real reason (wrong plan tier, exceeded quota, bad auth) in `errors`. This is what happened in July 2026 when the subscription lapsed to the Free plan: every non-EU-league pick silently got `NO_MATCH` and the dashboard reported "No matches to settle." with zero indication anything was wrong. `api_football_get()` now raises `ProviderError` for this case instead of returning the response, which `fetch_api_football_fixtures_for_league_date()` turns into `(None, "PROVIDER_ERROR")` — the same "failed fetch" code path as any other provider error, not a false empty result. See §7 for full detail and `09_Architecture_Decisions.md` ADR-011.

### Settlement fails

**Individual pick:** The pick is skipped with a logged reason (TOO_EARLY, NOT_FINISHED, NO_MATCH, UNSUPPORTED_MARKET, etc.). Other picks in the same run are not affected.

**Manual bet settlement failure:** Wrapped in a `try/except`. A failure in manual bet settlement does not abort bot pick settlement. The warning is printed and the manual settlement section is skipped.

### Generation fails

**`fetch_oddsapi_fixtures.py` fails:** `run_main.py` raises `RuntimeError` and the process exits non-zero. GitHub Actions marks the job as failed. `main.py` is not reached.

**`main.py` fails:** The job fails. Any CSVs already written locally are not uploaded. The previous generation's files remain on GitHub.

---

## 13. Performance and Scalability

### Synchronous settlement

Settlement is synchronous and single-threaded. `update_dataframe()` iterates pick rows sequentially, making one API call per row (cached per `(league, date)` pair so only one call per league per date, not per pick). 

Typical settlement duration (Railway remote):
- Download CSVs from GitHub: ~2–5 seconds
- Bot pick settlement (history + daily): ~20–60 seconds depending on number of open picks and API response times
- Upload CSVs: ~5–10 seconds
- Manual bet settlement: ~10–30 seconds
- **Total: ~40–90 seconds**

### Worker model

One gunicorn worker handles all requests serially. Concurrent requests queue and wait. This is intentional — concurrent settlement calls would produce SHA conflicts on GitHub. The timeout is 300 seconds.

### API usage

**Generation per run (approximate):**
- `fetch_oddsapi_fixtures.py`: 22 leagues × `days_ahead` (5) dates = up to ~110 `/fixtures` calls, plus up to 80 `/odds` calls. Total: up to ~190 API-Football requests per run.
- Two generation runs per day (17:00 main, 23:00 top-up). Top-up is subset of 8 leagues. Approximate total: ~150 + ~60 = ~210 requests/day for generation.

**Settlement per run (approximate):**
- football-data.org: up to 6 leagues × 1 date call = 6 FD requests per settlement run.
- API-Football: up to 13 blocked/non-EU leagues × 1 date call = 13 AF requests per settlement run.
- Two settlement runs per day: ~38 AF requests/day for settlement.

**Total daily API-Football usage:** ~250 requests/day, well within the 7500-request paid plan limit.

### GitHub write frequency

| Event | Files written | Commits created |
|---|---|---|
| Generation (17:00) | picks_over25.csv, picks_btts.csv, picks_hoje.csv, picks_hoje_github.csv, picks_hoje_simplificado.csv, picks_history.csv, league_stats.csv, fixtures_today.csv | 8 |
| Top-up (23:00) | Same files (append mode) | 8 |
| Settlement (07:00, 22:30) | picks_history.csv, picks_hoje_simplificado.csv, cloud_state.json (if manual settled), league_stats.csv | 3–4 |
| Browser save (per user action) | cloud_state.json | 1 |

### Bottlenecks

- **Football-data.org rate limit (10 req/min):** The 0.65s minimum interval between FD calls means settlement for 6 EU leagues takes at least 3.9 seconds of enforced sleeping, plus response time. Settlement at 07:00 can take 30+ minutes if many picks are open across many league-date combinations.
- **API-Football odds fetching:** 80 `/odds` calls at 0.28s intervals = 22+ seconds of minimum sleep in `fetch_oddsapi_fixtures.py`.
- **Single gunicorn worker:** All Railway requests are serialised. A 90-second settlement run blocks all other requests.

### Architectural trade-offs

**GitHub as database:** Gives zero-cost persistence and full version history. The cost is two API calls per write (GET for SHA + PUT), SHA conflict risk under concurrency, and no transactions. Acceptable for this project's write frequency.

**Single worker:** Eliminates write concurrency issues at the cost of request queueing. Acceptable because settlement is user-triggered and infrequent.

**Synchronous settlement:** Simple, debuggable, and correct. The cost is a blocking 40–90 second request. Acceptable because the browser shows a loading state and the user expects to wait.

---

## 14. Backend Design Principles

**Stateless backend.** The Railway server holds no in-process state between requests. Every request reads from GitHub and writes to GitHub. The server can restart at any time without data loss or inconsistency.

**GitHub as the persistence layer.** All durable state lives in files committed to the repository. No separate database is required. Every write is a git commit, giving full version history and the ability to roll back any change by reverting a commit.

**Shared settlement engine.** `update_dataframe()` in `update_results.py` settles both bot picks and manual bets. A manual bet is converted to a DataFrame row, settled by the same function, and converted back. This guarantees that bot and manual results use identical logic and cannot diverge.

**Single source of truth for leagues.** `src/league_registry.py` is the only file that knows about league metadata. All settlement routing structures (`LEAGUE_CODE_MAP`, `BLOCKED_FOOTBALL_DATA_CODES`, `API_FOOTBALL_FALLBACK_COMPETITIONS`, `AF_SEASON_MODELS`) are derived from it automatically. Adding a league requires editing exactly one file.

**Configuration over hardcoding.** Market parameters (edge thresholds, Kelly fraction, cap fractions), API quotas, shortlist sizes, and Poisson model parameters are in `config.json`. API credentials and deployment coordinates are in environment variables. The only values hardcoded in the application are constants unlikely to change without a code change (e.g. `RESULT_READY_DELAY`, `MATCH_MIN_TOTAL_SCORE`).

**Deterministic processing.** The pick generation pipeline is deterministic given the same fixtures and history. The same inputs always produce the same picks. Settlement outcomes are determined solely by the match result data returned by the APIs, not by execution order or timing.

**Minimal duplication.** The same GitHub write pattern appears in three places (`sync_server.py`, `update_results.py`, `fetch_oddsapi_fixtures.py`) because each has different auth handling and error semantics. This is not a violation — they are genuinely different callers. The shared logic lives in `src/integrations.py`.

**Fail loudly at startup.** Both `sync_server.py` and `update_results.py` raise immediately if required environment variables are missing. A misconfigured deployment fails on startup rather than on the first request or the first settlement attempt.

**Idempotent settlement.** Rows with `Resultado` already in `{W, L, P}` are skipped. Re-running settlement on the same data produces the same result. Settlement can be run multiple times without corrupting already-settled picks.

---

## 15. Shared Quantitative Engine (Phase 26.29)

**Canonical implementation:** `src/calculations.py`. Contains every objective statistical calculation the project uses: `compute_lambdas()`, `apply_lambda_boost()`, `prob_over25()`, `prob_btts_yes_adjusted()`/`btts_prob_diagnostics()`, `kelly_fraction()`, `confidence_factor()`, `fair_odds()`, `expected_value()`, and the `clamp_*()` bounds. `src/pick_generation.py` and `src/market_rules.py::apply_stakes()` are its only Python callers.

**JavaScript mirror:** `QuantEngine`, an isolated module in `index.html` between the `QUANT_ENGINE_START`/`QUANT_ENGINE_END` markers, consumed only by the Manual Bet Scout's `analyzeFixture()`. It is a pure module — no DOM, no `state`, no network I/O, no Score/Opinion/Recommendation logic — so it can be extracted and evaluated standalone by a test runner.

**Why two implementations instead of one.** `index.html` has no build step and no framework (ADR-005); a literal single-runtime engine would require either compiling Python to run in the browser (a large WASM runtime for ~150 lines of arithmetic) or having the Scout call a Railway endpoint for every analysis (added latency, offline capability lost, coupling to the single-worker gunicorn process). Both were rejected — see ADR-014.

**Conformance guarantee — golden-vector testing.** `tests/golden_vectors.json` is a frozen set of input → output pairs computed once directly from `src/calculations.py`. Two independent test suites replay the same vectors against each implementation:

```
python -m pytest tests/test_quant_engine_golden.py -v      # Python side (142+ vectors)
node tests/test_quant_engine_golden.js                      # JS side — extracts QuantEngine
                                                              # out of index.html via the
                                                              # marker comments and evaluates
                                                              # it in an isolated Node vm context
```

Both must pass for the two engines to be considered in sync. Neither test requires any dependency beyond what's already in `requirements.txt` (Python) or Node's own standard library (JavaScript — no `npm install`, consistent with ADR-005).

**Updating a formula — required process:**
1. Change the formula in `src/calculations.py` (the canonical implementation) first.
2. Regenerate `tests/golden_vectors.json` by re-running the same input set through the updated Python function (see the vector-generation approach documented inline at the top of `tests/golden_vectors.json`'s sibling test file).
3. Update `QuantEngine` in `index.html` to match.
4. Re-run both conformance suites above — both must pass before the change is considered complete.

**What must never be added to either engine:** Score, Opinion, Recommendation Engine logic, Strategy Lab logic, stake-sizing *decisions* (as opposed to the stake *calculation* `apply_stakes()` performs using the engine's `confidence_factor()`), or any UI/presentation concern. These stay in each consumer — see ADR-014.

**Config as an engine input, not a hardcoded constant.** The JS `QuantEngine.computeLambdas()` takes `window`/`decay`/`minGamesHome`/`minGamesAway` as a parameter rather than reading a module-level default, exactly like the Python `compute_lambdas()` signature. The Scout loads these values (plus `lambda_boost`, `league_lambda_boost`, and `calibration.btts_probability_adjustment`) from `config.json` once per session (`loadModelConfig()`, cached, fetched from the same GitHub raw-content mechanism already used for picks CSVs — not a Railway round-trip), falling back to a frozen copy of the last-known defaults if the fetch fails.
