# Known Issues

Unresolved issues only. Move entries to `08_Change_Log.md` when fixed; a brief historical record is kept in the Resolved Issues section below.

Issue ID format: `LIVE-#`, `SETTLEMENT-#`, `SYNC-#`, `API-#`, `DASHBOARD-#`, `ANALYTICS-#`, `TELEGRAM-#`, `PERFORMANCE-#`

---

## Open Issues

None currently open.

---

## Resolved Issues

### SETTLEMENT-4 — `HISTORY_COLUMNS` Schema Drift Silently Erased `Placar` From Every Settled Row on Each Daily Generation Cycle (Already Active in Production)

**Status:** Resolved — 2026-07-21 (Phase 26.43's pre-commit safety audit, discovered while verifying the phase's own new `SettlementReason`/`MissingAttempts` columns). Full technical detail in `08_Change_Log.md` — Phase 26.43. See ADR-017's "Correction" section.

**Was:** Every settled row's `Placar` (final score, added Phase 26.19) was silently stripped from `picks_history.csv` on each daily generation run. Confirmed already active against real production data at the time this was discovered: 90 of 93 settled rows in the live file had an empty `Placar`, only the 3 most recent (not yet through a generation cycle) still had it.

**Root cause:** `src/history.py`'s `HISTORY_COLUMNS` — a separate, hardcoded 14-field schema list consumed by `load_history()`/`ensure_simple_columns()`/`merge_into_history()` (the daily-generation persistence path, `main.py` → `persist_history()` — distinct from `update_results.py`'s settlement engine and its own `CSV_COLUMNS`, which *did* get `Placar` added correctly in Phase 26.19) — was never updated to include it. `ensure_simple_columns()`'s reindex (`df[HISTORY_COLUMNS]`) is a hard "keep only these columns" operation, not a union — so `load_history()` dropped `Placar` from every row the moment it read `picks_history.csv`, and `merge_into_history()` wrote the stripped result back. Because `Resultado`/`Lucro€`/`LucroReal€` *are* in `HISTORY_COLUMNS`, a settled row still looked `already_done` to `update_dataframe()` on every subsequent settlement run — so the field, once stripped, was never re-populated. This was purely a display/analytics-field loss; no financial value (`Resultado`, `Lucro€`, `LucroReal€`) was ever affected.

**Discovered via:** Phase 26.43 (the postponed/cancelled/missing-fixture void policy, see ADR-017) added two new settlement-written fields, `SettlementReason` and `MissingAttempts`, to `update_results.py`'s `CSV_COLUMNS` — a pre-commit safety audit tracing their persistence lifecycle found they would be exposed to the identical erasure path, which led to finding `Placar` already silently affected in production.

**Fix:** `HISTORY_COLUMNS` extended to include `Placar`, `SettlementReason`, and `MissingAttempts`, restoring it as an exact mirror of `CSV_COLUMNS`. `src/pipeline.py`'s `save_all_outputs()` — a second, separate consumer that reindexes to `HISTORY_COLUMNS` directly without `ensure_simple_columns()`'s add-if-missing safety net — gained explicit blank-column assignments for the three fields (it would otherwise raise `KeyError` on every generation run once the schema grew). A new regression suite, `tests/test_history_schema.py`, asserts `HISTORY_COLUMNS` stays a set-equal mirror of `CSV_COLUMNS` going forward, specifically to catch the next drift immediately instead of after 11+ days of silent production loss.

**This fix is preventative only.** It does not and must not attempt to reconstruct the already-lost historical `Placar` values for the ~90 affected rows — that would require querying providers for old fixture data and was explicitly out of scope for this correction. Historical `Placar` reconstruction, if ever desired, must be a separate, explicitly-approved data-repair task.

---

### SETTLEMENT-3 — MLS Settlement Queried MLS Next Pro (API-Football ID Collision), Leaving Every Senior MLS Bet Unresolved

**Status:** Resolved — 2026-07-20 (Phase 26.42). Full technical detail in `08_Change_Log.md` — Phase 26.42. See ADR-004 update.

