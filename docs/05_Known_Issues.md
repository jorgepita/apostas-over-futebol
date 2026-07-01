# Known Issues

Unresolved issues only. Move entries to `08_Change_Log.md` when fixed; a brief historical record is kept in the Resolved Issues section below.

Issue ID format: `LIVE-#`, `SETTLEMENT-#`, `SYNC-#`, `API-#`, `DASHBOARD-#`, `ANALYTICS-#`, `TELEGRAM-#`, `PERFORMANCE-#`

---

## Open Issues

None currently open.

---

## Resolved Issues

Full technical detail, root cause analysis, and validation for each of these is in `08_Change_Log.md` — Phase 26.17.

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
