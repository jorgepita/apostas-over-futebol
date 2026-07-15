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

---

## ADR-011 — Provider API Responses Are Validated for Embedded Errors Before Being Trusted; Provider Health Lives in `cloud_state.json`

**Status:** Accepted

**Date:** 2026-07-07 (Phase 26.18)

**Decision**

Every API-Football response is checked for a meaningful `errors` field before its `response`/`matches` payload is trusted, even on HTTP 200. Any provider failure — whether signalled by an HTTP error status or by a 200 response with a meaningful `errors` field — is normalized into one record shape (`build_provider_error()`: `provider, endpoint, request, category, message, retryable, timestamp`) and recorded, rather than being allowed to look like a genuine empty result. The resulting per-provider health state (`status`, `consecutiveFailures`, `lastError`, ...) is persisted as a new top-level field in `cloud_state.json` (`providerHealth`) — no new file, no new database.

**Context**

In July 2026, the API-Football subscription lapsed to the Free plan. API-Football's `/fixtures` endpoint responded with HTTP 200, an empty `response: []`, and a `errors.plan` field stating the requested season wasn't covered. `update_dataframe()` had no code path that inspected `errors` on a successful HTTP response — it read `response`, got an empty list, and treated that identically to "no games scheduled today". Every currently-open pick in a league routed through API-Football (all non-EU leagues, plus any EU league falling back to API-Football) came back `NO_MATCH`, and the dashboard's "No matches to settle." message gave no indication a provider was the actual cause. Root-caused via a temporary, read-only audit of the live pipeline (see `08_Change_Log.md` Phase 26.18); renewing the subscription fixed it with zero code changes, confirming the settlement/matching logic itself was sound — the gap was response validation, not decision logic.

**Reasoning**

An HTTP 200 status code means the request reached the server and the server chose to respond; it does not mean the request was honoured. Treating "response body I can decode" as synonymous with "request succeeded" throws away the one piece of information (the `errors` field) that would have made this failure visible from the very first affected settlement run instead of persisting silently for days. Classifying by message content first (`"plan"`, `"quota"`, `"token"`, ...) and falling back to HTTP status only when no message is available (`classify_provider_error()`) gives a specific, actionable category instead of a generic "something went wrong".

Persisting the resulting health state in `cloud_state.json` rather than a new file or database follows directly from ADR-003 (Railway is stateless; GitHub is the persistence layer) and the spirit of ADR-008 (no second persistence model for state that belongs with the rest of the settlement/bet data) — `cloud_state.json` is already the single JSON blob the dashboard reads on every load, so adding one more key to it is consistent with how `movements` was added, not a new architectural surface.

**Consequences**

- `api_football_get()` can raise a new exception type, `ProviderError`, on a 200 response — callers that used to only catch `error.HTTPError`/`Exception` now also catch `ProviderError` explicitly (checked first, so it isn't silently absorbed by a broad `except Exception`).
- The specific "HTTP 200 + meaningful `errors`" case changes behaviour: it used to return `([], "")` (a trusted empty result); it now returns `(None, "PROVIDER_ERROR")` (an untrusted failed fetch), which is the one deliberate behavioural change in Phase 26.18. Every other existing failure path (`"HTTP {code}"`, `"OTHER"`, `"NO_LEAGUE_ID"`, ...) keeps its exact prior reason string and control flow.
- `cloud_state.json` is now written slightly more often — whenever a settlement run contacts any provider, not only when a manual bet newly settles — to keep `providerHealth` current even on a run that settles nothing.
- The dashboard, settlement summary, and logs all read from the same normalized error record, so a provider failure cannot be described differently (or lost) at different layers.

**Do Not Revert Without Good Reason**

Reverting to "HTTP 200 means trust the body" would silently reintroduce the exact failure mode this ADR exists to close: a provider can reject every request for days and the only visible symptom is an ambiguous "No matches to settle." with no record of why. Moving provider health to a separate file or database would violate ADR-003/ADR-008's reasoning for the same cost/benefit reasons already established for manual bets and movements.

---

## ADR-012 — A Manual Bet's Lifecycle Status Is Independent From Its Settlement Result; Rejected Is a Terminal, Analytical Lifecycle State

**Status:** Accepted

**Date:** 2026-07-10 (Phase 26.19)

**Decision**

A manual bet has two independent axes of state, not one: **lifecycle status** (`pending` → `approved` → `settled`, or `rejected`) and **settlement result** (`resultado`: `''`/`W`/`L`/`P`, plus the analytical `placar` final-score field). `status` and `resultado` are never combined into a single compound value (no `"rejectedWin"`, no `"approvedLoss"`). Once a bet's lifecycle status is `rejected`, it stays `rejected` forever — settlement is still allowed to populate `resultado`, `lucro`, and `placar` on it (see ADR-013's companion behaviour in `apply_df_results_to_manual_bets()`), but settlement completing never flips a rejected bet's status to `settled`. Every other lifecycle status continues to transition to `settled` on settlement exactly as before.