**Was:** Approved bot picks and manual bets on current senior MLS fixtures (e.g. Chicago Fire vs Vancouver Whitecaps, St. Louis City vs Sporting Kansas City, Nashville SC vs Atlanta United FC, Los Angeles Galaxy vs Los Angeles FC) never settled, even long after kickoff and `RESULT_READY_DELAY`. Meanwhile older `"MLS"`-labelled bets from earlier in the season had settled correctly, making the failure look intermittent rather than systemic.

**Root cause:** `src/league_registry.py`'s `"mls"` entry had `af_id=909` — API-Football's **MLS Next Pro** (reserve league) competition, not senior MLS (`253`) — hardcoded in Phase 26.12 to fix 13 bets that, at the time, genuinely were reserve-team fixtures. `config.json`'s `api_football.league_ids.mls` had held the correct `253` the entire time, undetected, because generation (`fetch_oddsapi_fixtures.py`) reads `config.json` directly and never imports the registry. The reason Phase 26.12's 13 stuck bets really were reserve-team fixtures: `fetch_fixtures_for_league_date()`'s zero-fixture retry (`search_league_id_by_api()`) fuzzy-matched the configured league's short name (`"MLS"`) against API-Football's `/leagues` listing — since `"major league soccer"` does not contain the substring `"mls"` but `"MLS Next Pro"` does, any date where senior MLS legitimately had no fixture silently substituted MLS Next Pro fixtures under the `"MLS"` label instead. Both defects together were self-consistent (generation and settlement agreed, on the wrong competition) for as long as senior MLS had sparse fixtures on the checked dates; once senior MLS resumed a normal calendar, generation started finding real senior-MLS fixtures directly (no substitution needed) while settlement kept querying MLS Next Pro — the two paths diverged and every senior MLS bet since became permanently unsettleable.

**Fix:** `"mls"` restored to `af_id=253` (`af_name="Major League Soccer"`). A new, distinct `"mls_next_pro"` registry entry (`af_id=909`) gives the reserve competition its own stable identity. Generating MLS Next Pro picks was always an intentional part of this project's coverage — the defect was never that they were generated, only that they were obtained via a fallback from MLS and stored under MLS's identity — so `mls_next_pro` was **also** registered in `config.json`'s `leagues` / `api_football.league_ids` sections (plus `main.py`'s non-EU top-up league set and a real `data_raw/mls_next_pro.csv` history file), making it a fully independent, actively-generating league exactly like MLS, never dependent on or substituting for it. `fetch_fixtures_for_league_date()` no longer retries a zero-fixture response with a different competition at all — a configured canonical ID is now authoritative everywhere, for both leagues.

**Historical data audit (Part 4 of the investigation, no destructive migration):** Every `"MLS"`-labelled row across `picks_history.csv` and `cloud_state.json["manualBets"]` was inspected. 14 bot-pick rows and 14 manual bets are genuine, already-**settled** MLS Next Pro fixtures (reserve/"II" teams, `Atlanta United II`, `Chattanooga`, `Real Monarchs`, etc.) — left untouched, per the investigation's explicit instruction not to migrate already-resolved historical data without a proven correctness reason. Exactly one row was both unresolved and deterministically identifiable as MLS Next Pro by team identity: `picks_history.csv`, `"Huntsville City vs Crown Legacy"` (2026-06-21) — both clubs are exclusively MLS Next Pro sides. Its `Liga` was changed from `"MLS"` to `"MLS Next Pro"` so it remains resolvable going forward; the matching `cloud_state.json["localEdits"]` key (`"2026-06-21|mls|..."` → `"2026-06-21|mls_next_pro|..."`) was re-keyed identically so its existing manual-result bridge (`resultadoManual: "P"`, ADR-015) is not orphaned. No `Resultado`/`Lucro€`/`resultado` field was touched on any row. 6 unresolved manual bets and 3 bot-pick rows already correctly carried senior-MLS identity (`leagueId: 253`, real club names) and needed no change — they simply now settle correctly under the corrected routing.

