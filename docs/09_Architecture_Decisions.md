# Architecture Decisions

This document records architectural decisions that are considered established. It explains *why* each decision was made so it is not accidentally reversed. For what the current system does, see `01_Architecture.md` and `04_Backend.md`. For design principles stated as rules, see `00_Project_Context.md`.

---

## ADR-001 — `cloud_state.json` Is the Single Source of Truth for Manual Bets

**Status:** Accepted

**Date:** 2026-06-28 (Phase 26.16)

**Decision**

All manual bet data is read from and written to `cloud_state.json`. No other file stores manual bet state. `manual_bets.csv` exists in the repository as a legacy file with a header row only and is not read by any active code path.

**Context**

Prior to Phase 26.16, manual bet settlement attempted to read from `manual_bets.csv`. That file was never written with bet data in the Railway deployment — it was a leftover from an earlier design. Settlement silently operated on an empty file, and manual bets were not settled. The decision was made to make the actual data source (`cloud_state.json`) the declared source of truth and remove the dead CSV path entirely.

**Reasoning**

A system with two declared sources of truth for the same dataset will always diverge. `cloud_state.json` was already the de-facto source: the browser wrote to it, the Railway `/save` endpoint wrote to it, and the browser read from it. Formalising this removes the ambiguity and eliminates the failure mode where settlement operates on the wrong file.

**Consequences**

- Settlement is always operating on current data.
- Any code that reads manual bets must go through the Railway `/load` endpoint or the GitHub Contents API directly.
- `manual_bets.csv` cannot be repurposed without a conscious architectural decision.

**Do Not Revert Without Good Reason**

Reinstating `manual_bets.csv` as an active store would create two persistence paths for manual bets. Settlement would need to know which source to trust, and divergence between them would become a source of silent data loss.

---

## ADR-002 — Bot and Manual Bets Share the Same Settlement Engine

**Status:** Accepted

**Date:** 2026-06-28 (Phase 26.16)

**Decision**

`update_dataframe()` in `update_results.py` is the single settlement function. It accepts any DataFrame with the standard CSV column schema. Manual bets are converted to this schema, settled by the same function, and converted back. No separate settlement logic exists for manual bets.

**Context**

When manual bet settlement was introduced, the simplest implementation would have been a separate code path: different market normalisation, different profit calculation, different API queries. This was rejected because it would create two implementations of the same logic that could drift independently.

**Reasoning**

If a market result is calculated incorrectly for bot picks, it is calculated the same way for manual bets, which means the bug surfaces immediately. If the calculation is corrected for one, it is corrected for both. A separate pipeline would allow silent divergence: manual bets settled by different rules, producing different profit figures, without any obvious inconsistency.

**Consequences**

- All settlement behaviour — API selection, team name matching, market calculation, profit calculation, retry logic — applies equally to both bet types.
- Adding a new market type requires only one change (`market_result()`) and both bet types support it automatically.
- Manual bet objects must be convertible to the standard CSV row schema. The `manual_bets_to_settlement_df()` and `_normalize_market_code()` functions maintain this bridge.

**Do Not Revert Without Good Reason**

A separate settlement engine for manual bets would immediately diverge from the bot engine over time. Bugs would be fixed in one but not the other. Two implementations of the same profit calculation will eventually produce different numbers.

---

## ADR-003 — GitHub Is the Persistence Layer; Railway Is Stateless

**Status:** Accepted

**Date:** 2026-06 (Phase 26.11)

**Decision**

All persistent data is stored in files committed to the GitHub repository. The Railway server holds no state between requests. Every request that reads or writes data does so via the GitHub Contents API. Railway can be restarted, redeployed, or replaced without data loss.

**Context**

The project has no infrastructure budget for a dedicated database. GitHub was already required for the pick pipeline — CSVs are committed by GitHub Actions as part of pick generation. Using GitHub for `cloud_state.json` as well means the entire system has one storage backend, and all state is inspectable and recoverable from the repository.

**Reasoning**

A stateless server eliminates an entire class of failure: no stale in-memory cache, no state loss on restart, no multi-instance consistency problems. GitHub provides durable, versioned storage with a standard REST API. Every write is a commit with a timestamp and message, providing a complete audit trail with no additional logging infrastructure.

The cost — two API calls per write (GET for SHA + PUT) and a risk of SHA conflict under concurrency — is acceptable given the project's low write frequency. The benefit — zero operational complexity for the persistence layer — outweighs it.