**Context**

Before this phase, `apply_df_results_to_manual_bets()` unconditionally set `bet['status'] = 'settled'` the moment a bet's `resultado` was written, regardless of what `status` had been beforehand. Because `manual_bets_to_settlement_df()` and `update_dataframe()` never filtered by lifecycle status — every non-`W`/`L`/`P` manual bet was already fed through the shared settlement engine — a rejected bet whose fixture finished would flow through settlement, get a real result, and have its `status` silently overwritten from `rejected` to `settled`. The fact that the user had passed on the opportunity was lost the moment the fixture ended, and the bet would then satisfy every "is this bet resolved/real" check in the frontend (`getResolvedManualBets()`, the main History table, bankroll/ROI aggregation), incorrectly affecting real money figures with a bet that was never actually placed.

**Reasoning**

Workflow state (did the user act on this opportunity, and how) and match outcome (what actually happened in the game) are different questions answered by different actors at different times — the user decides lifecycle, the result API decides settlement. Conflating them into one field forces a choice at settlement time between "know the result" and "remember the rejection," and the existing code had already made the wrong choice by accident. Keeping them as two fields means: querying "is this rejected" is always `status === 'rejected'`, independent of whether it has been settled; querying "is this resolved for financial purposes" is always `status !== 'rejected' && resultado in {W,L,P}`; and no third combined vocabulary (`RejectedWin`, `RejectedLoss`, ...) ever needs to be invented, because the two axes are already orthogonal. This is an extension of the existing partial separation — `status` and `resultado` were already two different fields — not a new field or a migration; existing `pending`/`approved`/`settled` bets are entirely unaffected.

**Consequences**