**Verification (read-only, live API-Football query under the corrected routing, 2026-07-20):** St. Louis City vs Sporting Kansas City — `FT`, `3-2` (Over 2.5 → W). Nashville SC vs Atlanta United FC — `FT`, `1-0` (Over 2.5 → L). Los Angeles Galaxy vs Los Angeles FC — `FT`, `0-3` (Over 2.5 → W). Chicago Fire vs Vancouver Whitecaps was not found in API-Football's schedule within a ±10-day window of its stored kickoff, consistent with a genuine postponement whose two clubs have since resumed against different opponents — the engine correctly does not match or settle it (no `FT`/`AET`/`PEN` status to observe), it simply remains open. See `08_Change_Log.md` Phase 26.42 for the full per-fixture trace.

---

### DASHBOARD-6 — Manual Bets' Persisted `kickoffUTC` Was Never Read by Pending/Live Center, Showing "Kickoff: —" Once a Fixture Aged Out of the Live Feed

**Status:** Resolved — 2026-07-20 (Phase 26.42). Full technical detail in `08_Change_Log.md` — Phase 26.42.

**Was:** Manual bets in the Live Center and Pending page showed `Kickoff: —` even though Phase 26.32 already persists `kickoffUTC` on fixture-backed manual bets at creation time. Bot picks, which read their own CSV `KickoffUTC` column directly, were unaffected.

**Root cause:** Two independent gaps. First, `getManualRowsMerged()` — the shared function both `getPendingRows()` and `getLiveRows()` build their manual rows from — never copied `kickoffUTC` from the raw `state.manualBets` entry onto its merged row object at all, so the field was unconditionally lost before any consumer could read it. Second, even had it been propagated, `getPendingRows()`/`getLiveRows()`/`getPendingCount()` derived a manual bet's kickoff exclusively via `findFixtureKickoff()` — a live lookup against the current rolling `fixtures_today.csv` window — rather than ever reading the bet's own persisted field; once a fixture's date passed and it aged out of that forward-looking window, the lookup naturally returned empty. Backend settlement was unaffected — `manual_bets_to_settlement_df()` already read `bet.get('kickoffUTC')` directly from the persisted field, so `RESULT_READY_DELAY` gating was always correct; this was a display/classification-only gap.

**Fix:** `getManualRowsMerged()` now includes `kickoffUTC` on every local manual row. A new `resolveManualKickoff(b)` helper (`b.kickoffUTC || findFixtureKickoff(...)`) is used at all four manual-row kickoff call sites (`getPendingRows()`, `getLiveRows()`, `getPendingCount()` — kept in sync with `getPendingRows()` per its Phase 26.38 invariant), preferring the persisted value and falling back to the live lookup only for bets that genuinely predate Phase 26.32 and have no persisted kickoff of their own. Bot-pick kickoff handling (`r['KickoffUTC']`) is untouched. The Manual Bets tab's own row table (a separate, out-of-scope render path) still calls `findFixtureKickoff()` directly and was not touched — it exhibits the same latent live-lookup weakness but was outside this fix's stated scope.

---

### DASHBOARD-5 — StakeReal Auto-Fill Guard Treated a Stored "0" as an Already-Entered Value, Permanently Suppressing the Default

**Status:** Resolved — 2026-07-15 (Phase 26.35). Full technical detail in `08_Change_Log.md` — Phase 26.35.

**Was:** The Phase 26.33 auto-fill guard (`.js-bot-approve` handler in `bindBotTableControls()`) used string truthiness — `if (!cleanString(stakeReal))` — to decide whether a pick already had a real stake. `"0"` is a non-empty string, so the guard treated a stored `stakeReal: "0"` identically to a deliberately-typed value and never replaced it with the recommended stake. A real, approved bot pick ("Mjallby AIF vs Vasteras SK FK") was found with exactly this state in `cloud_state.json` — `StakeReal` showed `€0.00` on the Pending page and did not contribute to Open Exposure, while a comparable pick approved the same way worked correctly.

**Root cause:** `computeRecommendedStake()` cannot itself produce zero — its output is hard-floored by `clamp(x, 1, maxCap)` with `maxCap ≥ 2` — so a stored `"0"` could only have entered `stakeReal` via the free-form `.js-stake-real` Pending-page input (no floor validation). `pendingCancel()` ("Cancelar") deliberately preserves `stakeReal` across a cancel, so a stray `"0"` could also survive an approve→cancel→re-approve cycle and keep suppressing the default indefinitely. `getRiskMetrics()`'s exposure sum does not filter out `0` (only `null`), so the pick was correctly counted as open but contributed nothing — exposure was faithfully summing a bad stored value, not miscalculating.