**Consequences**

- Every file write requires fetching the current SHA first.
- SHA conflicts can occur when two processes write the same file simultaneously. The current mitigation is `--workers 1` in gunicorn, which serialises Railway writes.
- GitHub rate limits apply (5000 requests/hour for authenticated requests). The project is well within this.
- All persistent data is human-readable and can be edited directly in the repository if needed.

**Do Not Revert Without Good Reason**

Introducing a database alongside GitHub would create a split persistence model. Settlement results would need to be kept in sync between GitHub (for the browser CSVs) and the database (for API queries). The current system's strength is that there is exactly one place to look for any piece of data.

---

## ADR-004 — The League Registry Is the Only Location Where League Metadata Is Maintained

**Status:** Accepted

**Date:** 2026-06 (Phase 26.11)

**Decision**

`src/league_registry.py` is the single file where league metadata is defined. All derived structures (`LEAGUE_CODE_MAP`, `BLOCKED_FOOTBALL_DATA_CODES`, `API_FOOTBALL_FALLBACK_COMPETITIONS`, `AF_SEASON_MODELS`, `REGISTRY_BY_KEY`) are generated automatically from the `REGISTRY` list. No league mapping, settlement routing code, or season model is defined anywhere else.

**Context**

Before the registry was introduced, league metadata was scattered: competition codes were in `update_results.py`, API-Football IDs were in `config.json`, and the mapping between display names and settlement codes was maintained manually. Adding a new league required changes in multiple files, and an inconsistency between files caused settlement to silently fail for affected leagues.

**Reasoning**

A league has a fixed set of properties: its display name, its football-data.org code, whether that code is blocked, its API-Football ID, its country, and its season model. All of these properties belong together. Splitting them across files creates the possibility of partial updates — a league added to `config.json` but missing from the settlement routing, or a season model changed in one place but not another.

The registry enforces coherence: you cannot add a league without specifying all its properties, and the derived structures are always consistent with the source.

**Consequences**

- Adding a league requires editing exactly one file (`src/league_registry.py`) and two sections of `config.json` (display name and API-Football ID). The registry entry drives all settlement routing automatically.
- The settlement engine (`update_results.py`) imports derived structures from the registry and contains no league-specific logic of its own.
- Removing a league from the registry removes it from all derived structures simultaneously.

**Do Not Revert Without Good Reason**

Returning to distributed league metadata means that any future modification — changing a season model, adding an API-Football fallback — requires finding and updating every file that holds a fragment of the league's definition. The history of this project includes silent settlement failures caused by exactly this kind of inconsistency.

---

## ADR-005 — The Frontend Is a Single Self-Contained HTML File with No Framework and No Build Step

**Status:** Accepted

**Date:** Project inception

**Decision**

`index.html` contains all application code inline: HTML structure, CSS, and JavaScript in a single `<script>` block. There is no npm, no bundler, no transpiler, no framework, no module system, and no build step. Deployment is committing the file to GitHub.

**Context**

The dashboard serves a single user with a real-money betting application that must always be accessible. Introducing a build pipeline adds operational complexity: Node.js version pinning, dependency management, build failures that block deployment, and a longer path from change to production. For a personal project with no team and no CI/CD requirement beyond GitHub Actions, this cost is not justified.

**Reasoning**

A single HTML file is deployable anywhere, readable in any browser, and debuggable with standard browser DevTools. The rendering model (read from `state`, produce HTML, replace DOM) is simple and deterministic without requiring a reactive framework. The application's complexity is in business logic (Poisson model, Kelly staking, settlement routing), not in UI interaction patterns that benefit from component abstractions.

The absence of a build step means that every change is immediately testable. There is no concept of a "build breaking".

**Consequences**

- All JavaScript is in one file, which is large (~13 000+ lines).
- No tree-shaking, minification, or dead code elimination.
- No TypeScript type checking.
- Adding a framework at a later date would require a rewrite, not an incremental migration.
- Each render function is responsible for its own DOM output. There is no component lifecycle.

**Do Not Revert Without Good Reason**

Migrating to a framework would require rebuilding the entire application. The current design is intentional: the complexity is in the data layer, which is well-understood, and the rendering model is simple enough that it does not need a framework to remain maintainable. A framework introduces a dependency with its own upgrade cycle, breaking changes, and failure modes.