- `getResolvedManualBets()` (frontend) filters out `status === 'rejected'` in addition to its existing `_lucro !== null` check — the single change point for every bankroll/ROI/analytics/versus consumer.
- A new `getRejectedManualBets()` accessor exists for analytical-only consumption (the Rejected History view — see ADR-013's sibling entry in `03_Dashboard.md`).
- The "Aprovar"/"Rejeitar" buttons in the Manual Bets list remain bidirectional: a user can still un-reject a bet (moving it back to `approved`), at which point it starts counting financially like any other approved bet — this is an intentional consequence of keeping the two axes independent, not a special case.
- `cloud_state.json`'s `manualBets` schema is unchanged (no migration): existing bets with `status: 'settled'` from before this phase are read exactly as before.

**Do Not Revert Without Good Reason**

Re-merging these into a single field reintroduces exactly the bug this ADR fixes: a rejected bet reaching a real match result silently loses the fact that it was rejected, and starts polluting real bankroll/ROI figures with a bet the user explicitly declined to place.

---

## ADR-013 — Duplicate Manual Bet Protection Lives in the Existing `/save` Endpoint, Not a New Create Endpoint

**Status:** Accepted

**Date:** 2026-07-10 (Phase 26.19)

**Decision**

The backend rejects duplicate manual bets — two bet records for the same fixture + market — inside the existing `POST /save` handler in `sync_server.py`, by silently dropping later duplicates (keeping the earliest) before writing to GitHub. No new "create manual bet" endpoint is introduced. The frontend independently guards against creating a duplicate at the moment of creation (`findManualBetByOpportunity()`, checked in both the Scout create path and the manual-entry-form path); the backend check is the authoritative backstop, not the primary mechanism.

**Context**

This project has no REST "create a manual bet" operation (see ADR-001/ADR-008): the browser holds the full `manualBets` array in memory and periodically `POST /save`s the entire `cloud_state.json` blob (debounced 4 seconds). A "prevent duplicate creation" rule therefore cannot live in a create handler that doesn't exist. The two realistic sources of a duplicate reaching the cloud are (a) a frontend bug or a race — two rapid clicks, two browser tabs — producing two bet objects with the same fixture+market before either save fires, and (b) the Scout UI's own state briefly allowing a second create before its next re-render hides the card. The frontend now guards against both at creation time; this ADR is about the server-side backstop for whatever gets past that guard regardless of cause.

**Reasoning**

Adding a dedicated endpoint (e.g. `POST /manual-bets`) purely to get a place to enforce this rule would introduce a second write path for the exact data `/save` already owns, immediately creating two ways to write the same field of `cloud_state.json` — the precise anti-pattern ADR-008 exists to prevent. Validating the *existing* full-state payload before it's persisted keeps `/save` as the one and only write path for `manualBets`, consistent with "every cloud write is a full replacement" (`02_Data_Flow.md` §10). Identity is computed by reusing `_resolve_liga_display_name()` and `_normalize_market_code()` — the exact same normalisation the settlement engine already applies — rather than a second, independent implementation of "what counts as the same league/market" (ADR-004/ADR-009).

**Consequences**

- `POST /save` gains a pre-write step: `_dedupe_manual_bets()` scans `content["manualBets"]`, and for any two entries whose `(data, liga, jogo, mercado)` identity matches (after the same normalisation settlement uses), keeps the first occurrence and drops the rest.
- The response gains an optional `duplicatesRemoved` field, present only when at least one duplicate was dropped. The frontend's `saveCloudState()` calls `_reloadManualBetsFromCloud()` when this is non-zero, so `state.manualBets` is resynced to the authoritative (deduplicated) cloud copy instead of silently diverging from what was actually persisted.
- A bet that fails to resolve an identity (missing date/league/game/market) is passed through untouched rather than risk dropping a legitimate record on incomplete data.
- This is defense-in-depth: the primary UX guarantee (a user cannot casually create a duplicate) comes from the frontend hiding the Scout card immediately (see `03_Dashboard.md`) and from `findManualBetByOpportunity()` guarding both creation paths synchronously. The backend check exists for whatever gets past both — races between tabs, stale local state re-submitting a bet the cloud already has, or a future bug in the frontend guard.

**Do Not Revert Without Good Reason**

Removing this check re-opens the exact failure mode it exists to close, and re-adding it later as a new endpoint instead of inside `/save` would split `manualBets` writes across two paths that must then be kept consistent forever — the cost ADR-008 already explains for a different data type but applies identically here.

---

## ADR-014 — Quantitative Formulas Are Canonical in Python; the JavaScript Mirror Is Verified by Golden-Vector Conformance Testing, Not Shared Source

**Status:** Accepted

**Date:** 2026-07-11 (Phase 26.29)

**Decision**

`src/calculations.py` is the single canonical implementation of every objective quantitative calculation the project uses: lambda projection (`compute_lambdas()`), the per-league lambda-boost multiplier (`apply_lambda_boost()`), model probability (`prob_over25()`, `prob_btts_yes_adjusted()`/`btts_prob_diagnostics()`), implied probability, edge, fair odds (`fair_odds()`), Kelly fraction (`kelly_fraction()`), confidence (`confidence_factor()`), and expected value (`expected_value()`). `index.html` contains a second, independent implementation of the same formulas — `QuantEngine`, an isolated JavaScript module with no DOM/state/network dependencies — consumed by the Manual Bet Scout. The two are **not** the same source file and cannot be, but they are held to identical numeric behaviour by a golden-vector conformance test suite (`tests/golden_vectors.json` + `tests/test_quant_engine_golden.py` + `tests/test_quant_engine_golden.js`) that must pass for both to be considered in sync. Score, Opinion, Recommendation Engine logic, Strategy Lab logic, and every other decision-layer concept are explicitly excluded from both implementations and remain with each consumer.

**Context**

Before this phase, `index.html` contained a hand-ported, independently-maintained copy of the Python model (`mbComputeLambdas()`, `mbProbOver25()`, `mbProbBttsAdjusted()`, `mbKellyFraction()`, four `mbClamp*()` functions, and a hardcoded `MB_HISTORY_CFG` mirroring `config.json`'s `history` block) — flagged in its own code comment as `// Ported from src/calculations.py — do NOT change formulas`, an acknowledgement that the duplication was known and manually policed rather than structurally prevented. A full inventory (this phase's investigation) found this port had already partially drifted: the JS `mbProbBttsAdjusted()` never exposed the diagnostic breakdown the Python `btts_prob_diagnostics()` computes, `confidence_factor` had no JS equivalent at all, and `fairOdd`/`EV` existed only in JS with no Python equivalent. `MB_HISTORY_CFG` required a human to notice and hand-update it every time `config.json`'s `history` block changed for the bot.

The request that produced this ADR asked for "a single shared Quantitative Engine used by both" the Python bot and the JavaScript Scout. A literal reading — one implementation, one runtime, called by both — is not achievable here without violating one of three other hard constraints, all independently justified:
- **ADR-005**: `index.html` has no build step, no framework, no npm, no transpiler.
- **Avoiding unnecessary Railway round-trips**: Scout's analysis is currently instant and works with only a data-fetch dependency (GitHub raw content), not a live server call; routing every analysis through a new Railway endpoint would add latency, lose offline capability, and couple Scout's availability to the single-worker gunicorn process (ADR-006).
- **No new runtime dependencies**: a WASM Python runtime (e.g. Pyodide) capable of running `src/calculations.py` literally in-browser is tens of megabytes and a large operational dependency for what is, in total, roughly 150 lines of arithmetic.

**Reasoning**

The actual harm "duplicated formulas" causes is not that two files exist — it is that they can **silently drift** with nothing to catch it, which is exactly what had already begun happening (see Context). Golden-vector conformance testing converts "one authoritative implementation" from a physical/textual property (impossible to guarantee across two runtimes without new heavyweight infrastructure) into a **verified behavioural property**: a fixed set of inputs computed once from the canonical Python engine, replayed against both implementations, with both test suites required to pass. This achieves everything the "no duplication" requirement is actually protecting against — silent divergence — without violating ADR-005, without adding latency, and without a new runtime dependency. It is the same pattern real-world multi-language SDKs use to keep equivalent logic in sync across runtimes that cannot literally share source.

Python was chosen as canonical because it is the version already running in production, generating real-money picks; JavaScript's role is to catch up to and stay verified against that source of truth, not the reverse.

**Consequences**

- Any change to a formula must be made in `src/calculations.py` first, then `tests/golden_vectors.json` regenerated from the updated Python function, then `QuantEngine` updated to match, then both conformance suites re-run — see `04_Backend.md` §15 for the exact process and commands.
- `QuantEngine` must remain a pure module: no `state` reference, no DOM access, no `fetch()` calls, no Score/Opinion/Recommendation logic. This is what makes it possible to extract and evaluate in an isolated Node context for testing (`tests/test_quant_engine_golden.js`) without a browser.
- `src/calculations.py` gained three new named functions this phase (`confidence_factor()`, `fair_odds()`, `expected_value()`) that did not previously exist as explicit, callable functions — `confidence_factor()` was inline in `src/market_rules.py::apply_stakes()` before extraction (behaviourally identical after extraction, verified by comparing `apply_stakes()` output before and after on identical input); `fair_odds()`/`expected_value()` are new additions that were previously JS-only concepts (`fairOdd`, `EV` in `analyzeFixture()`), now also canonically defined in Python even though the bot's own pipeline does not currently consume them.
- The Scout's `MB_HISTORY_CFG` hardcoded constant was replaced with a `loadModelConfig()` fetch of the real `config.json` (cached per session, falling back to a frozen copy of the prior defaults if the fetch fails) — closing the config-duplication gap without adding a Railway dependency, since `config.json` is fetched via the same GitHub raw-content mechanism already used for picks CSVs and `data_raw/*.csv`.
- Two independent, low-maintenance test suites now exist (`tests/test_quant_engine_golden.py`, `tests/test_quant_engine_golden.js`) with zero new dependencies beyond what each language's standard library / already-installed packages provide.
- **Post-implementation architecture audit follow-up (same phase):** a dedicated audit of the completed migration found one residual gap this ADR's own conformance guarantee had not yet closed — the per-league lambda-boost clamp-and-multiply step was inline, duplicated arithmetic in both `src/pick_generation.py` and `analyzeFixture()`, outside `src/calculations.py`/`QuantEngine` and outside the golden-vector suite. It was extracted into `apply_lambda_boost()` (Python) and mirrored as `QuantEngine.applyLambdaBoost()` (JavaScript), with golden-vector coverage added for both (8 vectors, verified identical to the pre-extraction inline formula). This closed the last quantitative-formula duplication inside the Bot + Scout architecture; the pre-existing, separately-scoped duplicate lambda logic in `fetch_oddsapi_fixtures.py` (Phase 1 fixture shortlisting — never part of this ADR's scope) remains untouched.