**Fix:** The guard now parses the existing value with the project's existing `num()` helper and auto-fills whenever it is `null` or `<= 0` — covering empty, undefined, NaN, invalid strings, zero, and negative values uniformly, while a genuine positive value (user-typed or from a prior auto-fill) is never touched. No change to `computeRecommendedStake()`, exposure calculation, or bankroll calculation. No data migration: a pick already sitting at a stale `stakeReal: "0"` self-corrects the next time it goes through Cancelar → Aprovar, not automatically.

---

### DASHBOARD-4 — Manual Result Override (`resultadoManual`) Could Permanently Mask a Later, Real Automated Settlement Result

**Status:** Resolved — 2026-07-15 (Phase 26.34). Full technical detail in `08_Change_Log.md` — Phase 26.34. See ADR-015.

**Was:** `getRowWithLocalEdits()` computed `resultadoFinal = ['W','L','P'].includes(resultadoManual) ? resultadoManual : resultadoBase` — a valid `resultadoManual` (set via the History page's result dropdown or "Live Settle") permanently took precedence over the CSV's own `Resultado`, even after automated settlement later wrote a real, possibly different, result into `picks_history.csv`. A read-only investigation prompted by a reported inconsistency on "Huntsville City vs Crown Legacy" (2026-06-21) found this had already caused two real, silent bankroll/ROI misstatements: "Saint Etienne vs Nice" (2026-05-26) displayed a stale manual `W` (+€0.70) when automated settlement had actually determined `L` (−€1.00); "Nice vs Saint Etienne" (2026-05-29) displayed a stale manual `P` (€0.00) when automated settlement had determined `W` (+€1.00).

**Root cause:** The manual-override mechanism was designed as a bridge for bot picks automated settlement can't resolve, but its precedence logic had no expiry or reconciliation against the CSV once a real result eventually arrived — a human's earlier best guess could out-rank the actual, confirmed outcome indefinitely.

**Fix:** `getRowWithLocalEdits()` now prefers a valid CSV `Resultado` whenever one exists, falling back to `resultadoManual` only while the CSV cell is still empty/invalid. `getDailyRowsMerged()`'s cross-file reconciliation (borrowing a result from `picks_history.csv` when a row's own daily-CSV cell is empty) was extended identically, so it also wins over a stale manual override, not only over a genuinely-unresolved row. `resultadoManual` is never deleted or mutated automatically — it simply stops being read once the CSV has a real result, preserving it as an inert historical record (see ADR-015 for the full reasoning, including why automatic cleanup was rejected). The two affected historical bets now display the correct automated result; the Huntsville fixture (whose automated settlement genuinely never resolved) is unaffected and continues to show its manual result exactly as before.

---

### SETTLEMENT-2 — Manual Bets Bypassed `RESULT_READY_DELAY`, Settling Before the Equivalent Bot Pick for the Same Fixture

**Status:** Resolved — 2026-07-12 (Phase 26.32). Full technical detail in `08_Change_Log.md` — Phase 26.32.

**Was:** For a fixture with both a bot pick and a manual bet on the same market, clicking "Executar Resolução" would settle the manual bet immediately while the bot pick stayed `LIVE`. Some time later, without any manual intervention, the bot pick settled correctly on a subsequent run. Both eventually settled correctly, but never during the same execution.

