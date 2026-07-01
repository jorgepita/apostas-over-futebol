# Roadmap

Future work only. Completed items belong in `08_Change_Log.md`. Current unresolved bugs belong in `05_Known_Issues.md`.

---

## Vision

The Football Bot should become a self-sufficient personal betting intelligence system: one that generates value picks, tracks execution with precision, settles results automatically, and provides enough analytical depth to evaluate model quality and calibration over time without requiring manual data entry or external dashboards.

The architectural principles are fixed: single-file frontend, GitHub as persistence, stateless Railway, shared settlement engine. Future development should improve within those boundaries, not replace them.

---

## Short-Term Roadmap

### ST-1 — Periodic Manual Bet Auto-Refresh

**Objective:** Resolve LIVE-1. Add a periodic background sync of `cloud_state.json` so the Live Center reflects settlement that happened outside the current browser session.

**Why it matters:** Without this, the user must manually click "Load Cloud" to see that a bet has been settled. A settled bet appearing as LIVE is incorrect and erodes trust in the dashboard.

**Dependencies:** LIVE-1 must be the active implementation task. No external dependencies.

**Definition of Done:**
- A 5-minute `setInterval` added to `boot()` calls `_reloadManualBetsFromCloud()` when `state.cloudAvailable` is true.
- All validation checklist items in LIVE-1 pass.
- Diagnostic instrumentation (F1–F6 console logs in `index.html`, STEP 1–5 prints in `update_results.py`) is removed.

---

### ST-2 — Telegram Settlement Notifications

**Objective:** Send a Telegram message after settlement settles at least one bet, listing each settled bet with its result and profit.

**Why it matters:** Currently Telegram is used only for pick generation. There is no notification when a bet resolves. The user must open the dashboard to check results.

**Dependencies:** ST-1 should be complete first, so the settlement flow is stable and the instrumentation is clean.

**Definition of Done:**
- `run_settlement_remote()` and `update_results.main()` send a Telegram message when `newly_settled > 0`.
- Message format: one line per settled bet — game, market, result, profit.
- No duplicate notifications on re-run (already-settled bets are not re-reported).
- Telegram failure does not abort settlement.

---

### ST-3 — SHA Conflict Retry in Railway

**Objective:** Retry `POST /save` automatically when GitHub returns HTTP 422 (SHA mismatch) by re-fetching the SHA and retrying the PUT.

**Why it matters:** A SHA conflict causes the browser to show a save error and the user's edits to remain unsaved until the next manual action. With a single retry, the conflict resolves transparently in all cases except genuine concurrent writes to the same file.

**Dependencies:** None.

**Definition of Done:**
- `put_file_to_github()` in `sync_server.py` retries once on HTTP 422 by calling `get_file_from_github()` again to get the fresh SHA.
- A second consecutive 422 propagates as HTTP 409 to the browser with a descriptive error.
- No other endpoint behaviour changes.

---

## Medium-Term Roadmap

### MT-1 — Seasonal Performance Reports via Telegram

**Objective:** Send a weekly Telegram summary of the current session's performance: total picks, win rate, ROI, profit by market, and top/bottom league.

**Why it matters:** The dashboard requires active access. A weekly Telegram digest provides passive awareness without opening the dashboard.

**Dependencies:** ST-2 (Telegram infrastructure for settlement). Access to `picks_history.csv` and `cloud_state.json` for combined P&L.

**Definition of Done:**
- A new scheduled GitHub Actions job runs on Monday 08:00 UTC.
- The report aggregates the current session (from `sessionStartDate` in `cloud_state.json`) up to the previous Sunday.
- Covers: bot picks (executed), manual bets, combined. Minimum 5 executed picks for stats to be meaningful (otherwise the report is suppressed).
- Report is sent to the same Telegram chat as pick notifications.

---

### MT-2 — League History Auto-Update

**Objective:** Automate the refresh of `data_raw/{league_key}.csv` match history files rather than requiring manual downloads.

**Why it matters:** The Poisson model quality depends on up-to-date history. Currently the history CSVs must be manually refreshed from external sources. Stale history reduces model accuracy, particularly for leagues where form changes rapidly.

**Dependencies:** football-data.org API for EU leagues; API-Football for non-EU leagues. `fetch_historical.py` already exists as a starting point.

**Definition of Done:**
- A new GitHub Actions job runs weekly (e.g. Monday 06:00 UTC, before the settlement job).
- Fetches the last N (configurable) completed matches for each league from the appropriate API.
- Appends new rows to `data_raw/{league_key}.csv` without duplicates.
- Commits updated history files to the repository.
- Does not exceed API-Football daily request budget.

---

### MT-3 — O1.5 and O3.5 Market Expansion