---

## ADR-006 — Settlement Is Synchronous

**Status:** Accepted

**Date:** 2026-06 (Phase 26.11)

**Decision**

Settlement is a single synchronous function call. `POST /run-settlement` blocks until settlement completes and returns the result directly. There is no queue, no background worker, no polling endpoint, and no webhook. The browser waits for the HTTP response.

**Context**

When on-demand settlement was introduced via Railway, an asynchronous design (accept the request, return a job ID, poll for completion) was considered. It was rejected as unnecessarily complex for the project's scale.

**Reasoning**

A typical settlement run completes in 40–90 seconds. The gunicorn timeout is 300 seconds. The browser can hold an HTTP connection open for this duration. An asynchronous design would require: a job store (another persistence layer), a polling endpoint (additional API surface), and state management in the browser (tracking job ID, polling interval, result display). These add complexity without solving a real problem at the current scale.

The single-worker gunicorn configuration ensures that only one settlement can run at a time, preventing concurrent GitHub writes. This is not a limitation of the synchronous design — it would be required even with an async design.

**Consequences**

- The browser UI is unresponsive for the duration of settlement when triggered from the dashboard.
- A very long settlement run (> 300 seconds) would be killed by gunicorn and return HTTP 500. This has not occurred in production.
- Settlement triggered by GitHub Actions (at 07:00 and 22:30 UTC) is fully independent of Railway and is not affected by the synchronous design.

**Do Not Revert Without Good Reason**

Introducing an async settlement pipeline requires a job store (a new persistence layer), a polling mechanism, and additional browser state management. This is a significant increase in system complexity. The synchronous design should be retained until settlement runs routinely exceed 250 seconds, which would require a fundamentally different scale of operation.

---

## ADR-007 — Browser localStorage Is a Cache, Never Authoritative

**Status:** Accepted

**Date:** 2026-06 (Phase 26.15)

**Decision**

`localStorage` holds a working copy of `cloud_state.json`. It is written by `saveLocalState()` for fast access across page loads and written by `saveCloudState()` to the cloud. When `cloud_state.json` and `localStorage` diverge, `cloud_state.json` is authoritative. The cloud always wins.

**Context**

Early in the project, localStorage was treated as the primary data store and the cloud as a backup. This caused a failure mode: settlement ran on the backend and updated `cloud_state.json`, but the browser continued displaying stale data from localStorage, showing settled bets as LIVE (LIVE-1).

**Reasoning**

The browser is one possible client. Settlement runs independently on GitHub Actions. Both can modify `cloud_state.json`. If localStorage were authoritative, any backend operation would be invisible to the browser until a manual reload. The cloud must be the authority because it is the only store that all writers share.

localStorage exists for performance: page loads are immediate because data is already in memory. It is not the source of truth. Any code path that treats localStorage as authoritative will produce stale displays.

**Consequences**

- Fresh browser sessions with no localStorage recover from `cloud_state.json` automatically (via `_doLoadCloudState()` in `boot()`).
- Settlement results written by GitHub Actions or a different browser session are not visible until the browser explicitly fetches from the cloud.
- LIVE-1 is a consequence of the 60-second interval not refreshing `state.manualBets` from the cloud. The fix is to add a periodic cloud refresh, not to make localStorage more authoritative.

**Do Not Revert Without Good Reason**

Making localStorage authoritative would mean that any backend operation (GitHub Actions settlement, Railway settlement from a different browser) must coordinate with every client's localStorage to ensure consistency. This is not possible in the current architecture. localStorage can only be kept consistent by regularly overwriting it from the cloud.

---

## ADR-008 — Manual Settlement Must Not Introduce a Second Persistence Model

**Status:** Accepted

**Date:** 2026-06-28 (Phase 26.16)

**Decision**

Manual bet persistence has one path: browser → Railway → GitHub → `cloud_state.json`. Every operation that reads or modifies manual bets uses this path. There is no direct database write from the backend, no separate state file for manual results, and no merge required between multiple stores.

**Context**

When manual settlement was implemented, the tempting shortcut was to write settlement results to a separate file (e.g. `manual_results.json`) that could be read without loading all of `cloud_state.json`. This was rejected because it would create a second persistence model: `cloud_state.json` would hold the current bet objects, but their results would be in a different file.

**Reasoning**