**Root cause:** This was not a settlement-engine bug — `update_dataframe()` is the single shared engine for both bot picks and manual bets (ADR-002/ADR-009), processed atomically in the same `/run-settlement` request with a shared provider-response cache. The asymmetry was in the *input data*: `update_dataframe()`'s `KICKOFF_TOO_EARLY` gate (`now < KickoffUTC + RESULT_READY_DELAY` — 2h15m) only runs `if kickoff_str:` — i.e. only when the row actually has a `KickoffUTC` value. Bot picks always have it (propagated end-to-end since Phase 26.7–26.9). Manual bets never did: `addManualBetFromFixture()` (`index.html`) never set a `kickoffUTC` field on the bet object, despite `docs/08_Change_Log.md`'s Phase 26.7–26.9 entry claiming this field was "propagated through... manual bet objects" — that claim was inaccurate; only a transient, render-time-only placeholder (`kickoffUTC: ''`, for display formatting) existed, never a persisted field read by settlement. So a manual bet became eligible for settlement as soon as its date matched, with no 2h15m safety margin — while the bot pick for the identical fixture correctly waited out the delay.

**Fix:** Manual bets created from an existing fixture (the Scout workspace) now persist `kickoffUTC`, `homeTeam`, `awayTeam`, and `leagueId` (the last derived from the already-fetched `config.json.api_football.league_ids`, no new network call) at creation time — immutable fixture metadata, never re-derived from `state.fixtures` later. `manual_bets_to_settlement_df()` already read `bet.get('kickoffUTC')`; it simply had never been given real data. **No change was made to the settlement engine, `RESULT_READY_DELAY`, matching logic, or persistence architecture** — this was purely a data-completeness fix at bet-creation time. Free-form manual bets (the text-entry form, not tied to any fixture) are unaffected and continue to have no kickoff metadata — this is a documented, accepted limitation, not a bug: there is no fixture to source it from. Pre-existing manual bets created before this phase also have no kickoff metadata and are unaffected; no persistence migration was performed or required.

---

### DASHBOARD-3 — DASHBOARD-2's Fix Targeted the Wrong Page; Duplicate Visibility Corrected in the Operational List Instead

**Status:** Resolved — 2026-07-11 (Phase 26.31). Full technical detail in `08_Change_Log.md` — Phase 26.31. **Supersedes DASHBOARD-2 below — see that entry's note.**

**Was:** DASHBOARD-2's fix made `getRejectedManualBets()` hide a rejected bet from "Rejeitadas" once it settled. This was the wrong page to fix: "Rejeitadas" is the intended permanent archive of rejected bets (settled or not), while the actual duplicate-visibility problem was that the *operational* "Apostas Manuais" list never stopped showing a rejected bet after it settled — that list's filter (`renderManualBets()`) only checked `status` (`!== 'approved' && !== 'settled'`), and a rejected bet's `status` stays `'rejected'` forever (ADR-012), so it never dropped out of the list a user works from day to day.

**Root cause:** Two separate filters govern rejected-bet visibility, and DASHBOARD-2 corrected the one that didn't need it while leaving the real bug in place: `renderManualBets()`'s row filter had no check on settlement state at all, so a settled rejected bet stayed in the operational list indefinitely, needing no further action but still cluttering the page the user actually triages from.

**Fix:** `getRejectedManualBets()` reverted to its pre-DASHBOARD-2 predicate (`status === 'rejected'`, settled or not) — "Rejeitadas" is now correctly the permanent archive. `renderManualBets()`'s filter gained one additional exclusion: a `status === 'rejected'` bet with `_lucro !== null` (settled) is now hidden from the operational list. Net effect: a rejected bet appears in both "Apostas Manuais" and "Rejeitadas" while unsettled; once settled, it drops out of "Apostas Manuais" only, remaining permanently in "Rejeitadas" and in every analytical module that reads `state.manualBets` directly (unaffected by either fix, since none of them call `getRejectedManualBets()`).

---

### DASHBOARD-2 — Settled Rejected Bets Remained Visible in History → Rejeitadas, Creating Duplicate Visibility With Analytics

**Status:** Resolved — 2026-07-11 (Phase 26.28). **Note (2026-07-11, Phase 26.31): this fix targeted the wrong page — see DASHBOARD-3 above for the correction.** Full technical detail in `08_Change_Log.md` — Phase 26.28 and Phase 26.31.

**Was:** A rejected manual bet stayed visible in the History page's "Rejeitadas" view forever, even after settlement gave it a real result. At the same time, the same bet correctly began appearing in Strategy Lab, Opinion Validation, and other analytical modules once settled (by design — see ADR-012). This created the appearance of the same analytical record being shown twice at once.

