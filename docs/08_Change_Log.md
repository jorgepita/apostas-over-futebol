# Change Log

Major architectural phases in reverse chronological order. Minor commits, CSV updates, and hotfixes are not listed — see `git log` for the full record.

---

## Summary

| Phase | Date | Summary |
|---|---|---|
| 26.17 | 2026-07-01 | Manual bet/bankroll cloud synchronization fixed; boot sync guard and event-driven refresh replace periodic polling; Railway `GITHUB_REPO` misconfiguration resolved; dashboard KPI/alert consistency fixes; diagnostic instrumentation removed |
| Doc System | 2026-06-29 | Complete documentation system established; `CLAUDE.md` added at repository root |
| 26.16 | 2026-06-28 | Manual settlement unified into `cloud_state.json`; legacy CSV endpoints removed |
| 26.15 | 2026-06 | Automatic cloud-state recovery on fresh browser startup |
| 26.14 | 2026-06 | Canonical league key used in pick deduplication |
| 26.12 | 2026-06 | Calendar-year season model fix for MLS and Nordic leagues |
| 26.11 | 2026-06 | Railway backend introduced; on-demand settlement added |
| 26.7–26.9 | 2026-05 | KickoffUTC propagated end-to-end; live/pending transitions made kickoff-aware |
| 26.6 | 2026-05 | Pending queue redesigned as an execution workspace |
| 20–21 | 2026-04 | Live Center V1; live settlement engine with audit trail |
| 19 | 2026-03 | Pending queue introduced; create → approve → live workflow |
| 17 | 2026-03 | Scout workspace with real-time Poisson analysis; manual bets in financials |
| 14–16 | 2026-02 | History redesigned as an investigation tool; equity curve and drawdown added |
| 8–13 | 2026-01 | Analytics intelligence engine built incrementally |

---

## Phase 26.17 — Manual Bet & Bankroll Cloud Synchronization Fixed

**Implemented:** 2026-07-01

A multi-session investigation into a Live Center staleness report (LIVE-1) uncovered and fixed a chain of related synchronization defects across the frontend, backend, and Railway deployment configuration.

**Root cause of the manual bet synchronization issue (LIVE-1).** `state.manualBets` was populated from `localStorage` at startup. The 60-second `loadData()` auto-refresh interval only re-fetched the read-only picks CSVs from GitHub raw URLs — it never called `GET /load` and never refreshed `state.manualBets`. If settlement ran in another browser session, via GitHub Actions, or via a different device, the current tab kept showing stale manual-bet state (e.g. a settled bet still appearing in Live Center) until the user manually clicked "Load Cloud" or triggered settlement from that same tab.

**Boot synchronization redesign and guard.** `boot()` was restructured around a `_bootSyncComplete` flag. On startup, if no meaningful local session exists, `_doLoadCloudState()` recovers the full state from the cloud and sets the guard; otherwise `_reloadManualBetsFromCloud()` runs once to bring `state.manualBets` (and now `state.movements`) up to date without disturbing the rest of local state. The guard prevents a redundant second cloud fetch on the same boot and blocks `saveCloudState()` from firing before the first successful sync completes, avoiding a race where an unsynced local state could overwrite the cloud copy.

**Event-driven cloud synchronization.** The periodic 60-second interval now refreshes only the read-only picks CSVs, league stats, and pending-alert checks — it never touches manual bets. Manual bets (and movements) are instead refreshed on four explicit events: page boot, the "Run Settlement" button completing (`runSettlement()` → `_reloadManualBetsFromCloud()`), the "Load Cloud" button (`loadCloudState()` → `_doLoadCloudState()`), and the browser tab regaining visibility (`visibilitychange` → `_reloadManualBetsFromCloud()`). This covers settlement happening while the tab is backgrounded without adding a second polling interval.

**Bankroll movements lost during cloud recovery.** A follow-up audit found that `_doLoadCloudState()` and `_reloadManualBetsFromCloud()` copied `bankrollInicial`, `manualBets`, `localEdits`, and `sessionStartDate` from the `/load` response but never `content.movements`. `state.movements` therefore stayed at its initial empty array on any fresh session (e.g. Incognito), so the bankroll silently ignored all deposits/withdrawals after a cloud recovery while every betting-related figure (bets, wins, losses, ROI) stayed correct. Both functions now assign `state.movements = Array.isArray(content.movements) ? content.movements : []`, mirroring the other recovered fields. No new save call was introduced — the existing post-recovery `saveLocalState()` calls now persist movements to `localStorage` along with everything else.

**Railway `GITHUB_REPO` misconfiguration discovered and resolved.** While verifying the fixes against production, `GET /load` was found returning an empty `{}` body. Root cause: `sync_server.py` builds the GitHub Contents API URL from `GITHUB_OWNER`/`GITHUB_REPO` environment variables (`f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"`), and Railway's `GITHUB_REPO` variable was set to the fully-qualified `jorgepita/apostas-over-futebol` instead of just `apostas-over-futebol`, producing a doubled, 404-ing path. `update_results.py` was unaffected because it hardcodes the same two values as constants rather than reading them from the environment, which is why GitHub Actions settlement and `/run-settlement` kept working throughout. The Railway environment variable was corrected; no code change was needed or made (ADR-010 — configuration belongs in environment variables, not code).