**Objective:** Extend the pick generation pipeline to produce O1.5 and O3.5 picks using the same Poisson model and Kelly framework already in place for O2.5.

**Why it matters:** The model already computes cumulative goal probabilities for any threshold. O1.5 edges occur in low-scoring match profiles; O3.5 edges in high-scoring profiles. Both are served by the settlement engine (already supports `O1.5` and `O3.5` market codes).

**Dependencies:** MT-2 (up-to-date history improves O3.5 accuracy, which is more sensitive to lambda estimation). Calibration data for each market.

**Definition of Done:**
- `config.json` includes `rules.over15` and `rules.over35` sections.
- `process_league_fixtures()` generates O1.5 and O3.5 candidates.
- Output CSVs include O1.5 and O3.5 picks correctly labelled.
- Dashboard filter for "market" includes O1.5 and O3.5.
- Settlement handles O1.5 and O3.5 correctly (already implemented in `market_result()`).
- At least 4 weeks of live picks tracked before the markets are considered stable.

---

### MT-4 — Bankroll Immutability Improvements

**Objective:** Make the bankroll configuration (initial amount, session start date) safer to modify, with an explicit "close season" workflow that archives the season before resetting.

**Why it matters:** Currently clearing localStorage or accidentally resetting the bankroll loses session history. A structured season-close workflow preserves the record.

**Dependencies:** None. Dashboard-only change.

**Definition of Done:**
- "Close Season" button triggers a modal confirmation: shows session summary (P&L, pick count, date range).
- On confirm: archives the current session to `SEASON_ARCHIVES_KEY` in localStorage.
- Clears bankroll and session state.
- The History page can display archived seasons via a season selector.
- `cloud_state.json` is updated to reflect the new session.

---

## Long-Term Roadmap

### LT-1 — Multi-Season Model Calibration

**Objective:** Measure model calibration across seasons. Compare predicted probabilities with observed win rates per market and league, and surface the results in the Analytics tab.

**Why it matters:** The current BTTS adjustment factor (0.885) is a global constant. Calibration likely varies by league and market. Multi-season data makes it possible to tune these factors per league rather than applying a single global correction.

**Dependencies:** At least two full seasons of executed picks. MT-2 (automated history). `picks_history.csv` as the calibration source.

**Definition of Done:**
- New Analytics sub-section: "Calibration" shows, per league × market: predicted win rate, observed win rate, Brier score.
- `config.json` supports `league_overrides.{key}.calibration.btts_probability_adjustment` and `calibration.over25_probability_adjustment`.
- Backend can consume per-league calibration adjustments in `process_league_fixtures()`.

---

### LT-2 — Advanced Team Form Features

**Objective:** Extend the Poisson model to incorporate recency weighting at the fixture level (not just the window) and optional head-to-head data.

**Why it matters:** The current model uses a fixed `decay = 0.88` applied uniformly across the history window. Fixtures where both teams are in exceptional or poor recent form are treated the same as stable teams.

**Dependencies:** MT-2 (automated history refresh). LT-1 (calibration framework to validate model improvements).

**Definition of Done:**
- Model produces measurably better calibration (lower Brier score) on held-out picks compared to the current model.
- No increase in computation time that would push `fetch_oddsapi_fixtures.py` beyond 5 minutes.
- All existing leagues continue to produce picks within current edge bounds.

---

### LT-3 — Automated Edge Threshold Tuning

**Objective:** Replace fixed `edge_min` and `edge_max` in `config.json` with values derived from historical performance data, updated periodically.

**Why it matters:** The current thresholds are manually set. Historical win rates by edge bucket can reveal whether the current thresholds are optimal for each market.

**Dependencies:** LT-1 (multi-season calibration data). At least 200 executed picks per market for reliable edge-bucket analysis.

**Definition of Done:**
- A new analysis script (`tune_thresholds.py`) produces recommended `edge_min` and `edge_max` per market from `picks_history.csv`.
- Results are presented as a report (Telegram or CSV), not applied automatically.
- Manual application to `config.json` is the intended workflow.

---

## Technical Debt

### TD-1 — Split `update_results.py` into modules

`update_results.py` is 2600+ lines containing team name normalisation, football-data.org client, API-Football client, GitHub write helpers, and the settlement engine. These are logically independent and should live in `src/`. The file's size makes it difficult to navigate.

**Approach:** Extract into `src/settlement.py` (core `update_dataframe()`), `src/team_matching.py` (normalisation, similarity, alias learning), and keep API clients in `src/integrations.py`. `update_results.py` becomes a thin orchestrator.

**Risk:** The refactor must not change settlement behaviour. Requires careful testing against the existing pick history.

---

### TD-2 — Consolidate GitHub write helpers