**Root cause (as understood at the time):** `getRejectedManualBets()` (`index.html`) filtered only on `status === 'rejected'`, with no check on whether the bet had been settled. Since ADR-012 deliberately keeps a rejected bet's `status` at `'rejected'` forever — even after `resultado`/`lucro`/`placar` are populated by the shared settlement engine — this predicate returned every rejected bet regardless of settlement state. "Rejeitadas" is the only consumer of this function (2 call sites total: its own definition and `getRejectedHistoryRows()`); every analytical module (Strategy Lab, Opinion Validation, Recommendation Engine, Simulator, Bot vs Manual) sources its bet pool independently and never calls this function, so none of them were affected by the bug or by the fix.

**Fix applied at the time (since reverted — see DASHBOARD-3):** `getRejectedManualBets()` was changed to also require `b._lucro === null` (not yet settled). This was later recognised as fixing the symptom on the wrong page — "Rejeitadas" is the intended permanent archive, and the operational "Apostas Manuais" list was the one that actually needed the settlement check. See DASHBOARD-3.

---

### MANUAL-1 — Scout Card Stayed Visible for Pending Manual Bets; Rejected Bets Lost Their Status When Settled

**Status:** Resolved — 2026-07-10 (Phase 26.19). Full technical detail in `08_Change_Log.md` — Phase 26.19.

**Was (two related defects found while implementing the Manual Bet lifecycle rework):**
1. `renderManualScout()`'s hide-key only excluded fixtures with a manual bet in `status ∈ {approved, rejected, settled}` — a brand-new `pending` bet was not in that set, so its Scout card remained visible and clickable until the user approved or rejected it. A user who clicked "Criar" twice (or came back to the Manual Bets tab before approving) could create a second, duplicate bet for the same fixture.
2. `apply_df_results_to_manual_bets()` unconditionally set `status = 'settled'` on any bet that received a result, including bets the user had already rejected. A rejected bet whose fixture finished silently lost its "rejected" status the moment settlement ran, and — because `getResolvedManualBets()` only checked `_lucro !== null`, not `status` — it then counted as a real result in bankroll, ROI, and every other financial calculation, even though the user had explicitly declined to place it.

**Root cause:** Both were the same class of bug — a lifecycle check (`status === 'approved'`/`'rejected'`) that was written for the states that existed at the time and never revisited when a new state (`pending` staying visible; `rejected` meeting the settlement engine) started reaching that code path.

**Fix:** `renderManualScout()`'s hide-key now covers every bet regardless of `status`. `apply_df_results_to_manual_bets()` only advances `status` to `'settled'` when it was not already `'rejected'`. `getResolvedManualBets()` additionally excludes `status === 'rejected'`. See ADR-012 for the underlying decision (lifecycle status and settlement result are independent) and `03_Dashboard.md` §7/§9 for the resulting behaviour.

---

### SETTLEMENT-1 — "No Matches to Settle" Caused by an Expired API-Football Subscription Masquerading as Empty Fixtures

**Status:** Resolved — 2026-07-07 (Phase 26.18). Full technical detail in `08_Change_Log.md` — Phase 26.18.

**Was:** The dashboard reported "No matches to settle." on every settlement run, even though bets in non-EU leagues (MLS, Allsvenskan, Veikkausliiga, K League 1) had clearly finished. `updated` was 0 and every eligible pick came back `NO_MATCH`.

**Root cause:** The API-Football subscription had lapsed to the Free plan, which rejects the 2025/2026 season. API-Football responded with HTTP 200, an empty `response: []`, and the real reason in `errors.plan`. `update_dataframe()` never inspected `errors` on a 200 response — an empty `response` was indistinguishable from "no games today". Renewing the subscription fixed settlement immediately with no code change, confirming the settlement/matching logic itself was never broken.

**Fix:** API provider responses (both API-Football and football-data.org) are now validated for embedded errors before being trusted, normalized into one error record shape, logged, surfaced in the `/run-settlement` summary (`settlement_aborted`/`provider_errors`) and the dashboard (`⚠ Settlement unavailable`, plus a persistent provider-health badge), and tracked across runs in `cloud_state.json["providerHealth"]`. See ADR-011.

