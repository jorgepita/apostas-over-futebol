# Architecture

This document describes the complete production architecture. It is a technical companion to `00_Project_Context.md`. Read that file first for purpose, philosophy, and constraints.

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GitHub Repository                           │
│  picks_history.csv  picks_hoje_simplificado.csv  cloud_state.json  │
│  sent_state.json    league_stats.csv             manual_bets.csv   │
└───────┬─────────────────────────────────┬───────────────────────────┘
        │ git commit / Contents API        │ Contents API
        │ (writes)                         │ GET / PUT
        ▼                                 ▼
┌───────────────────┐            ┌────────────────────────┐
│   GitHub Actions  │            │    Railway Flask API   │
│   (bot.yml)       │            │    sync_server.py      │
│                   │            │                        │
│  07:00 settlement │            │  GET  /load            │
│  17:00 generation │            │  POST /save            │
│  22:30 settlement │            │  POST /run-settlement  │
│  23:00 top-up     │            │  GET  /health, /       │
└───────┬───────────┘            └──────────┬─────────────┘
        │                                   │ HTTP
        │ HTTP                              ▼
        ▼                        ┌────────────────────────┐
┌───────────────────┐            │  Browser Dashboard     │
│ football-data.org │            │  index.html            │
│ API-Football v3   │◄───────────│                        │
│ (result lookups)  │            │  localStorage (cache)  │
└───────────────────┘            │  60s CSV auto-refresh  │
        │                        │  explicit cloud sync   │
        ▼                        └────────────────────────┘
