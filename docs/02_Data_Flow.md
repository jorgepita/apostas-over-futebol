# Data Flow

This document describes how data moves through the Football Bot — from creation through persistence, settlement, and presentation. For component descriptions and architectural rules, see `01_Architecture.md`.

---

## 1. Data Flow Overview

```
                         API-Football
                         (fixtures)
                              │
                              ▼
                   fetch_oddsapi_fixtures.py
                              │
                      fixtures_today.csv
                       (ephemeral, local)
                              │
                              ▼
                           main.py
                        (Poisson model)
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
   picks_hoje_simplificado  picks_history  Telegram
         .csv (today)         .csv           notification
              │               │
              └───────┬───────┘
                      │ GitHub Contents API (upload)
                      ▼
               GitHub Repository
                      │
        ┌─────────────┼────────────────────┐
        │ raw URL GET  │                    │
        ▼              ▼                    │
     Browser        settlement           league_stats.csv
    (loadData)    (update_results)             │
        │                │                    │
        │         ┌──────┤                    │
        │         │      │                    │
        │    FD API    AF API                 │
        │    (results) (results)              │
        │         │      │                   │
        │         └──────┤                   │
        │                ▼                   │
        │         picks_history.csv          │
        │         (results written)          │
        │                │                   │
        │                │ upload to GitHub  │
        │                ▼                   │
        │         GitHub Repository ◄────────┘
        │                │ raw URL GET
        └────────────────┤
                         │
                    Browser renders
                    (Daily Picks,
                     History,
                     Analytics)


         User (Scout Workspace)
                   │
           creates manual bet
                   ▼
            state.manualBets
            (in-memory + localStorage)
                   │ POST /save
                   ▼
            Railway Flask API
                   │ PUT GitHub Contents API
                   ▼
          cloud_state.json (GitHub)
                   │ POST /run-settlement or GitHub Actions
                   ▼
        update_results.run_settlement_remote()
                   │ result APIs (FD / AF)
                   ▼
          cloud_state.json updated (GitHub)
                   │ GET /load (user action)
                   ▼
            state.manualBets refreshed
                   │
                Browser renders
                (Live Center, History)
```

---

## 2. Bot Pick Lifecycle

### Stage 1 — Fixture Download

`fetch_oddsapi_fixtures.py` calls the API-Football `/fixtures` endpoint for each league configured in `config.json`. The response contains fixture metadata, odds, and kickoff times.

**Output:** `fixtures_today.csv` — a local file written to the runner's disk. It is not committed to GitHub and is discarded when the Actions runner terminates.

---

### Stage 2 — Poisson Model

`main.py` reads `fixtures_today.csv` via `load_fixtures()`. For each fixture, the model estimates:
- `λ_home`, `λ_away` — expected goals for each team based on historical goal rates
- `λ_total` — expected total goals
- `P(goals > N)` — probability of Over 1.5, Over 2.5, Over 3.5
- `P(BTTS)` — probability of both teams scoring

---

### Stage 3 — Value Detection

For each fixture and market, the model probability is compared against the implied probability from the bookmaker odds:

```
edge = model_probability − (1 / odd)
```

Picks where `edge < edge_min_dynamic` are discarded. `edge_min_dynamic` is a Kelly-based floor that adjusts with bankroll size.

---

### Stage 4 — Cross-Market Selection & Fixture Lock

O2.5 and BTTS candidates are generated independently per fixture (Stage 2/3), so a fixture can have both a qualifying O2.5 row and a qualifying BTTS row at this point. Two mechanisms then narrow this down to at most one bot market per fixture, applied in this order — both run identically whether this is the main (17:00 UTC) or top-up (23:00 UTC) job, since both call the same `main()` function:

1. **`apply_fixture_market_lock()`** (`src/pipeline.py`) — Policy A, the fixture-level market lock (see ADR-018). Builds a `fixture id → {markets already in picks_history.csv}` map from the existing history file, then discards any candidate whose market is *not* already among the markets recorded for that fixture. A fixture with no prior history is completely unaffected. This runs *before* cross-market selection below, so it never influences the Edge comparison for a fixture that has never been recommended before — it only ever removes a *competing* market's candidate for a fixture that already has a persisted recommendation.
2. **`dedupe_correlated_picks()`** (`src/market_rules.py`) — the pre-existing same-run cross-market selection. Groups the remaining candidates by `[Date, League, HomeTeam, AwayTeam]` (fixture identity, no Market) and keeps one row per fixture: `Edge DESC → KellyTrue DESC → ProbModel DESC → Odd DESC`. For a fixture with no prior history, both O2.5 and BTTS candidates reach this step and the winner is chosen purely by that ranking, exactly as before Stage-4's lock existed. For an already-locked fixture, at most one candidate (the locked market) survives Step 1, so this step is a trivial single-row pass-through.