Three files contain independent implementations of the GitHub Contents API write pattern: `sync_server.py` (using `requests.Session`), `update_results.py` (using `urllib`), and `fetch_oddsapi_fixtures.py` (using `urllib`). They handle auth and error semantics differently.

**Approach:** Unify into a single `src/github_client.py` with a consistent interface. `sync_server.py` uses `requests`; the two pipeline scripts use `urllib`. The unified module should use `requests` throughout.

---

### TD-3 — Automated test coverage for settlement

There are no automated tests. The settlement engine has complex branching (provider selection, team matching, market calculation, profit calculation) that is currently validated only by running against real data.

**Approach:** Unit tests for `market_result()`, `calc_profit()`, `normalize_team_name()`, `similarity_score()`, `find_best_fixture_match()`, and `_normalize_market_code()`. Integration test with a fixture of known result to validate the end-to-end settlement path.

---

### TD-4 — Remove diagnostic instrumentation

F1–F6 console logs in `index.html` and STEP 1–5 print statements in `update_results.py` were added to investigate LIVE-1. They add noise to production logs and should be removed once LIVE-1 is resolved and validated.

**Blocked by:** ST-1 (LIVE-1 fix and validation).

---

## Future Dashboard Improvements

### Functional

**DX-1 — Periodic cloud sync for manual bets (LIVE-1 fix, ST-1)**  
See ST-1.

**DX-2 — Toast notification on settlement result**  
When `POST /run-settlement` returns, show a toast listing how many bets were settled and their outcomes. Currently the button shows a generic "Settlement complete" message.

**DX-3 — Offline indicator with queued-save display**  
When Railway is unavailable, show a persistent banner with the count of pending saves and a retry button. Currently the cloud status indicator exists but does not show a retry affordance.

**DX-4 — Season selector in History tab**  
Allow switching between the current session and archived seasons (linked to MT-4). History, Analytics, and Bankroll would scope their data to the selected season.

**DX-5 — Pick annotation field**  
Add a free-text notes field to bot picks (alongside the existing `localEdits` system). Useful for recording why a pick was or was not placed.

### Cosmetic

**DX-6 — Consistent loading skeletons**  
When `loadData()` is in progress, replace tables with skeleton placeholders rather than showing stale data or empty states.

**DX-7 — Dark-mode colour token audit**  
Several hardcoded `#hex` values exist alongside the CSS custom properties. Unify all colours through the `--bg`, `--card`, `--accent`, `--ok`, `--bad`, `--warn`, `--info` token system.

---

## Backend Improvements

**BX-1 — SHA conflict retry (ST-3)**  
See ST-3.

**BX-2 — Structured logging**  
Replace `print()` statements in `update_results.py` and `sync_server.py` with a consistent log format (level, timestamp, key=value pairs). Enables easier filtering in Railway log viewer and GitHub Actions output.

**BX-3 — Settlement health check endpoint**  
Add `GET /settlement-status` to Railway that returns the timestamp of the last successful settlement, the number of open picks, and whether the GitHub token is valid. Useful for monitoring without triggering a full settlement run.

**BX-4 — Graceful timeout handling in `run_settlement_remote()`**  
If settlement exceeds 270 seconds (leaving 30 seconds before the gunicorn timeout), return a partial result with `{"ok": true, "partial": true, "updated": N}` rather than letting gunicorn kill the connection and return HTTP 500 to the browser.

**BX-5 — `team_alias_cache.json` on GitHub**  
Currently `team_alias_cache.json` is local to the Railway container and is lost on every deploy. Move it to GitHub (read on settlement start, write on settlement end) so learned aliases persist across deploys.

---

## Data & Model Improvements

**MX-1 — BTTS calibration per league**  
The global `btts_probability_adjustment = 0.885` is applied identically to all leagues. Leagues with different scoring profiles (e.g. Brazil vs Premier League) likely need different adjustments. `config.json` already supports `league_overrides.{key}.btts.edge_min` — extend this to `calibration.btts_probability_adjustment`.

**MX-2 — O2.5 calibration factor**  
Add a configurable `over25_probability_adjustment` (analogous to the BTTS one) to account for systematic model over/underestimation per market. Set to 1.0 by default (current behaviour).

**MX-3 — Minimum history validation at generation time**  
When a team has fewer than `min_games_home` / `min_games_away` games, the league average is used as a lambda fallback. The pick is currently generated without any flag indicating the lambda is unreliable. Add a `LambdaSource` column to `fixtures_today.csv` (`"team_specific"` or `"league_avg_fallback"`) so picks based on fallback lambdas can be filtered or discounted.

**MX-4 — Odds freshness tracking**  
`fixtures_today.csv` stores the odds fetched at ~17:00. Odds at kickoff can differ significantly. Track the timestamp when odds were fetched and surface an "odds may be stale" warning in the dashboard for fixtures where kickoff is more than 12 hours after the odds fetch time.