┌───────────────────┐
│     Telegram      │
│  (notifications)  │
└───────────────────┘
```

Data flow directions:
- **GitHub Actions → GitHub**: commits updated CSVs after settlement and generation.
- **Railway → GitHub**: reads/writes `cloud_state.json` via GitHub Contents API.
- **Browser → Railway**: GET /load to read cloud state; POST /save to write; POST /run-settlement to trigger settlement.
- **Browser → GitHub**: fetches picks CSVs via raw HTTPS URLs (read-only, no auth required).
- **GitHub Actions → result APIs**: queries football-data.org and API-Football to settle picks.
- **GitHub Actions → Telegram**: sends pick notifications after generation.

---

## 2. Component Responsibilities

### GitHub Repository

**Purpose:** The persistence layer. All durable state lives here as files.

**Owns:** `picks_history.csv`, `picks_hoje_simplificado.csv`, `picks_hoje.csv`, `cloud_state.json`, `sent_state.json`, `league_stats.csv`, `manual_bets.csv` (legacy header only).

**Does not own:** Runtime state, browser localStorage, team alias cache (Railway-local), in-memory settlement caches.

---

### GitHub Actions — `bot.yml`

**Purpose:** Scheduled automation host. Runs the pick generation and settlement pipelines on a fixed daily schedule.

**Coordinates:** `fetch_oddsapi_fixtures.py`, `main.py`, `update_results.py`, `run_topup.py`.

**Writes:** `picks_history.csv`, `picks_hoje_simplificado.csv`, `picks_hoje.csv`, `league_stats.csv`, `sent_state.json`.

**Does not own:** `cloud_state.json` (shared with Railway settlement), `manual_bets.csv` (dead).

---

### Railway Flask API — `sync_server.py`

**Purpose:** Always-on HTTP proxy. Bridges `cloud_state.json` between the browser and GitHub, and hosts on-demand settlement.

**Owns:** Nothing persistent. Stateless between requests.

**Responsibilities:**
- `GET /load` — fetch `cloud_state.json` from GitHub, decode, return as JSON.
- `POST /save` — accept JSON body, encode, PUT to GitHub (fetching SHA first).
- `POST /run-settlement` — import and call `update_results.run_settlement_remote()` synchronously.
- `GET /health`, `GET /` — operational status.

**Does not own:** Any file. The Railway filesystem is ephemeral.

---

### Settlement Engine — `update_results.py`

**Purpose:** Single settlement pipeline shared by bot picks and manual bets.

**Core function:** `update_dataframe(df, label, shared_state)` — iterates every row; skips ALREADY_DONE (W/L/P result present), INVALID_ROW, FUTURE_DATE, MISSING_LEAGUE_MAP, UNSUPPORTED_MARKET; queries football-data.org or API-Football for finished matches; writes Resultado and Lucro€.

**Entry points:**
- `main()` — called by GitHub Actions; reads/writes local CSV files from disk.
- `run_settlement_remote()` — called by Railway /run-settlement; downloads/uploads files via GitHub Contents API.

**Does not own:** Pick generation, fixture pre-fetching, Telegram notifications.

---

### Browser Dashboard — `index.html`

**Purpose:** Operational interface. Renders picks, manages manual bets, displays analytics.

**Owns:** `state` object in memory; localStorage copy of `cloud_state.json`.

**Reads from:** Railway API (cloud state), GitHub raw URLs (picks CSVs — no auth).

**Writes to:** Railway API (cloud state via POST /save and POST /run-settlement).

**Does not own:** Any file in the repository. Cannot commit to GitHub directly.

---

### football-data.org

**Purpose:** Primary result provider for EU leagues.

**Used for:** Premier League, LaLiga, Ligue 1, Serie A, Eredivisie, Championship. Endpoint: `/v4/competitions/{code}/matches?dateFrom=&dateTo=`.

**Rate limit:** 10 requests/minute (free tier). Enforced by `FD_CALL_MIN_INTERVAL = 0.65s`.

**Does not serve:** Blocked EU leagues (returns HTTP 403) or non-EU leagues (no coverage). These route directly to API-Football.

---

### API-Football v3

**Purpose:** Direct provider for non-EU leagues and blocked EU leagues; fallback for all leagues when football-data.org fails.

**Used for:** Primeira Liga, Bundesliga, 2. Bundesliga, Serie B, Ligue 2, Jupiler Pro League, Super Lig (FD-blocked), and all non-EU leagues (MLS, Nordic, Asian, Brazilian). Also used for fixture download in pick generation.

**Rate limit:** Paid subscription — 7500 requests/day, 300 requests/minute.

---

### Telegram

**Purpose:** Push notifications for new picks.

**Used by:** `src/pipeline.process_notifications()`, called from `main.py` after generation.

**Deduplication:** `sent_state.json` records pick IDs sent today. Only picks absent from this file are transmitted.

---

## 3. Startup Flow

When the user opens `index.html`, `boot()` runs in this sequence:

```
boot()
 │
 ├─ checkStartupRecovery()
 │   └─ reads ?recover= query param (internal use only)
 │
 ├─ loadCompactMode()
 │   └─ restores compact/full display preference from localStorage
 │
 ├─ loadLocalState()
 │   └─ state.manualBets    ← localStorage["apostas_bot_manual_bets_v3"]
 │   └─ state.bankroll, localEdits, settings ← localStorage
 │
 ├─ rerenderAll(false)
 │   └─ renderLiveCenter() → getLiveRows() filters state.manualBets
 │   (first render uses localStorage data only; no network calls yet)
 │
 ├─ await Promise.all([loadData(true), loadLeagueStats()])
 │   └─ loadData(): fetches three CSVs from GitHub raw URLs
 │       ├─ picks_hoje_simplificado.csv → state.botPicks
 │       ├─ picks_history.csv           → state.history
 │       └─ manual_bets.csv             → state.manualBetsRemote (always empty)
 │   └─ loadLeagueStats(): fetches league_stats.csv
 │
 ├─ if (!hasMeaningfulLocalState()):
 │   └─ _doLoadCloudState({ fromUser: false })
 │       └─ GET Railway /load → cloud_state.json
 │       └─ state.manualBets ← cloud_state.json["manualBets"]
 │       └─ saveLocalState()
 │
 └─ setInterval(60s, () => loadData(true))
     └─ fetches picks CSVs only; does NOT call /load; does NOT refresh state.manualBets