The fixture id used for the lock (`fixture_id_from_parts()`/`fixture_id_from_simple()`/`fixture_id_from_candidate()` in `src/history.py`) is `Date + League(display name) + Game`, deliberately excluding Market — a distinct identity from every other market-specific key in the codebase (`history_pick_id_from_simple()`, `localEdits` keys, settlement matching), which are all unchanged.

---

### Stage 5 — Kelly Staking

For qualifying picks:
```
kelly_fraction = edge / (odd − 1)
stake = bankroll × kelly_fraction × kelly_multiplier
```

The fractional Kelly multiplier and daily cap are read from `config.json`.

---

### Stage 6 — Deduplication

`load_sent_state(today_iso)` reads `sent_state.json` from disk. This file records pick IDs already sent via Telegram today. Any pick whose `pick_id` (built from `Date|League|HomeTeam|AwayTeam|Market`) is already in `sent_state` is excluded from the Telegram notification — but still written to the output CSVs.

A competing market rejected by Stage 4's fixture lock never reaches this stage at all — it is not merely excluded from the Telegram message, it is absent from `out25_final`/`out_btts_final` entirely, so it cannot be written to `sent_state.json` or any output CSV.

---

### Stage 7 — CSV Generation

`save_all_outputs()` writes multiple files from the generated picks:

| File | Content | Separator |
|---|---|---|
| `picks_hoje_simplificado.csv` | Dashboard-facing columns only | `;` |
| `picks_hoje.csv` | Full columns including Lambda fields | `;` |
| `picks_hoje_github.csv` | Same as picks_hoje but comma-separated | `,` |
| `picks_over25.csv` | O2.5 picks only | `;` |
| `picks_btts.csv` | BTTS picks only | `;` |

In **top-up mode**, these files are appended rather than overwritten. `_append_csv()` deduplicates by `[Date, HomeTeam, AwayTeam, Market]`.

---

### Stage 8 — History Persistence

`persist_history()` calls `merge_into_history()` which reads the existing `picks_history.csv`, appends new picks, and deduplicates by `[Data, Liga, Jogo, Mercado]`. The merged file is written back to `picks_history.csv`.

Because Stage 4's fixture lock already removed any competing-market candidate before Kelly staking, a fixture can never reach this stage with two different markets in the same run — `merge_into_history()`'s own `[Data, Liga, Jogo, Mercado]` key was already sufficient to prevent a literal same-market duplicate, but it alone could not prevent the *competing*-market case across separate runs, which is what the Stage 4 lock closes (see ADR-018).

`update_league_stats()` then regenerates `league_stats.csv` from the updated history. Since Phase 26.44, both this path (`main.py`) and the settlement path (`update_results.py`) explicitly upload the regenerated file in the same run — see Stage 9 and `04_Backend.md` §11.

---

### Stage 9 — GitHub Upload

`upload_csvs_to_github()` calls the GitHub Contents API (PUT) for each output file. Each PUT includes the current SHA fetched in the same operation to avoid conflicts.

After this step, the picks are durable and available at GitHub raw URLs.

---

### Stage 10 — Telegram Notification

`process_notifications()` sends picks that are new (not in `sent_state`) via the Telegram Bot API. After sending, the pick IDs are added to `sent_state` and `sent_state.json` is written to disk.

---

### Stage 11 — Dashboard Display

The browser fetches `picks_hoje_simplificado.csv` from the GitHub raw URL in `loadData()`. This happens at page load and every 60 seconds. The picks appear on the **Daily Picks** page.

---

### Stage 12 — Settlement

`update_dataframe()` processes each row in `picks_history.csv` and `picks_hoje_simplificado.csv`. For each unsettled row it queries football-data.org (primary for EU leagues) or API-Football (direct for blocked/non-EU; fallback for all). When a match is confirmed FINISHED and at least 2h15m have elapsed since kickoff, the Resultado (W/L/P) and Lucro€ are written to the row.

The updated CSVs are committed back to GitHub.

---

### Stage 13 — History and Analytics

Settled rows in `picks_history.csv` feed the dashboard **History** and **Analytics** pages. `getHistoryRowsMerged()` combines rows from `picks_history.csv` (via `state.history` populated by `loadData`) with local edits from `state.localEdits` (OddReal, StakeReal, Apostada).

---

## 3. Manual Bet Lifecycle

### State 1 — Scout Workspace

The user opens the **Manual Bets** page. They search for a fixture by typing team names or a date. The Scout calls API-Football to find matching fixtures.