A second persistence model requires merge logic: when displaying a bet, you must load both the bet object (from `cloud_state.json`) and its result (from the second file), join them, and handle cases where one exists without the other. This join logic is a recurring source of bugs. Every operation — display, analytics, history, export — must perform the same join.

The current design is simpler: a manual bet is a single JSON object. Its `resultado` field is either empty (unsettled) or `W`/`L`/`P` (settled). No join is needed. Any code that loads `manualBets` has complete information.

**Consequences**

- The entire `cloud_state.json` must be read and written for any manual bet operation, even if only one bet's result changes.
- The file grows over time as settled bets accumulate. Current size is not a concern.
- All manual bet state is co-located and consistent by definition.

**Do Not Revert Without Good Reason**

Splitting manual bet data across two files introduces a consistency problem that must be managed forever. The current design's simplicity — one file, one source of truth, no joins — prevents an entire class of bugs.

---

## ADR-009 — Shared Implementation for Equivalent Bot and Manual Behaviour

**Status:** Accepted

**Date:** 2026-06 (Phase 26.16)

**Decision**

When bot picks and manual bets require the same operation, they share one implementation. Market result calculation, profit calculation, team name matching, and settlement API routing apply identically to both. Separate implementations are not created even when the data formats differ (the format difference is bridged by `manual_bets_to_settlement_df()`).

**Context**

This principle emerged from the settlement unification in Phase 26.16. Before that phase, a separate (incomplete) settlement path existed for manual bets. That path had different market codes, different profit calculation, and different API routing. The bugs in that path were distinct from (and invisible to) the bugs in the bot pick path.

**Reasoning**

Two implementations of the same logic drift apart. A bug fixed in one is not fixed in the other. A feature added to one must be added to both. The cognitive overhead of remembering that the same concept has two implementations increases with every change. Shared implementations are tested by both usage contexts simultaneously: a bug in `market_result()` breaks both bot and manual settlement at the same time, making it visible immediately.

**Consequences**

- The data format bridge (`manual_bets_to_settlement_df()`) must be maintained when the standard CSV schema changes.
- Manual bets must be expressible in the standard schema. If a manual-bet-only feature requires schema columns that have no bot pick equivalent, this principle must be revisited.

**Do Not Revert Without Good Reason**

Diverging implementations will produce different results for the same underlying event. A manual bet on "Over 2.5" in a match ending 2-0 must produce the same `"L"` result as a bot pick on the same match. Any implementation that produces a different result is a bug, and the risk of that bug increases with every line of code that separates the two implementations.

---

## ADR-010 — Configuration Belongs in Environment Variables or `config.json`; Not in Code

**Status:** Accepted

**Date:** Project inception (formalised 2026-06)

**Decision**

Values that vary by deployment (API keys, credentials, repository coordinates, API rate limits) are environment variables on Railway or GitHub Actions secrets. Values that control model behaviour (edge thresholds, Kelly fraction, bankroll amounts, Poisson decay) are in `config.json`. Production values are not hardcoded in source files.

**Context**

Early versions of the pipeline had bankroll amounts, API keys, and rate limits hardcoded. This meant changing any production value required a code commit. It also meant the same value appeared in different places (code, comments, documentation) and could become inconsistent.

**Reasoning**

Hardcoded production values create three problems. First, they expose secrets in source code. Second, they make configuration changes require code review and deployment. Third, they scatter the system's operational parameters across source files rather than concentrating them in a single place.

Environment variables separate secrets from code and allow Railway configuration to change without a code change. `config.json` separates model parameters from implementation and makes them inspectable without reading Python source. The split is deliberate: `config.json` is committed to the repository (model parameters are not secrets), while environment variables are not.

**Consequences**

- Adding a new configurable parameter requires adding a key to `config.json` and a `DEFAULT_` constant in `src/config.py`. It does not require changing any other file.
- API rate limits (API-Football requests/day) are Railway environment configuration. Changing them does not require a code change or a redeploy.
- `config.json` is the canonical source for all model tuning parameters. Documentation and code reference it by key name.

**Do Not Revert Without Good Reason**

Hardcoding a production value — particularly an API key, a rate limit, or a bankroll amount — creates a hidden coupling between the code and a specific deployment. The next time the value needs to change (and it will), the change requires finding all occurrences in code, updating them, committing, and deploying. A misconfigured but deployed value also becomes invisible: the code "looks correct" even when running with the wrong parameters.