Full technical detail, root cause analysis, and validation for the rest of these is in `08_Change_Log.md` — Phase 26.17.

### LIVE-1 — Live Center Does Not Auto-Refresh Manual Bet Results

**Status:** Resolved — 2026-07-01 (Phase 26.17)

**Was:** The Live Center showed manual bets as LIVE after they had already been settled on the backend. The user had to manually click "Load Cloud" or trigger "Run Settlement" to see the updated result. Root cause: the 60-second `loadData()` auto-refresh interval fetched picks CSVs only and never called `GET /load`, so `state.manualBets` went stale whenever settlement happened outside the current tab.

**Fix:** Replaced the assumption of periodic polling with an event-driven refresh model. `state.manualBets` (and `state.movements`) now refresh on four events: boot (via a new `_bootSyncComplete` guard deciding between `_doLoadCloudState()` and `_reloadManualBetsFromCloud()`), on-demand settlement completing, the "Load Cloud" button, and the browser tab regaining visibility. The 60-second interval continues to refresh only the read-only picks CSVs and league stats.

### SYNC-1 — Bankroll Movements Lost During Cloud Recovery

**Status:** Resolved — 2026-07-01 (Phase 26.17)

**Was:** A fresh browser session (e.g. Incognito) that recovered state from `cloud_state.json` showed the correct bankroll base, manual bets, and betting KPIs, but ignored all deposits/withdrawals — bankroll totals, "Global Result", and the Movement History table differed from a normal session with existing local data, even though both were reading the same cloud data.

**Root cause:** `_doLoadCloudState()` and `_reloadManualBetsFromCloud()` copied `bankrollInicial`, `manualBets`, `localEdits`, and `sessionStartDate` from the `/load` response, but neither ever assigned `content.movements` to `state.movements`. `state.movements` stayed at its initializer value (`[]`) on any session that went through cloud recovery.

**Fix:** Both functions now include `state.movements = Array.isArray(content.movements) ? content.movements : []`, matching how every other recovered field is handled. The existing post-recovery `saveLocalState()` calls persist the recovered movements to `localStorage` — no new save call was introduced.

### SYNC-2 — Railway `GITHUB_REPO` Misconfiguration

**Status:** Resolved — 2026-07-01 (Phase 26.17)

**Was:** `GET /load` on the Railway backend returned an empty `{}` body, so any fresh session had nothing to recover from the cloud at all, independent of the SYNC-1 code defect above.

**Root cause:** `sync_server.py` builds the GitHub Contents API URL from the `GITHUB_OWNER`/`GITHUB_REPO` environment variables. Railway's `GITHUB_REPO` variable was set to the fully-qualified `jorgepita/apostas-over-futebol` instead of just `apostas-over-futebol`, producing a doubled path (`.../repos/jorgepita/jorgepita/apostas-over-futebol/...`) that 404s against GitHub. `update_results.py` was unaffected — it hardcodes the same two values as module-level constants instead of reading them from the environment — which is why GitHub Actions settlement and `/run-settlement` kept working the whole time.

**Fix:** The Railway `GITHUB_REPO` environment variable was corrected to `apostas-over-futebol`. No code change was made or needed (per ADR-010, this class of value belongs in environment configuration, not code).

### DASHBOARD-1 — Pending KPI / Alert Count Diverged From the Pending Page

**Status:** Resolved — 2026-07-01 (Phase 26.17)

**Was:** The "Pendentes Abertas" dashboard KPI and the "Muitas apostas abertas" alert both showed a higher count than the Pending page for the same nominal dataset.

**Root cause:** The Pending page's `getPendingRows()` excludes bets whose kickoff has already passed (those belong to Live Center). The KPI and the alert instead read `getRiskMetrics().openCount`, which counts every approved-and-unsettled bet with no kickoff-time filter — i.e. Pending + Live combined.

**Fix:** The KPI and the alert now call `getPendingRows()` directly. `getRiskMetrics().openCount` was left unchanged and is still used by the exposure/risk widgets ("Risco Atual", stake-at-risk figures), which intentionally include live bets since they measure total capital currently at risk, not the "awaiting kickoff" count.
