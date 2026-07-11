# Known Issues

Unresolved issues only. Move entries to `08_Change_Log.md` when fixed; a brief historical record is kept in the Resolved Issues section below.

Issue ID format: `LIVE-#`, `SETTLEMENT-#`, `SYNC-#`, `API-#`, `DASHBOARD-#`, `ANALYTICS-#`, `TELEGRAM-#`, `PERFORMANCE-#`

---

## Open Issues

None currently open.

---

## Resolved Issues

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