```

**`hasMeaningfulLocalState()`** returns `true` if any of these are true:
- `state.bankrollInicialSet === true`
- `state.localEdits` has entries
- `state.manualBets.length > 0`

When `true`, the auto-recovery step is skipped entirely and the localStorage snapshot is used as-is.

**Manual bet refresh triggers:** Clicking "Load Cloud" (`_doLoadCloudState`) or clicking "Run Settlement" (`_reloadManualBetsFromCloud` after settlement). The 60-second interval does not trigger either.

---

## 4. Pick Generation Flow

Triggered at 17:00 UTC (main) and 23:00 UTC (top-up) by GitHub Actions.

```
run_main.py
 │
 ├─ fetch_oddsapi_fixtures.py
 │   └─ calls API-Football /fixtures for each configured league
 │   └─ writes fixtures_today.csv (local; not committed to GitHub)
 │
 └─ main.py
     │
     ├─ load_config()              // config.json — leagues, bankroll, Kelly params
     ├─ build_runtime_settings()  // resolves Kelly fraction, edge thresholds, daily cap
     ├─ load_fixtures(url)         // reads fixtures_today.csv
     │
     ├─ for each league:
     │   └─ process_league_fixtures()
     │       ├─ Poisson model: estimate λ_home, λ_away, λ_total
     │       ├─ compute P(goals > N) for O1.5, O2.5, O3.5; P(BTTS)
     │       ├─ compare model probability to 1/odd (implied probability)
     │       ├─ edge = model_prob − implied_prob
     │       ├─ filter by minimum edge threshold (dynamic Kelly-based floor)
     │       └─ compute Kelly fraction → stake€
     │
     ├─ deduplicate against sent_state.json
     │   └─ picks already sent today are excluded from output and Telegram
     │
     ├─ save_all_outputs()
     │   ├─ picks_over25.csv               (O2.5 picks, semicolon)
     │   ├─ picks_btts.csv                 (BTTS picks, semicolon)
     │   ├─ picks_hoje.csv                 (combined, semicolon)
     │   ├─ picks_hoje_github.csv          (combined, comma)
     │   └─ picks_hoje_simplificado.csv    (dashboard columns only)
     │
     ├─ persist_history()
     │   ├─ merge_into_history() — deduplicates by [Data, Liga, Jogo, Mercado]
     │   ├─ appends new picks to picks_history.csv
     │   └─ update_league_stats() — regenerates league_stats.csv
     │
     ├─ upload_csvs_to_github()    // commits all output CSVs via Contents API
     │
     └─ process_notifications()
         ├─ for each new pick not in sent_state: build Telegram message
         ├─ send via Telegram Bot API
         └─ update sent_state.json
```

**Top-up mode** (`run_topup.py`, 23:00 UTC): identical pipeline with `topup_mode=True`. Instead of overwriting CSVs, `_append_csv()` deduplicates by `[Date, HomeTeam, AwayTeam, Market]` and appends. Targets non-EU leagues whose odds arrive late in the day.

---

## 5. Settlement Flow

### 5.1 Bot Pick Settlement

```
update_results.py  (GitHub Actions or run_settlement_remote())
 │
 ├─ download picks_history.csv from GitHub
 ├─ download picks_hoje_simplificado.csv from GitHub
 │
 ├─ make_shared_runtime_state()
 │   ├─ fd_matches_cache {}      // (league_code, date) → FD API response
 │   ├─ af_fixtures_cache {}     // (league_id, date)   → AF API response
 │   ├─ af_league_id_cache {}    // league_code → AF league_id integer
 │   └─ team_alias_cache         // normalised team name mappings
 │
 ├─ update_dataframe(history_df, "history", shared_state)
 └─ update_dataframe(today_df,   "today",   shared_state)
     │
     └─ for each row:
         ├─ SKIP if Resultado ∈ {W, L, P}              → ALREADY_DONE
         ├─ SKIP if Odd or Stake missing/invalid        → INVALID_ROW
         ├─ SKIP if Liga not in LEAGUE_CODE_MAP         → MISSING_LEAGUE_MAP
         ├─ SKIP if Mercado not in SUPPORTED_MARKETS    → UNSUPPORTED_MARKET
         ├─ SKIP if date > today_iso                    → FUTURE_DATE
         │
         ├─ resolve league_code = LEAGUE_CODE_MAP[liga]
         │
         ├─ [provider selection — see 5.3 below]
         │
         └─ if fixture found and FINISHED:
             ├─ check kickoff + RESULT_READY_DELAY (2h15m)
             ├─ extract home_goals, away_goals
             ├─ market_result(mercado, goals) → "W" / "L" / "P"
             └─ calc_profit() → write Resultado, Lucro€