**Dashboard KPI/alert consistency fixes.** The "Pendentes Abertas" KPI and the "Muitas apostas abertas" alert both independently re-derived an open-bet count instead of calling the same `getPendingRows()` helper the Pending page uses, causing them to include live (already-kicked-off) bets that the Pending page correctly excludes. Both now call `getPendingRows()` directly. Exposure-related widgets (`stakeOpen`, `potencialLucro`, "Risco Atual") were deliberately left on `getRiskMetrics().openCount`, since those intentionally measure total capital at risk including live bets — a different metric, not a duplicate.

**Diagnostic instrumentation removed.** All temporary investigation instrumentation — `debugger` statements, `[F1]`–`[F6]`, `[BOOT-DIAG]`, `[RECOVERY]`, `[RECOVERY-SCHEMA]` console logging in `index.html`, and `[STEP 1]`–`[STEP 5]` print statements in `update_results.py` — was removed once every fix was validated. Normal production logging (`[settlement] ...`, `console.error` in catch blocks, etc.) was left unchanged.

### Impact

`cloud_state.json` is now reliably the authoritative source for manual bets and bankroll movements alike — a fresh browser session reconstructs the same runtime state as a session with existing local data. Synchronization is fully event-driven with no periodic polling of manual-bet/bankroll state. The Pending KPI, Pending page, and volume alert can no longer numerically diverge, since they share one filtering function.

### Root Causes Fixed

- LIVE-1: 60-second interval never refreshed `state.manualBets` from the cloud.
- Bankroll movements (`state.movements`) were never copied out of the `/load` response during cloud recovery, in two separate functions.
- Railway `GITHUB_REPO` environment variable held a fully-qualified `owner/repo` value instead of just the repo name.
- Pending KPI and volume alert each re-implemented open-bet counting instead of reusing `getPendingRows()`.

---

## Documentation System Established

**Implemented:** 2026-06-29

A complete documentation system was created under `/docs` and a Claude workflow entry point added at the repository root. The system is designed so that any future Claude session can begin productive work by reading the documentation alone, without relying on previous chat history.

**Documents created:**

- `docs/README.md` — Documentation index, reading order, session lifecycle, update rules, documentation philosophy
- `docs/PROJECT_MAP.md` — Repository navigation guide: where every file and directory lives, development entry points, files that should rarely be modified
- `docs/SESSION_HANDOVER_TEMPLATE.md` — Reusable template for end-of-session handovers; copied and filled at the end of each session
- `docs/handovers/` — Directory for filled session handover documents
- `CLAUDE.md` (repository root) — Startup workflow and working principles for Claude sessions

**Documents rewritten or significantly extended:**

- `docs/DEVELOPMENT_GUIDELINES.md` — Rewritten as a practical engineering handbook: general principles, debugging workflow, frontend/backend/CSS/JS guidelines, validation requirements, implementation philosophy, "Working with Claude" section
- `docs/09_Architecture_Decisions.md` — 10 ADRs covering all major architectural decisions
- `docs/05_Known_Issues.md` — Restructured as a permanent issue tracker with severity, root cause, fix strategy, and validation checklist
- `docs/06_Roadmap.md` — Complete long-term roadmap with short/medium/long-term items and summary table
- `docs/07_Current_Status.md` — Refactored as a stable-structure status snapshot
- `docs/08_Change_Log.md` — Summary table added; implementation dates and Impact sections added to all phases

### Impact

Future Claude sessions have a complete documentation system to work from. The session handover workflow ensures that context survives across conversation boundaries without depending on chat history. The development guidelines provide enforceable engineering standards.

---

## Phase 26.16 — Manual Settlement Unified into `cloud_state.json`

**Implemented:** 2026-06-28

Manual bet settlement migrated from `manual_bets.csv` to `cloud_state.json`. `update_results.py` now loads `cloud_state.json`, converts `manualBets` to a DataFrame, settles using the same `update_dataframe()` engine as bot picks, and writes results back. `sync_server.py` was rewritten to remove dead CSV-based endpoints and retain only `/load`, `/save`, `/run-settlement`, and `/health`.

### Impact

`cloud_state.json` became the exclusive persistence layer for manual bets. Bot and manual settlement now share a single engine (`update_dataframe()`), eliminating divergence risk. The Railway API surface is minimal and well-defined.

### Breaking Changes

- `manual_bets.csv` retired as an active data store. The file remains in the repository with a header row only. No active code path reads bet data from it.
- `/state` GET and POST endpoints removed from `sync_server.py`.

---

