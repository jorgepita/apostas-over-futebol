# Known Issues

Unresolved issues only. Move entries to `08_Change_Log.md` when fixed; a brief historical record is kept in the Resolved Issues section below.

Issue ID format: `LIVE-#`, `SETTLEMENT-#`, `SYNC-#`, `API-#`, `DASHBOARD-#`, `ANALYTICS-#`, `TELEGRAM-#`, `PERFORMANCE-#`

---

## Open Issues

None currently open.

---

## Resolved Issues

### DASHBOARD-2 — Settled Rejected Bets Remained Visible in History → Rejeitadas, Creating Duplicate Visibility With Analytics

**Status:** Resolved — 2026-07-11 (Phase 26.28). Full technical detail in `08_Change_Log.md` — Phase 26.28.

**Was:** A rejected manual bet stayed visible in the History page's "Rejeitadas" view forever, even after settlement gave it a real result. At the same time, the same bet correctly began appearing in Strategy Lab, Opinion Validation, and other analytical modules once settled (by design — see ADR-012). This created the appearance of the same analytical record being shown twice at once.

**Root cause:** `getRejectedManualBets()` (`index.html`) filtered only on `status === 'rejected'`, with no check on whether the bet had been settled. Since ADR-012 deliberately keeps a rejected bet's `status` at `'rejected'` forever — even after `resultado`/`lucro`/`placar` are populated by the shared settlement engine — this predicate returned every rejected bet regardless of settlement state. "Rejeitadas" is the only consumer of this function (2 call sites total: its own definition and `getRejectedHistoryRows()`); every analytical module (Strategy Lab, Opinion Validation, Recommendation Engine, Simulator, Bot vs Manual) sources its bet pool independently and never calls this function, so none of them were affected by the bug or by the fix.

**Fix:** `getRejectedManualBets()` now also requires `b._lucro === null` (not yet settled — the same convention `getResolvedManualBets()` already uses for the opposite check). A rejected bet disappears from "Rejeitadas" automatically once settled; it is never deleted and remains fully available everywhere else that reads `state.manualBets` directly. Confirmed via a repository-wide search that no dedicated "is settled" helper already existed to reuse — `_lucro === null` is the established inline convention used at 5+ other sites in the file, so no new abstraction was introduced.

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