```

After both DataFrames settle:
```
 ├─ upload picks_history.csv to GitHub (Contents API PUT)
 ├─ upload picks_hoje_simplificado.csv to GitHub (Contents API PUT)
 └─ update_league_stats() → upload league_stats.csv
```

### 5.2 Manual Bet Settlement

Runs in the same `update_results.py` execution, after bot picks, using the same shared state.

```
 ├─ load_cloud_state_from_github()
 │   └─ GET Contents API → cloud_state.json → parse → manual_bets list
 │
 ├─ manual_bets_to_settlement_df(manual_bets)
 │   ├─ _resolve_liga_display_name(liga_raw)
 │   │   └─ LEAGUE_CODE_MAP → REGISTRY_BY_KEY → case-insensitive match
 │   ├─ _normalize_market_code(mercado_raw)
 │   │   └─ "Over 2.5" → "O2.5", "Over 1.5" → "O1.5", "BTTS" → "BTTS", etc.
 │   └─ produces DataFrame with same columns as picks CSV
 │
 ├─ update_dataframe(manual_df, "manual", shared_state)
 │   └─ same function as bot picks; shared FD and AF caches
 │
 ├─ apply_df_results_to_manual_bets(manual_bets, manual_df)
 │   └─ 1:1 index mapping: copies Resultado and Lucro€ back to bet dicts
 │
 └─ if newly_settled > 0:
     save_cloud_state_to_github(content, message)
     └─ GET SHA → PUT cloud_state.json (Contents API)
```

**Key property:** `update_dataframe()` is called identically for both bot and manual bets. The only differences are the input conversion (JSON → DataFrame) and output destination (CSVs vs `cloud_state.json`).

### 5.3 Settlement Provider Decision Tree

```
For each unsettled row:
    league_code = LEAGUE_CODE_MAP[liga]

    if league_code ∈ BLOCKED_FOOTBALL_DATA_CODES:
        → API-Football direct (no FD attempt)
        exit

    try football-data.org:
        fetch_matches_for_league_date(league_code, date)
        ├─ HTTP 403 or 429:
        │   if league has AF coverage → API-Football fallback
        │   else → skip this run
        ├─ No fixture matched:
        │   if league has AF coverage → API-Football fallback
        │   else → skip this run
        └─ Fixture matched and FINISHED → settle from FD data