## Phase 26.15 — Automatic Cloud-State Recovery on Boot

**Implemented:** 2026-06

`boot()` now calls `_doLoadCloudState()` automatically on startup if `hasMeaningfulLocalState()` returns false. A fresh browser session with no localStorage recovers the full state from `cloud_state.json` without a manual "Load Cloud" click.

### Impact

New browser sessions and incognito windows are now self-recovering. The cloud is always consulted before presenting an empty dashboard to the user.

---

## Phase 26.14 — Canonical League Key in Pick Deduplication

**Implemented:** 2026-06

`makePickKey()` now uses the canonical league key from the registry rather than the raw display name. Existing `localEdits` entries were migrated to match.

### Impact

Pick deduplication is stable across league name variants. `localEdits` are no longer lost when the same league is referenced by different display strings (e.g. `"LaLiga"` vs `"La Liga"`).

---

## Phase 26.12 — Calendar-Year League Season Model Fix

**Implemented:** 2026-06

`api_football_season_from_date()` now consults `AF_SEASON_MODELS` from the league registry to determine the correct season integer per league. MLS and Nordic leagues were incorrectly mapped to season 2025 for June 2026 fixtures.

### Impact

Season resolution is now driven by `src/league_registry.py`. Adding a new league with a non-European season model requires only a `season_model` field in the registry entry.

---

## Phase 26.11 — Railway Backend Migration

**Implemented:** 2026-06

Dashboard migrated from GitHub Actions-based settlement to an always-on Railway server. `sync_server.py` introduced as the Flask application. "Run Settlement" button added to the Live Center. Settlement league mapping unified into the league registry.

### Impact

Settlement became on-demand and browser-triggered, no longer requiring a GitHub Actions run or direct API call. Railway became the single CORS bridge between browser and GitHub. The league registry became the authoritative source for all settlement routing.

### Breaking Changes

- Settlement previously required a GitHub Actions dispatch or manual script execution. On-demand settlement via the dashboard replaced this for the common case.

---

## Phase 26.7–26.9 — KickoffUTC End-to-End

**Implemented:** 2026-05

`KickoffUTC` field propagated through fixtures, picks CSVs, Scout bet creation, manual bet objects, and Live/Pending display. Pending and Live filter logic made kickoff-aware. Odd Real / Stake Real field persistence on page refresh fixed.

### Impact

Pending and Live Centre state transitions are now determined by actual kickoff time, not just bet date. Bets with future dates stay in Pending until kickoff passes; bets cross into Live only when they are genuinely in play.

---

## Phase 26.6 — Pending Queue Overhaul

**Implemented:** 2026-05

Pending section redesigned as an execution workspace with approve and reject actions. Approve button event binding fixed. Daily Picks page cleaned up to show only unplaced picks.

### Impact

The approve/reject action path became reliable. The distinction between "created", "approved/pending kickoff", and "approved/live" became consistent with the data model.

---

## Phase 20–21 — Live Center and Live Settlement Engine

**Implemented:** 2026-04

Live Center V1 introduced with merged bot and manual bet display. Pending/Live state separation formalised. Live settlement engine added with audit trail. Settlement hardening against partial results and malformed rows.

### Impact

The dashboard gained a unified view of all in-play bets. The settlement engine became robust enough for production use on real money.

---

## Phase 19 — Pending Queue

**Implemented:** 2026-03

Pending queue introduced as the first end-to-end manual bet workflow: create → approve → live. Manual bets tracked from creation through to a live state.

### Impact

Manual bets became a first-class feature with a defined lifecycle. The three-state model (pending, approved, settled) was established here and has remained unchanged.

---

## Phase 17 — Manual Bets Scout Workspace

**Implemented:** 2026-03

Scout workspace added to the Manual Bets tab with real-time Poisson analysis run in the browser. Manual bet workflow formalised: analyse → approve → reject. Manual bets integrated into financial calculations (bankroll, ROI, Bot vs Manual comparison).

### Impact

Manual bets became analytically consistent with bot picks. The Scout workspace established the pattern of running the Poisson model client-side using `state.fixtures`.

---

## Phase 14–16 — History Intelligence and Equity Curve

**Implemented:** 2026-02

History section redesigned from a simple table into an investigation tool. Equity curve, drawdown analysis, and financial intelligence panels added. Filtering by date range, league, and result added.

### Impact

The History tab became the primary performance review surface. Equity curve data is consumed by the Bankroll page for evolution charts.

---

## Phase 8–13 — Analytics Intelligence Engine

**Implemented:** 2026-01

Analytics section built incrementally across six phases: edge validation, strategy validation, model calibration display, action engine, learning centre, bot vs manual performance intelligence, score-band intelligence, and opinion intelligence.

### Impact

The dashboard shifted from a pick-viewing tool to a model-evaluation tool. Per-league ROI tracking, win-rate calibration, and the Bot vs Manual comparison tab were all established in this phase and have not required structural changes since.