The user selects a fixture, specifies a market (O1.5, O2.5, O3.5, BTTS) and an odd. The Poisson model runs on-demand in JavaScript to compute edge and Kelly stake.

A new bet object is created in memory with:
- `status: "pending"` — not yet approved for live tracking
- `resultado: ""` — unsettled
- `id` — unique string built from date + league + game + market + timestamp
- `isLocal: true` — distinguishes cloud-sourced bets from legacy CSV bets

---

### State 2 — Created (pending)

The bet exists in `state.manualBets` in memory and is immediately written to `localStorage` via `saveLocalState()`. It is also immediately pushed to `cloud_state.json` via `POST /save` (subject to the backend's duplicate check — ADR-013).

The bet appears on the **Pending** page. It does not appear in the Live Center.

The Scout card for this fixture disappears from the Scout workspace the instant the bet is created — `renderManualScout()` hides any fixture already represented by a bet in `state.manualBets`, in any lifecycle state, not just once it's approved or rejected (Phase 26.19; see `03_Dashboard.md` §7). This is what prevents the user from accidentally creating a second bet for the same fixture while the first is still pending.

---

### State 3 — Approved

The user clicks "Approve" on the bet in the Pending queue. The bet's `status` changes from `"pending"` to `"approved"`. `saveLocalState()` is called (localStorage update). `POST /save` pushes the updated `cloud_state.json` to GitHub.

The bet moves from Pending to the **Live Center**.

Live Center filter for manual bets:
```javascript
b.isLocal === true
&& b.status === 'approved'
&& !['W','L','P'].includes(b._resultKey)
&& (kickoff_timestamp <= Date.now() || b.data <= today)
```

---

### State 4 — Live

The bet is displayed in the Live Center alongside any bot picks that are also active. It remains here until settlement writes a result.

No automated process changes `status` from `"approved"` to anything else. The way to exit this state is through settlement (which writes `resultado`) or the user clicking "Rejeitar".

---

### State 4b — Rejected (a parallel branch, not an exit from the pipeline)

The user can click "Rejeitar" from the Manual Bets list at any point before settlement (and can still un-reject afterwards). This sets `status: 'rejected'` — **the bet is not deleted** (this changed in Phase 26.19; see ADR-012). A rejected bet:
- Disappears from Pending and Live Center immediately (both require `status === 'approved'`).
- Is excluded from every financial calculation — bankroll, ROI, `getResolvedManualBets()` — regardless of whether it later gets a settlement result.
- Still appears in the Manual Bets list (badge "Rejeitada") and, once its data is available, in the History page's "Rejeitadas" view (`getRejectedManualBets()`).
- Still goes through settlement exactly like an approved bet (State 5) — the settlement engine does not filter by `status` at all. This is what lets rejected bets become genuine analytical records (win rate on rejected opportunities, etc. — see `03_Dashboard.md` §9) instead of just disappearing.

---

### State 5 — Settlement

Settlement can be triggered in two ways:
1. **GitHub Actions** — scheduled at 07:00 and 22:30 UTC, runs `update_results.py` directly.
2. **"Run Settlement" button** — browser sends `POST /run-settlement` to Railway, which calls `run_settlement_remote()` synchronously.

In both cases, the settlement engine:
1. Downloads `cloud_state.json` from GitHub.
2. Converts `manualBets` to a DataFrame — **every** bet regardless of `status`, including rejected ones.
3. Runs `update_dataframe()` — the same engine as bot picks.
4. Copies `resultado`/`lucro`/`placar` (final score, Phase 26.19) back to the bet objects. `status` advances to `'settled'` unless it was already `'rejected'`, in which case it stays `'rejected'` forever (ADR-012).
5. If any bets were newly settled, uploads `cloud_state.json` back to GitHub.

The bet's `resultado` field is now `"W"`, `"L"`, or `"P"`, and `placar` holds the final score (e.g. `"2-1"`) — independently of whatever `status` the bet is on.

---

### State 6 — Settled (History)

After settlement, an **approved** bet is excluded from the Live Center filter (`_resultKey` is now W/L/P) and appears in the **History** page's default "Resolvidas" view and in the **Analytics** calculations. A **rejected** bet that gets settled the same way never appears in Resolvidas, Analytics, or Bankroll — it appears only in History's "Rejeitadas" view (`03_Dashboard.md` §9).

The browser only reflects the settlement result after `state.manualBets` is refreshed from the cloud. This happens when:
- The user clicks "Load Cloud" — calls `_doLoadCloudState()`.
- Settlement was triggered from this browser session — `_reloadManualBetsFromCloud()` is called automatically after the `/run-settlement` response.
- A new page load occurs and `hasMeaningfulLocalState()` is false.
- The backend dropped a duplicate bet on the last save (`duplicatesRemoved > 0` in the `/save` response — ADR-013).

---

### State 7 — Analytics and Bankroll

Settled manual bets flow into the Analytics page through `getResolvedManualBets()`, which filters `getManualRowsMerged()` for bets with a non-null `_lucro` **and `status !== 'rejected'`** (Phase 26.19 — see ADR-012). The bankroll calculation incorporates manual bet profits alongside bot pick profits; rejected bets never contribute to it, settled or not. Rejected bets are available separately via `getRejectedManualBets()` for the History page's analytical "Rejeitadas" view.

---

## 4. Dashboard Data Flow

| Page | Primary Data Source | Refresh Trigger |
|---|---|---|
| Daily Picks | `picks_hoje_simplificado.csv` via GitHub raw URL | Page load; every 60 seconds (`loadData`) |
| Live Center | `state.manualBets` (manual); `state.history` + `state.botPicks` (bot) | Any `rerenderAll()`; tab activation |
| Pending | `state.manualBets` filtered for `status === 'pending'` | Any `rerenderAll()` |
| Manual Bets | `state.manualBets` (all bets); API-Football (Scout fixture search) | Any `rerenderAll()`; Scout search is on-demand |
| History | `picks_history.csv` via GitHub raw URL (`state.history`); `state.manualBets` settled | Page load; every 60 seconds; any `rerenderAll()` |
| Analytics | Derived from `state.history`, `state.manualBets`, `state.localEdits` | Any `rerenderAll()` |
| Settings | `state.bankrollInicial`, Kelly/edge settings — all from `localStorage` | Page load; user input |

**`getManualRowsMerged()`** is the central function that produces the unified manual bet row list. It merges:
- `remoteRows` from `state.manualBetsRemote` (always empty — `manual_bets.csv` is dead) with `isLocal: false`
- `localRows` from `state.manualBets` (cloud-sourced bets) with `isLocal: true`

All manual bet pages consume `getManualRowsMerged()` and then filter for the relevant status.

---

## 5. Settlement Data Flow

### Bot Pick Settlement

```
picks_history.csv (GitHub)
picks_hoje_simplificado.csv (GitHub)
         │
         │ GitHub Contents API GET (download)
         ▼
   update_dataframe()
         │
   for each unsettled row:
         ├─ football-data.org → match result
         │  (EU leagues: primary)
         │
         └─ API-Football → match result
            (blocked EU + non-EU: direct)
            (any league: fallback on FD failure)
         │
         ▼
   Resultado: "W" / "L" / "P"
   Lucro€: profit calculation
         │
         │ GitHub Contents API PUT (upload)
         ▼
picks_history.csv (GitHub) — results written in-place
picks_hoje_simplificado.csv (GitHub) — results written in-place
         │
         │ Browser fetches raw URL every 60s
         ▼
     Dashboard (History, Analytics, Daily Picks)
```

### Manual Bet Settlement

```
cloud_state.json (GitHub)
         │
         │ GitHub Contents API GET (download)
         ▼
manual_bets_to_settlement_df()
   ├─ _resolve_liga_display_name()   ← LEAGUE_CODE_MAP / REGISTRY_BY_KEY
   └─ _normalize_market_code()       ← "Over 2.5" → "O2.5"
         │
         ▼
   update_dataframe()                ← SAME FUNCTION as bot picks
         │
   for each unsettled row:
         ├─ football-data.org → match result
         └─ API-Football → match result
         │
         ▼
   Resultado: "W" / "L" / "P"
   Placar: final score (e.g. "2-1")
   Lucro€: profit calculation
   SettlementReason: blank, or why a P was a void (Phase 26.43 — ADR-017)
   MissingAttempts: persisted evidence counter for the missing-fixture safeguard
         │
apply_df_results_to_manual_bets()
   └─ copies resultado/lucro/placar/settlementReason back to bet objects (1:1 index)
   └─ always copies missingAttempts, even for a bet that stays unresolved
   └─ status → 'settled' UNLESS status was already 'rejected' (ADR-012)
         │
   if newly_settled > 0 OR evidence_changed > 0:
         │ GitHub Contents API PUT (upload)
         ▼
cloud_state.json (GitHub) — manualBets array updated
         │
         │ GET /load (user-triggered or post-settlement)
         ▼
   state.manualBets refreshed
         │
         ▼
   Dashboard (Live Center clears; History → Resolvidas populates for
   approved bets, History → Rejeitadas populates for rejected bets;
   rejected bets never reach Analytics/Bankroll)
```

**Rejected bets are not filtered out anywhere in this pipeline** — `manual_bets_to_settlement_df()` converts every bet regardless of `status`, so a rejected bet's fixture is looked up, matched, and settled by the exact same code path as an approved one. The only place lifecycle status is consulted is the single line in `apply_df_results_to_manual_bets()` that skips the `status → 'settled'` transition for already-`'rejected'` bets.

### Convergence Point

Both pipelines call `update_dataframe(df, label, shared_state)` with identical arguments. The `shared_state` object is shared across the bot and manual settlement runs in a single execution. This means API responses cached during bot pick settlement (e.g. fixtures for a league and date) are reused when settling manual bets for the same league and date — saving API quota.

---

## 6. Persistence Flow

### `cloud_state.json`

| When | Who writes | Why |
|---|---|---|
| User creates/edits/approves/rejects a manual bet | Browser via `POST /save` | Every state mutation is immediately persisted to avoid data loss |
| Settlement completes with at least one new result | `run_settlement_remote()` or `main()` via GitHub Contents API PUT | Settlement results must be durable |

**Format:** JSON object containing:
- `manualBets` — array of bet objects (the single source of truth for manual bets)
- `footballDaily` — today's bot picks (populated from CSVs on load, may be stale)
- `footballHistory` — bot pick history (populated from CSVs on load, may be stale)
- `bankrollInicial` — initial bankroll amount
- `bankrollInicialSet` — boolean flag
- `sessionStartDate` — ISO date string for the current betting session
- `localEdits` — map of pick keys to user-edited fields (OddReal, StakeReal, Apostada)

---

### `picks_history.csv`

| When | Who writes | Why |
|---|---|---|
| Main generation (17:00 UTC) | `persist_history()` via `merge_into_history()` | New picks appended to permanent history |
| Top-up generation (23:00 UTC) | `_append_csv()` | Non-EU picks appended after late odds available |
| Settlement (07:00, 22:30 UTC) | `update_dataframe()` + GitHub Contents API | Results written in-place to settled rows |

Since ADR-018 (Policy A fixture-level market lock), a fixture already present in this file — in any state, unresolved or settled — can never receive a row for a *different* bot market; `apply_fixture_market_lock()` (`src/pipeline.py`) rejects the competing candidate before it reaches this stage. Same-market regeneration is unaffected and still relies on the pre-existing `[Data, Liga, Jogo, Mercado]` dedup key above.

Contains all bot picks ever generated, including unsettled ones. Settlement finds and fills the Resultado and Lucro€ columns.

---

### `picks_hoje_simplificado.csv`

| When | Who writes | Why |
|---|---|---|
| Main generation (17:00 UTC) | `save_all_outputs()` | Overwrites today's picks with simplified column set |
| Top-up generation (23:00 UTC) | `_append_csv()` | Appends non-EU picks |
| Settlement (07:00, 22:30 UTC) | `update_dataframe()` + GitHub Contents API | Results written in-place |

The dashboard's primary bot pick source. Refreshed from GitHub every 60 seconds.

---

### `picks_hoje.csv`

| When | Who writes | Why |
|---|---|---|
| Main generation (17:00 UTC) | `save_all_outputs()` | Full-column version of today's picks |
| Top-up generation (23:00 UTC) | `_append_csv()` | Appended |

Not consumed by the dashboard. Used as an internal full-detail record.

---

### `sent_state.json`

| When | Who writes | Why |
|---|---|---|
| After Telegram send (17:00 or 23:00 UTC) | `process_notifications()` | Records which pick IDs were sent today |

Date-keyed. `load_sent_state(today_iso)` returns an empty set if the stored date does not match today — this resets deduplication every day. Committed to GitHub so it persists across Actions runners.

---

### `league_stats.csv`

| When | Who writes | Why |
|---|---|---|
| After every settlement run | `update_league_stats()` + upload | Aggregates win rates and profits per league |
| After every generation run | `update_league_stats()` + upload | Updated with new picks even before results |

The browser fetches this via `loadLeagueStats()` at startup and displays it in the Analytics page.

**Persistence invariant (Phase 26.44):** regenerating this file locally has no effect on its own — GitHub Actions runners are ephemeral, so an unpushed write is discarded at job end. Prior to Phase 26.44, both call sites regenerated the file but neither uploaded it, leaving `league_stats.csv` frozen at its last manually-triggered date (2026-05-24) for ~2 months regardless of ongoing settlement/generation activity. Both call sites now upload the file in the same run it is regenerated. See `05_Known_Issues.md` ANALYTICS-1.

---

### `team_alias_cache.json`

| When | Who writes | Why |
|---|---|---|
| At the end of a settlement run when new aliases were learned | `save_team_alias_cache()` | Persists team name normalisation mappings discovered during fixture matching |

This file is written to the local filesystem of the GitHub Actions runner or the Railway container. It is **not committed to GitHub**. It is re-learned from scratch on each fresh runner. The file reduces redundant fuzzy matching within a single run but does not persist across runs.

---

## 7. Browser State Flow

### Initial State

When the page loads, all state variables start empty. `boot()` immediately calls `loadLocalState()`.

### `loadLocalState()`

Reads from `localStorage` and populates the in-memory `state` object:

```
localStorage["apostas_bot_manual_bets_v3"]  → state.manualBets
localStorage["apostas_bot_bankroll"]         → state.bankrollInicial
localStorage["apostas_bot_bankroll_set"]     → state.bankrollInicialSet
localStorage["apostas_bot_picks_v3"]         → state.localEdits
localStorage["apostas_bot_movements"]        → state.movements
localStorage["apostas_bot_session_start"]    → state.sessionStartDate
```

After this call, `state.manualBets` contains the snapshot from the last time `saveLocalState()` was called. This may be stale if settlement ran in a different session.

---

### `loadData()`

Called at startup and every 60 seconds. Fetches three CSVs from GitHub raw URLs:

```
picks_hoje_simplificado.csv → state.botPicks (today's bot picks)
picks_history.csv           → state.history  (all settled bot picks)
manual_bets.csv             → state.manualBetsRemote  (always empty)
```

Does **not** call `GET /load`. Does **not** modify `state.manualBets`.

---

### Cloud Recovery

After `loadData()` completes, `boot()` checks `hasMeaningfulLocalState()`:

```javascript
hasMeaningfulLocalState() returns true if:
  state.bankrollInicialSet === true
  OR state.localEdits has entries
  OR state.manualBets.length > 0
  OR state.movements.length > 0
```

If `false` (fresh browser session, no localStorage), `_doLoadCloudState()` runs automatically:
- `GET /load` → Railway → GitHub → `cloud_state.json`
- `state.manualBets` ← `content.manualBets`
- `state.bankrollInicial` ← `content.bankrollInicial`
- `state.localEdits` ← `content.localEdits`
- `saveLocalState()` — writes cloud data into localStorage

If `true`, auto-recovery is **skipped**. The localStorage snapshot is used as-is.

---

### `saveLocalState()`

Called after every state mutation. Serialises `state.manualBets`, `state.localEdits`, `state.bankrollInicial`, and other fields back to `localStorage`. This write is always synchronous and in-process.

`saveLocalState()` does **not** call `POST /save`. It only writes to `localStorage`. The cloud write (POST /save) is triggered separately after state mutations that need persistence.

---

### Relationship Between `state.manualBets` and `cloud_state.json`

```
cloud_state.json (GitHub)
        │
        │ GET /load (explicit user action or startup recovery)
        ▼
state.manualBets (in-memory)
        │
        │ saveLocalState() — always synchronous
        ▼
localStorage["apostas_bot_manual_bets_v3"]
        │
        │ loadLocalState() — on next page load
        ▼
state.manualBets (restored)
```

`localStorage` is a write-through cache of the last cloud load. It is always one cloud-load behind: if settlement runs externally (GitHub Actions) and writes new results to `cloud_state.json`, `localStorage` still holds the pre-settlement snapshot until the user explicitly loads from the cloud.

The cloud is the authoritative state. `localStorage` is the working copy.

---

## 8. Synchronisation Flows

### Dashboard → Railway (cloud state save)

| Property | Value |
|---|---|
| Trigger | User creates, edits, approves, or rejects a manual bet |
| Direction | Browser → Railway |
| Data | Full `cloud_state.json` content as JSON body in `POST /save` |
| Frequency | On every state-mutating action (not throttled) |
| Synchrony | Asynchronous (browser does not block UI; shows a save toast) |

---

### Dashboard → Railway (settlement)

| Property | Value |
|---|---|
| Trigger | User clicks "Run Settlement" button |
| Direction | Browser → Railway → external result APIs → GitHub → Railway → Browser |
| Data | `POST /run-settlement` request; settlement result dict in response |
| Frequency | On-demand only |
| Synchrony | Synchronous end-to-end (browser awaits the full `/run-settlement` response, which may take up to ~90 seconds) |

After the response returns, `_reloadManualBetsFromCloud()` is called automatically to pull the newly settled state back into `state.manualBets`.

---

### Railway → GitHub

| Property | Value |
|---|---|
| Trigger | Any `/save` or `/run-settlement` request |
| Direction | Railway → GitHub Contents API |
| Data | `cloud_state.json` content encoded as base64 (PUT request) |
| Frequency | Per browser action |
| Synchrony | Synchronous within the Railway request handler |

Every write fetches the current SHA first (one GET), then PUTs the new content. No caching on the Railway side.

---

### GitHub Actions → GitHub

| Property | Value |
|---|---|
| Trigger | Scheduled cron (07:00, 17:00, 22:30, 23:00 UTC) or `workflow_dispatch` |
| Direction | GitHub Actions runner → GitHub Contents API |
| Data | `picks_history.csv`, `picks_hoje_simplificado.csv`, `picks_hoje.csv`, `league_stats.csv`, `sent_state.json` |
| Frequency | 2–4 times per day |
| Synchrony | Synchronous within the Actions step |

---

### Dashboard → GitHub CSVs

| Property | Value |
|---|---|
| Trigger | Page load; every 60 seconds (setInterval in `boot()`) |
| Direction | Browser → GitHub raw HTTPS URLs |
| Data | `picks_hoje_simplificado.csv`, `picks_history.csv`, `league_stats.csv` (read-only GET) |
| Frequency | Startup + every 60 seconds |
| Synchrony | Asynchronous (awaited in `loadData()`; UI renders before and after) |

No authentication. GitHub raw URLs are publicly accessible.

---

### Settlement → Dashboard

| Property | Value |
|---|---|
| Trigger | Settlement completion (GitHub Actions or Railway) |
| Direction | Indirect: `cloud_state.json` updated on GitHub → browser must call GET /load |
| Data | Updated `manualBets` array inside `cloud_state.json` |
| Frequency | Automatic only when settlement is triggered from the current browser session |
| Synchrony | Not automatic when settlement runs externally (GitHub Actions); requires explicit user action |

There is no push mechanism. The browser is not notified when GitHub Actions updates `cloud_state.json`. The settlement result reaches the browser only when the user clicks "Load Cloud" or triggers settlement from the current session.

---

## 9. Data Ownership Matrix

| Dataset | Owner | Producer | Consumers | Persistent? | Source of Truth |
|---|---|---|---|---|---|
| `manualBets` array | `cloud_state.json` | Browser (via Railway /save); settlement (results) | Browser dashboard (Live Center, History, Analytics) | Yes — GitHub | `cloud_state.json` on GitHub |
| Bot picks (today) | `picks_hoje_simplificado.csv` | GitHub Actions main generation | Browser (loadData); settlement engine | Yes — GitHub | CSV on GitHub |
| Bot picks (history) | `picks_history.csv` | GitHub Actions generation + settlement | Browser (loadData); settlement engine | Yes — GitHub | CSV on GitHub |
| Bot pick results | `picks_history.csv` (Resultado column) | Settlement engine (`update_dataframe()`) | Browser (loadData) | Yes — GitHub | CSV on GitHub |
| League statistics | `league_stats.csv` | Settlement pipeline (`update_league_stats()`) | Browser (loadLeagueStats) | Yes — GitHub | CSV on GitHub |
| Notification deduplication | `sent_state.json` | Main generation pipeline | Main generation pipeline | Yes — GitHub | JSON on GitHub |
| Local bot pick edits (OddReal etc.) | `state.localEdits` | Browser (user input) | Browser (History, Analytics display) | Yes — localStorage + `cloud_state.json` | `cloud_state.json` (authoritative); localStorage (working copy) |
| Browser session state | `state.*` | Browser (runtime) | Browser (all pages) | Partially (via localStorage) | localStorage (lost on clear) |
| Team name aliases | `team_alias_cache.json` | Settlement engine (learned during run) | Settlement engine (same run) | Local only (not GitHub) | Not durable across runs |
| Fixtures for picks | `fixtures_today.csv` | `fetch_oddsapi_fixtures.py` | `main.py` (generation only) | No — ephemeral | Not durable |
| Fixtures for settlement | In-memory cache | `fetch_matches_for_league_date()` or `fetch_api_football_fixtures_for_league_date()` | `update_dataframe()` | No — in-memory per run | Not persistent |

---

## 10. Data Integrity Rules

**One source of truth per dataset.** `cloud_state.json` owns manual bets. The picks CSVs own bot picks. No code should read manual bets from a CSV or write bot results to `cloud_state.json`. Mixing ownership creates state that diverges.

**Browser localStorage is a cache, not authoritative.** `localStorage` holds the last-loaded copy of `cloud_state.json`. If the cloud changes (e.g. external settlement), `localStorage` becomes stale. The dashboard's correctness depends on the user reloading from the cloud after external changes.

**Settlement skips rather than errors.** A row that cannot be settled this run is left unchanged. The settlement engine never writes partial results or zeros. An unsettled row will be retried on the next run.

**The shared settlement engine prevents divergence.** Both bot and manual bets are settled by `update_dataframe()`. A bug fix or behavioural change to settlement logic applies to both automatically. Duplicating settlement logic is prohibited.

**Every cloud write is a full replacement.** `POST /save` always sends the complete `cloud_state.json` content. There is no partial update or patch operation. This means concurrent saves (two browser tabs, or a browser save racing with settlement) will produce a last-write-wins outcome. The losing write is silently overwritten.

**CSV uploads use the GitHub SHA.** Before every `PUT` to the GitHub Contents API, the current SHA is fetched. Without a correct SHA, GitHub rejects the PUT with HTTP 409. This is the only concurrency guard in the system. It protects against overwriting a file with stale content but does not prevent two writers from racing.

**Settlement writes to `cloud_state.json` only when necessary.** `save_cloud_state_to_github()` is called only when `newly_settled > 0`. If no manual bets are newly settled (all ALREADY_DONE or skipped), `cloud_state.json` is not written and the SHA is not consumed. This reduces the risk of conflicting writes.

**`localEdits` is merged, not replaced, on cloud load.** When `_doLoadCloudState()` loads `cloud_state.json`, it calls `migrateLocalEditsKeys(content.localEdits)` to normalise keys before assigning. Edits made in the current session that are not in the cloud snapshot are lost. The cloud copy takes precedence on explicit load.

**`sent_state.json` is date-keyed.** If the stored date does not match today, `load_sent_state()` returns an empty set. This prevents yesterday's sent IDs from suppressing today's Telegram notifications without requiring a manual reset.

---

## 11. Backup & Disaster Recovery Flow (Phase 27.2)

See `04_Backend.md` §16 and `09_Architecture_Decisions.md` ADR-020 for full detail. This flow is additive — none of the flows above (§1–§10) changed.

**Backup creation (scheduled — GitHub Actions, every 6h):**
```
bot.yml `backup` job
 │
 ├─ actions/checkout already has every production file on disk
 ├─ backup_job.py reads config.json["backup"]["files"] from disk
 ├─ src/backup/backup_engine.create_backup('scheduled', ...)
 │   ├─ builds one ZIP fully in memory (no disk write, ever)
 │   ├─ uploads to R2, HEAD-verifies
 │   ├─ records the entry in backups/index.json (R2, not Railway)
 │   └─ runs retention (evicts oldest scheduled backups beyond the cap)
 └─ exits 0 whether or not R2 is configured — never fails this workflow run
```

**Backup creation (manual / critical — Railway, on demand):**
```
Browser → POST /backup/create {type, reason, extraPayload}
 │
 └─ sync_server.py
     ├─ src/backup/github_files.fetch_files() — fresh GitHub Contents API GET per file
     │   (no local checkout on Railway, unlike the GitHub Actions path above)
     ├─ create_backup(...) — identical engine, identical ZIP-in-memory/upload/verify/index/retention cycle
     └─ returns the new backup's entry to the browser
```
`executeSeasonClose()`'s new Step 0 calls this with `type: 'critical'`, `reason: 'pre_season_close'`, and `extraPayload` set to the Season Archive object itself — the first time that object has ever had a durable copy outside the browser's `localStorage` (see `03_Dashboard.md`'s Season Archive section).

**Restore:**
```
Browser → POST /backup/validate-restore {id}   (dry run, changes nothing)
Browser → POST /backup/restore {id, confirmed: true}
 │
 └─ sync_server.py → src/backup/backup_restore.restore()
     ├─ rebuild_index_from_r2() — the catalog is always re-derived from R2's own
     │   listing first, never trusted from a prior read (Railway holds no state
     │   between requests — unchanged existing rule, §6 above)
     ├─ downloads + re-validates the target archive
     ├─ takes a mandatory fresh 'critical' backup of GitHub's CURRENT state —
     │   aborts the whole restore, writes nothing, if this snapshot fails
     └─ writes every archived file back to GitHub via the Contents API
         (github_files.write_file — the existing github_put_file() primitive,
         same GET-SHA-then-PUT pattern every other GitHub write in this project uses)
```

**What does not change:** GitHub remains the only thing the browser, GitHub Actions, and Railway all read from — a restore is an ordinary, auditable git commit, not a new read path any existing consumer needs to learn.

**Data ownership addition:** the R2 bucket owns backup archives and the backup catalog (`backups/index.json`) — a separate store from every row in §9's Data Ownership Matrix above, which remains entirely about GitHub-tracked production files. Nothing in that matrix changed.