```

All 21 registered leagues have `af_id` set, so all have API-Football coverage. There is no league in the current registry that will be permanently skipped if FD fails.

---

## 6. Synchronisation Flow

### Browser ↔ Railway (on-demand, synchronous from browser perspective)

| Event | Browser sends | Railway does |
|---|---|---|
| "Load Cloud" button | `GET /load` | Fetch `cloud_state.json` from GitHub, return parsed JSON |
| Any state mutation | `POST /save {content, message}` | GET SHA → PUT `cloud_state.json` to GitHub |
| "Run Settlement" | `POST /run-settlement` | Run `run_settlement_remote()` synchronously (~90s max), return result |
| Health check | `GET /health` | Return `{ok: true, time: ...}` |

### Railway ↔ GitHub (per-request, no caching)

Every `/load` call makes one GitHub GET. Every `/save` makes one GET (SHA) then one PUT. There is no in-memory cache on Railway. Each browser request translates directly to GitHub API calls.

### GitHub Actions ↔ GitHub (scheduled)

GitHub Actions checks out the repository, runs the script, and the script calls `upload_csvs_to_github()` which uses the Contents API to PUT each file individually. Changed files are committed and pushed within the Actions run.

### Browser ↔ CSVs (scheduled, read-only)

At startup and every 60 seconds, `loadData()` fetches from GitHub raw HTTPS URLs:
- `picks_hoje_simplificado.csv` → bot picks for today
- `picks_history.csv` → settled history
- `league_stats.csv` → per-league performance

These are unauthenticated GET requests. The browser never writes to CSVs.

### Browser ↔ `cloud_state.json`

The browser reads `cloud_state.json` through Railway `/load`. localStorage is a write-through cache of the last successful load. On startup, localStorage is used immediately; the cloud is checked only when `!hasMeaningfulLocalState()`. All writes (POST /save) go through Railway immediately on state change.

---

## 7. Persistence Architecture

| File | Format | Written by | Read by | Notes |
|---|---|---|---|---|
| `picks_history.csv` | CSV ; | GitHub Actions settlement, `update_results.py` | Browser (loadData), settlement (re-reads each run) | Append-only in practice; results written in-place per row |
| `picks_hoje_simplificado.csv` | CSV ; | GitHub Actions main generation | Browser (loadData), settlement | Overwritten daily at 17:00; top-up appends |
| `picks_hoje.csv` | CSV ; | GitHub Actions main generation | Internal only | Full-column version; not used by dashboard |
| `picks_hoje_github.csv` | CSV , | GitHub Actions main generation | Internal only | Comma-separated variant |
| `picks_over25.csv` | CSV ; | GitHub Actions main generation | Internal only | Per-market split output |
| `picks_btts.csv` | CSV ; | GitHub Actions main generation | Internal only | Per-market split output |
| `cloud_state.json` | JSON | Railway /save, `update_results.py` (manual settlement) | Railway /load → browser | Contains manualBets, footballDaily, footballHistory, bankroll, localEdits |
| `sent_state.json` | JSON | `src/pipeline.save_sent_state()` | `src/pipeline.load_sent_state()` | Date-keyed; resets daily; committed to GitHub |
| `league_stats.csv` | CSV | Settlement (`src/league_stats.update_league_stats()`) | Browser (loadData) | Regenerated on every settlement run |
| `manual_bets.csv` | CSV | Nobody | Nobody | Header row only; legacy artefact |
| `team_alias_cache.json` | JSON | `update_results.save_team_alias_cache()` | `update_results.load_team_alias_cache()` | Local to Railway/Actions runner; not committed |
| `fixtures_today.csv` | CSV ; | `fetch_oddsapi_fixtures.py` | `main.py` (pick generation) | Ephemeral; not committed to GitHub |

---

## 8. Runtime Ownership

| File | Authoritative owner | May modify | Read-only for |
|---|---|---|---|
| `cloud_state.json` | Railway server (proxying GitHub) | Railway /save; `run_settlement_remote()` (manualBets only) | Browser (reads via /load; writes back via /save) |
| `picks_history.csv` | GitHub Actions settlement | `update_results.py` (in-place result writes); main gen (append new rows) | Browser (raw URL); settlement (re-reads each run) |
| `picks_hoje_simplificado.csv` | GitHub Actions main generation | Main gen (overwrite); top-up (append) | Browser (raw URL); settlement |
| `sent_state.json` | Main generation pipeline | `process_notifications()` after generation | `process_notifications()` before send (dedup) |
| `league_stats.csv` | Settlement pipeline | `update_league_stats()` on every settlement run | Browser (raw URL) |
| `team_alias_cache.json` | Settlement engine | `save_team_alias_cache()` at end of settlement run | `load_team_alias_cache()` at start of run |
| `manual_bets.csv` | Nobody | Nobody | Nobody |
| Browser localStorage | Browser | Any state mutation in index.html | Railway and GitHub Actions cannot access it |

---

## 9. Failure Boundaries

### Railway unavailable

- **Bot pick display:** Unaffected. CSVs are fetched directly from GitHub raw URLs; Railway is not involved.
- **Manual bet display:** The most recent localStorage snapshot is shown. No data is lost.
- **On-demand settlement:** Unavailable. GitHub Actions scheduled settlement (07:00, 22:30) continues unaffected.
- **Cloud state persistence:** Blocked. State changes remain in localStorage until Railway is restored.
- **Recovery:** On Railway restoration, the browser auto-loads fresh state on the next page open. User may click "Load Cloud" to force a sync without refresh.

### GitHub unavailable

- **Settlement:** Fails entirely. `get_file_from_github()` returns `(None, None)`; settlement aborts without writing anything.
- **Bot pick display:** Blank or stale. Raw URL fetches fail; `loadData()` returns empty.
- **Cloud state:** Railway /load fails (500). Browser shows localStorage snapshot.
- **Pick generation:** Fails. Fixture download from API-Football may succeed, but CSV upload to GitHub fails.
- **Recovery:** No data is lost. Settlement is retried automatically at the next scheduled time (07:00 or 22:30 UTC).

### football-data.org unavailable (HTTP 403, 429, or network error)

- **Affected leagues:** EU primary leagues (Premier League, LaLiga, Ligue 1, Serie A, Eredivisie, Championship).
- **Fallback:** `should_use_api_football_fallback(league_code, reason)` returns `True` for any HTTP error. All 21 registered leagues have `af_id` set and are in `API_FOOTBALL_FALLBACK_COMPETITIONS`, so every league can fall back to API-Football.
- **Impact:** Slightly higher API-Football request count. All leagues still settle.
- **Recovery:** Transparent. Rows unsettled this run are retried next run.

### API-Football unavailable

- **Affected leagues:** Non-EU leagues (MLS, Nordic, Asian, Brazilian) and FD-blocked EU leagues (Primeira Liga, Bundesliga, etc.) cannot settle. FD-primary EU leagues lose their fallback.
- **FD-primary EU leagues:** Continue to settle via football-data.org if FD is healthy.
- **Pick generation:** `fetch_oddsapi_fixtures.py` fails. No new picks are generated for that run.
- **Recovery:** Rows are skipped; retried on next settlement run.

### Concurrent write conflict (GitHub SHA mismatch)

- **Scenario:** GitHub Actions settlement and Railway /save both fetch the SHA of `cloud_state.json` simultaneously, then both attempt a PUT. The second PUT returns HTTP 409.
- **Current handling:** Railway propagates the 409 as a 500 response. The browser shows an error. GitHub Actions settlement raises an exception.
- **Mitigation:** Railway enforces `--workers 1`, preventing parallel /save requests. The settlement schedule (07:00, 22:30) is unlikely to coincide with a browser /save, but it is not impossible. If it occurs, the user retries the save manually; settlement is retried at the next scheduled run.

---

## 10. Architectural Rules

These rules must be preserved in future development.

**Every dataset has exactly one owner.** `cloud_state.json` owns manual bets. The picks CSVs own bot picks. A piece of code that writes manual bets to a CSV, or bot picks to `cloud_state.json`, creates split-brain state that will diverge.

**Settlement logic lives in `update_dataframe()` and nowhere else.** All result computation, profit calculation, and row-settling belongs in this function. A parallel settlement path — however convenient — will diverge from the main path over time and produce inconsistent results.

**The League Registry is the only registration point for leagues.** `src/league_registry.py` is the single file to edit when adding or changing a league. All derived structures (`LEAGUE_CODE_MAP`, `BLOCKED_FOOTBALL_DATA_CODES`, `API_FOOTBALL_FALLBACK_COMPETITIONS`, `AF_SEASON_MODELS`) are computed from it automatically. Hard-coding league metadata in `update_results.py`, `config.json`, or any other file violates this rule.

**The Railway server holds no state between requests.** It is a pure proxy. Any logic that requires the server to remember something across requests is out of scope and belongs elsewhere.

**The frontend is a single file with no build step.** `index.html` is edited directly. There is no compilation, no bundling, no `node_modules`. A change to the frontend is a change to this file and nothing else.

**GitHub is the database.** Data that must survive a Railway restart, a browser refresh, and a new GitHub Actions runner must be in a file committed to the repository. Data only in memory, only in localStorage, or only on the Railway filesystem is ephemeral and will be lost.

**The 60-second browser interval refreshes CSVs only.** It does not and must not call `GET /load`. Adding a cloud sync to the interval would issue one Railway→GitHub API request every 60 seconds per open browser tab. If more frequent cloud sync is needed, implement a backoff strategy or a targeted event-driven refresh — not a fixed-interval blanket call.

**Settlement skips rather than fails.** A row that cannot be settled this run (game not yet finished, API unreachable, no fixture matched) is skipped with a diagnostic log. It will be retried on the next scheduled run. Settlement never deletes rows, never writes partial results, and never leaves a file in an inconsistent state.