**MX-5 — Automated history data refresh (MT-2)**  
See MT-2.

---

## Automation Improvements

**AX-1 — Telegram settlement notifications (ST-2)**  
See ST-2.

**AX-2 — Weekly P&L report (MT-1)**  
See MT-1.

**AX-3 — GitHub Actions job failure alert**  
When a scheduled job (generation or settlement) fails, send a Telegram alert. Currently failures are only visible in the GitHub Actions UI.

**AX-4 — Automatic `team_alias_cache.json` commit**  
When GitHub Actions settlement learns new team aliases, commit `team_alias_cache.json` to the repository alongside the CSV updates. Currently the file is only updated in Railway's ephemeral filesystem.

**AX-5 — Daily fixture preview alert**  
At 16:00 UTC (before the 17:00 generation run), send a Telegram message listing today's fixtures with their computed lambdas for leagues where picks are likely. Provides advance awareness before picks are generated.

---

## Nice-to-Have Ideas

These are interesting but not currently planned. They should not influence short- or medium-term priorities.

- **Web-based configuration editor:** A settings UI in the dashboard for editing `config.json` fields (bankroll, Kelly fraction, edge thresholds) without committing directly to the repository.
- **Multi-user support:** Separate `cloud_state.json` files per user. Not aligned with the current personal-project scope.
- **Odds comparison across bookmakers:** Track odds from multiple bookmakers and flag when the best available odd differs materially from the API-Football odd used in generation.
- **Live odds API integration:** Subscribe to a live odds feed and trigger re-evaluation when odds move significantly after picks are generated.
- **Machine learning model:** Replace or augment the Poisson model with a gradient-boosted classifier trained on historical match features. Significant infrastructure change.
- **Mobile app:** A native mobile client. Conflicts with the single-file, no-build-step frontend principle.
- **Betting exchange integration:** Log actual bets placed on an exchange alongside the CSV picks. Significant change to the bet lifecycle.

---

## Roadmap Table

| ID | Feature | Priority | Status | Dependencies |
|---|---|---|---|---|
| ST-1 | Periodic manual bet auto-refresh (LIVE-1 fix) | Critical | Ready | — |
| ST-2 | Telegram settlement notifications | High | Planned | ST-1 |
| ST-3 | SHA conflict retry in Railway | High | Planned | — |
| MT-1 | Weekly P&L Telegram report | Medium | Planned | ST-2 |
| MT-2 | League history auto-update | Medium | Planned | — |
| MT-3 | O1.5 and O3.5 market expansion | Medium | Planned | MT-2 |
| MT-4 | Bankroll season-close workflow | Medium | Planned | — |
| LT-1 | Multi-season model calibration | Low | Deferred | MT-2, 2 full seasons |
| LT-2 | Advanced team form features | Low | Deferred | MT-2, LT-1 |
| LT-3 | Automated edge threshold tuning | Low | Deferred | LT-1, 200+ executed picks |
| TD-1 | Split `update_results.py` into modules | Medium | Planned | — |
| TD-2 | Consolidate GitHub write helpers | Low | Planned | TD-1 |
| TD-3 | Automated test coverage for settlement | Medium | Planned | TD-1 |
| TD-4 | Remove diagnostic instrumentation | High | Blocked | ST-1 |
| DX-1 | Periodic cloud sync (LIVE-1) | Critical | Blocked | ST-1 |
| DX-2 | Toast on settlement result | Low | Planned | ST-1 |
| DX-3 | Offline indicator with retry | Medium | Planned | — |
| DX-4 | Season selector in History | Low | Deferred | MT-4 |
| DX-5 | Pick annotation field | Low | Planned | — |
| BX-1 | SHA conflict retry | High | Planned | — |
| BX-2 | Structured logging | Low | Planned | — |
| BX-3 | Settlement health check endpoint | Low | Planned | — |
| BX-4 | Graceful timeout in settlement | Medium | Planned | — |
| BX-5 | `team_alias_cache.json` on GitHub | Medium | Planned | — |
| MX-1 | BTTS calibration per league | Medium | Planned | LT-1 |
| MX-2 | O2.5 calibration factor | Low | Planned | LT-1 |
| MX-3 | Lambda source flag in fixtures | Medium | Planned | — |
| MX-4 | Odds freshness tracking | Low | Planned | — |
| AX-1 | Telegram settlement notifications | High | Planned | ST-2 |
| AX-2 | Weekly P&L report | Medium | Planned | MT-1 |
| AX-3 | GitHub Actions failure alert | Medium | Planned | ST-2 |
| AX-4 | Auto-commit team alias cache | Medium | Planned | — |
| AX-5 | Daily fixture preview alert | Low | Planned | — |