**Do Not Revert Without Good Reason**

Reverting to two unverified, independently-maintained implementations reopens the exact silent-drift failure mode this ADR exists to close — the partial drift found in this phase's investigation (missing BTTS diagnostics, missing confidence, a hand-maintained config mirror) is what happens by default without a conformance suite enforcing equivalence. Choosing a different sharing mechanism (Pyodide, a build step, a Railway round-trip) without a new fact changing the ADR-005/latency/dependency trade-offs analysed here would need to explain why those costs are now acceptable when they were rejected for the same reasons this phase rejected them.

---

## ADR-015 — A Bot Pick's Manual Result Override (`resultadoManual`) Is a Temporary Bridge; Automated Settlement Always Wins Once It Exists

**Status:** Accepted

**Date:** 2026-07-15 (Phase 26.34)

**Decision**

`getRowWithLocalEdits()` resolves a bot pick's displayed result as: use the CSV's `Resultado` (from `picks_history.csv`/`picks_hoje_simplificado.csv`) whenever it is a valid `W`/`L`/`P`; only when the CSV cell is empty/invalid does it fall back to `localEdits[pickKey].resultadoManual` (set via the History page's result dropdown or "Live Settle"). `getDailyRowsMerged()`'s cross-file reconciliation (borrowing a result from `picks_history.csv` when the same row's own daily-CSV cell is empty) follows the identical rule — automated settlement wins even over a manual override that had filled the gap. A stale `resultadoManual` is never automatically deleted or mutated; it simply stops being read once a real CSV result exists, remaining in `cloud_state.json["localEdits"]` as an inert historical record.

**Context**

A read-only investigation (prompted by a reported inconsistency on the "Huntsville City vs Crown Legacy" fixture) found the precedence had been reversed: `resultadoFinal = ['W','L','P'].includes(resultadoManual) ? resultadoManual : resultadoBase` let a manual override permanently mask the CSV, even after automated settlement later produced a real, possibly different, result. A systematic scan of all 12 historical `resultadoManual` uses against the current `picks_history.csv` found this was not merely theoretical: **two real bets** (Saint Etienne vs Nice, 2026-05-26; Nice vs Saint Etienne, 2026-05-29) had a manual override that disagreed with the automated result that arrived afterward, and the dashboard was silently showing the stale, wrong value — a real, live misstatement of bankroll/ROI (a €1.70 swing and a €1.00 swing respectively). A third case (Huntsville City vs Crown Legacy) had no automated result at all, which is the mechanism's legitimate, intended use.

**Reasoning**

`resultadoManual` exists to close out a bot pick the automated settlement pipeline cannot resolve (team-name mismatch, provider coverage gap, etc.) — a bridge until the real answer arrives, not a competing source of truth. Once `picks_history.csv` (the documented single owner of bot pick results — see `00_Project_Context.md`'s Source of Truth table and `04_Backend.md` §5) has a real result, that result reflects what actually happened in the match; a human's earlier best guess has no reason to keep overriding it. Making the CSV win whenever it's available restores exactly one owner for "what happened in this match," consistent with the project's "single source of truth" principle — the manual field only fills the gap while that owner has nothing to say yet.

Automatic deletion of `resultadoManual` once superseded was considered and rejected: `getRowWithLocalEdits()` is called on effectively every render, many times per interaction; mutating `state.localEdits` from inside it would make a pure "compute merged row" function silently stateful, risking unexpected `markDirty()`/cloud-save cascades triggered by rendering rather than user action. It also destroys the exact audit trail that made the two-conflict discovery above possible — being able to compare "what the user thought happened" against "what automated settlement determined" has diagnostic value even after the override stops driving the display. Simply ignoring the stale value achieves the same correctness outcome (CSV always wins) with none of that risk, matching the safer of the two options the investigation was asked to weigh.

**Consequences**

- `getRowWithLocalEdits()` and `getDailyRowsMerged()` are the only two places this precedence is implemented; every downstream consumer (History, Analytics, bankroll/ROI aggregation, `getRiskMetrics()`, Live/Pending classification) reads the already-resolved `_resultKey`/`_resultadoFinal` and needed no change.
- Strategy Lab, Opinion Validation, the Recommendation Engine, and the Simulator are unaffected — they consume settled **manual bets** (`state.manualBets`, keyed by their own `resultado` field), an entirely separate data model from bot picks' `localEdits.resultadoManual`; confirmed by tracing their data-source functions, all gated on `b.hadAnalysis === true`, which bot-pick rows never have.
- The two historical conflicting bets identified above now correctly display the automated result (L and W respectively) instead of the stale manual one; their `resultadoManual` values remain in `cloud_state.json["localEdits"]`, present but no longer read.
- A fixture whose automated settlement never resolves (the Huntsville case) continues to display its manual result exactly as before — no regression for the bridge's intended use.

**Do Not Revert Without Good Reason**

Reverting to "manual override always wins" reopens the exact silent-misstatement failure mode this ADR exists to close: a human's earlier guess would again be able to permanently outrank the real, automated settlement result for as long as the pick exists. Introducing automatic deletion of `resultadoManual` instead of simply ignoring it would need to first solve the side-effecting-pure-function risk this ADR identifies, and would destroy the audit trail this decision deliberately preserves.

---

## ADR-016 — Rendering Is Gated by Active Tab, Not by Data Change Alone; Every Tab Panel Remains Fully Mounted and Instantly Current on Activation

**Status:** Accepted

**Date:** 2026-07-15 (Phase 26.40)

**Decision**

`rerenderAll()` and `markDirty()` no longer unconditionally re-render all ~50 render functions across every tab on every state mutation. A single dependency map, `PAGE_RENDERERS` (tab id → array of that tab's own render functions, derived by tracing each function's actual DOM target), plus a small dispatcher (`renderActiveTabContent()`, `renderActiveTabIfStale()`) means a mutation now renders only the currently active tab's own panels. `renderActiveTabIfStale()` dedupes back-to-back render requests for the same tab against the Phase 26.39 `_dataGeneration` counter, so one logical user action (e.g. a single Approve click) never triggers two overlapping full render passes. `setActiveTab()` always forces a fresh render of the tab it switches to, regardless of dedup state — every tab panel stays fully mounted in the DOM (ADR-005 is unchanged) and is guaranteed fully current the instant it becomes active. This is explicitly **not** lazy-loading: no tab's DOM is ever "not yet built" in a way visible to the user; the only thing skipped is redundant re-computation of a page nobody is currently looking at. `renderVersus()` is a deliberate, explicitly-named exception — kept GLOBAL (called unconditionally on every `rerenderAll()`) because it populates `window._opnSimCache`, a cross-tab dependency consumed by Strategy Lab, the Recommendation Engine, Opinion Validation, and the Simulator regardless of which tab is active.

**Context**

Phase 26.38 (H1) and Phase 26.39 (H2) reduced `rerenderAll()` from 87.7s to ~1.1–1.2s on the real production account by fixing the underlying *data*-layer cost (an unmemoized `computeRecommendedStake()` chain called from count-only sites and per pending row). Phase 26.39's own "Next Priorities" note flagged that the remaining ~1–2.7s per click was now dominated by two purely rendering-architecture costs, explicitly out of that phase's scope: (a) two overlapping render passes per click (`markDirty()`'s internal render plus the caller's own `rerenderAll()`), and (b) ~50 render functions rebuilding their own `innerHTML` unconditionally regardless of which single tab was actually visible. This ADR is the "future, separately-scoped session" that note anticipated.

**Reasoning**

The DOM cost of `rerenderAll()` was never proportional to what the user could see — a click on Daily Picks was rebuilding History, Analytics, Strategy Lab, the Simulator, and every other tab's markup even though nine of ten tab panels were `display:none` at that moment. A dependency audit (tracing each render function's actual `document.getElementById`/`querySelector` target against the static HTML's tab-panel boundaries) found this grouping had never actually matched the legacy `rerenderXOnly()` wrapper names — `rerenderSummaryOnly()` also rendered `tab-analytics` and `tab-bankroll`; `rerenderManualOnly()` also rendered `tab-pending` and `tab-live` — so a correct fix required a fresh map, not a refactor of the existing wrappers. Gating by active tab (rather than, say, gating by whether a tab has ever been opened this session — a lazy-loading model) was chosen because the task's requirement was explicit and the codebase's own precedent (ADR-007: localStorage is a cache, never authoritative; this project consistently avoids models where "have I looked at this yet" affects correctness) argues against any model where a tab could show stale data purely because the user hadn't switched to it since the last mutation. Always forcing a fresh render on activation, regardless of dedup state, closes that gap by construction — dedup only ever skips a render that would have produced identical output (same tab, same `_dataGeneration`), never one that would have shown something new.

A single, coarse `PAGE_RENDERERS` dispatcher was chosen over scattering `if (state.activeTab === 'tab-x')` checks throughout each of the ~50 individual render functions, for the same reason Phase 26.39 chose one shared data cache over one cache per function: a dependency map that lives in one place is auditable and hard to miss-classify, where dozens of inline conditionals scattered across a 17,000-line file would each be a separate opportunity to gate the wrong function, or the right function on the wrong tab.

**Consequences**

- Approve/Cancel/edit actions on the real production account now cost ~150–350ms (page-measured) instead of Phase 26.39's ~1.1–2.7s — see Phase 26.40 in `08_Change_Log.md` for full before/H1/H2/H3 timing detail.
- Any new render function added in the future must be added to `PAGE_RENDERERS` under its correct tab (or deliberately added as a GLOBAL exception, following `renderVersus()`'s pattern and comment) — a render function that targets DOM inside a tab panel but is left out of `PAGE_RENDERERS` entirely will silently never run via the dispatcher.
- `markDirty()` gained a `skipRender` parameter (and `bindBotTableControls()`'s inner `update()` closure gained a matching `skipActiveTabRender` parameter) specifically for the Pending page's live `.js-odd-real`/`.js-stake-real` inputs — rendering the active tab on every keystroke would destroy and recreate the very input being typed into. Any future live-input field on a page that is also that page's active-tab render target needs the same treatment.
- `renderVersus()` remains an unconditional call inside `rerenderAll()`, not gated — any future change that removes or conditions that call must first re-verify Strategy Lab/Recommendation Engine/Opinion Validation/Simulator still receive a populated `window._opnSimCache` regardless of active tab.
- **Update (2026-07-15, Phase 26.41):** an independent audit found this migration had not reached the Manual Bets action surface or two Bankroll movement handlers, which still bypassed the dispatcher via the legacy `rerenderManualOnly()` wrapper (or a redundant direct render call) — the exact "duplicate render pass" / "invisible-DOM" failure mode this ADR exists to prevent, confirmed at ~27% of one action's cost. Phase 26.41 migrated all 7 remaining mutation paths to `markDirty()` alone and deleted `rerenderSummaryOnly()`, `rerenderPendingOnly()`, and `rerenderLiveOnly()` (by then confirmed to have zero live callers) — see Phase 26.41 in `08_Change_Log.md`. This is a completion of the rollout described above, not a change to the decision itself.

**Do Not Revert Without Good Reason**

Reverting to unconditional full-page rendering reopens the exact DOM-cost problem this ADR exists to close, without touching the data-layer gains from Phase 26.38/26.39 (which remain independent and unaffected either way). A future session wanting further rendering gains should extend `PAGE_RENDERERS`'s classification discipline (e.g. finer-grained gating within a single large tab) rather than reintroducing scattered inline `activeTab` checks or reverting to always-render-everything.
