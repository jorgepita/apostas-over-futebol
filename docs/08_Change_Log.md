# Change Log

Major architectural phases in reverse chronological order. Minor commits, CSV updates, and hotfixes are not listed — see `git log` for the full record.

---

## Summary

| Phase | Date | Summary |
|---|---|---|
| 26.28 | 2026-07-11 | Fixed `getRejectedManualBets()` so History → Rejeitadas only shows rejected bets that haven't been settled yet — previously it showed every rejected bet forever regardless of settlement, creating duplicate visibility with Strategy Lab/Opinion Validation/etc. once a rejected bet settled. Single-predicate fix (`&& b._lucro === null`, the existing project convention — confirmed no dedicated settlement helper exists to reuse instead of introducing one). No change to settlement, persistence, `cloud_state.json`, bankroll, ROI, or any analytical module; all verified via the existing 6-suite Playwright regression harness plus a new targeted 19-check script |
| 26.27 | 2026-07-11 | Removed the legacy NBA subsystem entirely: 8 NBA-exclusive files deleted (5 scripts, 1 config file, 2 data/output CSVs) and 3 dead NBA keys removed from `config.json` (`bankroll.nba_over`, `rules.nba_over`, top-level `nba` block). Preceded by a full read-only audit (previous session) that verified zero shared code between the NBA and football pipelines, and by an archival git tag (`legacy-nba-final`) at the pre-removal commit. Full validation (syntax, test suite, config-equivalence, import checks) confirmed zero football behaviour changed. Repository is now exclusively football |
| 26.26 | 2026-07-11 | Repository hygiene cleanup: removed obsolete `PROJECT_RULES.md` (superseded by `docs/`), replaced the content-free root `README.md` placeholder with a real landing page, committed `CLAUDE.md` and `.claude/settings.json` for the first time (closing a 3-session-old gap where docs already described them as committed), deleted stale diagnostic `audit_output*.txt` files, and added `.gitignore` rules for `.claude/settings.local.json` and `audit_output*.txt`. No code, business logic, or runtime behaviour changed |
| 26.25 | 2026-07-11 | Full dashboard localization to European Portuguese (PT-PT): translated every remaining English UI string in `index.html` — the Season Archive/Close Season wizard, the four Opinion analytics features (26.20–26.23), Strategy Lab (26.24), and assorted pre-existing analytics tables/labels/alerts — to natural PT-PT. No business logic, calculation, threshold, or persistence changed. Internal English status/severity codes used in `===` comparisons across the calibration and recommendation rule engines were kept as-is and only translated at render time via a new shared `ptLabel()` lookup, so no comparison was touched. All 6 existing Playwright regression suites (130+ checks) re-run and passing |
| 26.24 | 2026-07-10 | New "Strategy Lab" page (own tab/nav entry): a pure betting-strategy backtester over settled, Scout-analysed manual bets (including rejected ones). Strategy Builder (opinion/score/edge/odds/stake/league/market/season filters) feeds a Historical Replay (reusing computeStreaks()/computeDrawdownAnalysis()), a Compare-Against-Production panel (reusing window._opnSimCache's calibration/decision-cost/confidence functions), a Robustness Score explicitly designed so tiny samples can never outrank large ones, chronological-thirds Stability, Risk Analysis, a bounded (≤81-combination) Strategy Optimizer ranked by robustness, explainability, and a pure JSON export. Analytics-only, no persistence; every prior Opinion analytics/recommendations/simulator section confirmed unchanged and regression-tested (124 checks across 6 suites) |
| 26.23 | 2026-07-10 | New "Recommendation Simulator" card: a pure what-if layer below Opinion Engine Recommendations. Three sliders (STRONG BUY/BUY/AVOID threshold) replay settled opinion bets through a parameterized copy of the real classifier and the existing calibrationScore()/statsFromBets()/confidenceTier() functions — never writes to state, never persists, never touches production thresholds. Shows Current-vs-Simulated distribution/calibration/decision-cost/pair-score/confidence with explainability and a bounded (±5) "Best Nearby Configuration" search. Analytics-only; every prior Opinion analytics/recommendations section confirmed unchanged and regression-tested |
| 26.22 | 2026-07-10 | New "Opinion Engine Recommendations" card: a deterministic, multi-signal rule engine layered on top of Opinion Validation (no new statistics — reads calib/confidence/decisionCost/pairResults/historyPoints/trendSeries already computed there). Produces severity-ranked, evidence-backed recommendations (review-threshold, confidence nudges, hierarchy-healthy, calibration/opinion trend, insufficient-data) and one overall Opinion Engine Health label. Analytics-only; M/N/O and Opinion Validation unchanged and regression-tested |
| 26.21 | 2026-07-10 | Opinion Validation evolved: configurable calibration tolerance (suppresses statistically-insignificant inversions), an Opinion Pair Analysis table (Expected/Obtained/Difference/Status) sharing one pair-evaluation function with the calibration score, Decision Cost (what the AVOID classifier actually cost or saved), per-opinion cumulative-ROI sparklines, an explained Confidence indicator, and richer generalised insights — internal ranking now compares yield (profit/stake) instead of ROI directly (identical results today; future-proofing only). Analytics-only; M/N/O sections unchanged and regression-tested |
| 26.20 | 2026-07-10 | New "Opinion Validation" analytics section (Bot vs Manual tab): expected-vs-actual ranking, a weighted pairwise-concordance Calibration Score (0–100), pairwise ✔/✖ validation, a sample-size Confidence indicator, priority-ranked insights, a trend warning, and a reconstructed calibration-over-time chart — analytics-only, no changes to pick generation, scoring, settlement, or persistence |
| 26.19 | 2026-07-10 | Manual Bet lifecycle reworked: Scout card hides for any pending bet (not just approved/rejected), fixing a duplicate-creation gap; three-layer duplicate protection (Scout hide, frontend creation guard, backend `/save` dedupe); Reject no longer deletes — it's a permanent, settleable, analytical lifecycle state, fully decoupled from settlement result; new `Placar` (final score) field; History page gains a Resolvidas/Rejeitadas toggle |
| 26.18 | 2026-07-07 | "No matches to settle" root-caused to an expired API-Football subscription silently returning HTTP 200 + empty fixtures; provider responses now validated for embedded errors, normalized, logged, surfaced in the settlement summary and dashboard, and persisted as per-provider health in `cloud_state.json` |
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

## Phase 26.28 — Hide Settled Rejected Bets From History → Rejeitadas

**Implemented:** 2026-07-11

**Goal.** A rejected manual bet stayed visible in the History page's "Rejeitadas" view forever, even after settlement gave it a real result — at the same time, the same bet correctly began appearing in Strategy Lab, Opinion Validation, and other analytics once settled (by design, per ADR-012). This created the appearance of the same analytical record being visible in two places at once. The expected behaviour: a rejected bet has two phases — (1) rejected + unsettled → visible in Rejeitadas; (2) rejected + settled → automatically disappears from Rejeitadas, remains fully available everywhere analytical (Strategy Lab, Opinion Validation, Recommendation Engine, Simulator, Bot vs Manual). This is not a data-loss fix — the bet is never deleted, only a presentation filter changes.

**Investigation (full trace before any change).**
- **Storage:** `cloud_state.json` → `manualBets` array (ADR-001/ADR-008) — unaffected.
- **Settlement writes:** the backend's `apply_df_results_to_manual_bets()` populates `resultado`, `placar`, `lucro`/`Lucro€`, `settledAt` on the bet object; `status` is left at `'rejected'` if it was already `'rejected'` (ADR-012) — confirmed via source inspection, not assumed.
- **Every filter site traced:** `getResolvedManualBets()` (`b._lucro !== null && b.status !== 'rejected'`) — used by Manual Bets financials, History "Resolvidas", Bot vs Manual, Opinion Validation, Recommendation Engine, Simulator — already correctly excludes all rejected bets regardless of settlement, untouched by this phase. `getRejectedManualBets()` — the only broken one, and the only function History "Rejeitadas" consumes (via `getRejectedHistoryRows()`, its sole caller). `getStrategyLabPool()` — reads `state.manualBets` directly, filtered only by `hadAnalysis && botOpinion && resultado∈{W,L,P}` — deliberately includes rejected bets by design (a documented, pre-existing decision, unrelated to this bug), untouched.
- **Root cause confirmed:** `getRejectedManualBets()` filtered only on `status === 'rejected'`, with zero check on settlement state, so a settled rejected bet never dropped out of the one view meant to show "awaiting outcome" rejected bets.
- **Quality review (post-fix):** searched the codebase for an existing "is settled"/"is resolved"/"is open bet" helper before finalising the fix. None exists anywhere in `index.html` — the established convention is the raw inline check `_lucro === null`/`!== null` (already used 5+ times, including inside the sibling function `getResolvedManualBets()`) or `_resultKey === 'pending'` (used 6+ times). Per that convention, no new helper was introduced for this single call site.

**Fix.** One predicate change:
```js
function getRejectedManualBets() {
  return getManualRowsMerged().filter(b => b.status === 'rejected' && b._lucro === null);
}
```
Plus updated doc comments on `getRejectedManualBets()` and `getRejectedHistoryRows()` that had explicitly documented the old ("shows settled or not") behaviour as intentional.

### Files Modified

| File | Change |
|---|---|
| `index.html` | `getRejectedManualBets()` predicate narrowed to unsettled-only (`&& b._lucro === null`); two doc comments updated |
| `docs/03_Dashboard.md` | 4 passages updated (Manual Bets §, Step 5 lifecycle narrative, ASCII lifecycle diagram, §9 Resolvidas/Rejeitadas toggle) that previously documented the old behaviour as intentional |
| `docs/05_Known_Issues.md` | New resolved-issue entry, `DASHBOARD-2` |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-11-rejected-bets-fix.md` | New handover for this phase |

### Validation

- **Quality review search.** Grepped for `function is[A-Z]`, `function has[A-Z]`, `function.*settl`, `const isSettled/isResolved/isPending/isOpen` across `index.html` — no dedicated settlement-state helper exists anywhere; `_lucro === null`/`!== null` and `_resultKey === 'pending'` are the only established conventions, both used repeatedly already. Confirms the fix correctly follows existing convention rather than needing a new or reused abstraction.
- **Syntax.** `node --check` on both extracted `<script>` blocks — zero errors.
- **Targeted regression script (new, 19 checks, scratchpad-only, not committed):** seeded 4 manual bets (rejected+unsettled, rejected+settled, approved+settled, plain pending) and verified: `getRejectedManualBets()` returns exactly the unsettled rejected bet; `getResolvedManualBets()` unchanged (still excludes all rejected bets, settled or not); `getStrategyLabPool('all')` still includes the settled rejected bet; the Rejeitadas DOM table shows only the unsettled rejected bet; the Resolvidas DOM table shows neither rejected bet; zero duplicate visibility across History tables; the Pending→Rejected→(settled)→disappears-from-Rejeitadas-but-stays-in-state transition; the unrelated Remove transition still works. All 19 checks passed both before and after the "quality review" step (no code changed between the two runs, since no helper was reused).
- **Full existing 6-suite Playwright harness re-run:** `test_opinion_validation.js` (19/19), `test_calibration_v2.js` (11/11), `test_recommendations.js` (22/22), `test_simulator.js` (26/26), `test_strategylab.js` (32/32 — including the explicit "Strategy Lab pool INCLUDES the rejected BUY bet" and "Production baseline excludes the rejected bet" checks) all pass unchanged. The pre-existing `test.js` shows 5 **expected** post-fix "failures" that assert the old (buggy) behaviour (e.g. "Rejected bet appears in `getRejectedManualBets()` with its settlement result") — the direct, intended consequence of this fix, not a regression; that scratchpad test file is not committed to the repository and was not edited.
- **Console/page errors.** Zero real errors in any run; the only console output observed anywhere was the pre-existing `Failed to fetch` noise from the test harness's deliberate network-blocking (confirmed identical on the unmodified suite, i.e. baseline, not caused by this fix).

### Impact

History → Rejeitadas now shows exactly what its name implies: rejected bets still awaiting an outcome. Once settled, a rejected bet is no longer duplicated across "Rejeitadas" and the analytical modules that are supposed to include it — it appears exactly once, in the modules designed to use it (Strategy Lab, Opinion Validation, Recommendation Engine, Simulator, Bot vs Manual), and nowhere in the two History tables. No data was deleted or altered; this is a presentation-only fix.

---

## Phase 26.27 — Remove Legacy NBA Subsystem

**Implemented:** 2026-07-11

**Goal.** A prior session's read-only audit (documented in that session's conversation, not a separate file) established that the repository contained a fully self-contained, parallel NBA pick-generation pipeline that shared zero code with the football system — no `sport` abstraction exists anywhere in `src/`, and every NBA script had its own config, own state file, own Telegram sender, and own data file. The audit found the NBA automation had run near-hourly from 2026-03-01 to 2026-04-30 (driven by something outside this repository, since `.github/workflows/bot.yml` never contained NBA scheduling at any point in its history) and had been dormant for 10+ weeks. This phase executes the approved removal: delete every NBA-exclusive artifact and the three dead NBA keys sitting inertly inside the shared `config.json`, with zero change to football behaviour.

**Archival safeguard.** Before any deletion, an annotated git tag `legacy-nba-final` was created at the pre-removal commit (`77dc981e`) as a permanent, unmodified snapshot — the NBA subsystem remains fully recoverable from that tag if ever needed again.

**What was deleted.**
- `fetch_fixtures_nba.py`, `run_job_nba.py`'s orchestrated fixture fetcher (100 lines)
- `fetch_oddsapi_fixtures_nba.py` — an earlier, superseded duplicate fixture fetcher, dead since the day after `fetch_fixtures_nba.py` was created (131 lines)
- `gerar_picks_nba.py` — the NBA pick-generation model, its own Telegram sender, its own dedup state (518 lines)
- `run_job_nba.py` — the orchestrator that ran the two scripts above (15 lines)
- `prepare_nba_small.py` — an orphaned, one-off local data-prep script hardcoded to a path that only ever existed on the original developer's machine (34 lines)
- `config_nba.json` — NBA model parameters, read exclusively by `gerar_picks_nba.py` (29 lines)
- `picks_nba_over.csv` — stale NBA pick output, last updated 2026-04-30 (5 rows)
- `data_raw/nba.csv` — historical NBA box-score data, read exclusively by `gerar_picks_nba.py` (13,561 rows / 496 KB)

**What was edited.** `config.json`: removed `bankroll.nba_over`, the `rules.nba_over` sub-block, and the top-level `nba` block (window/sigma_total). These three keys were verified dead in the prior audit by tracing every `config.json` accessor in `src/runtime.py` and `src/market_rules.py` — none ever look up an `nba`-prefixed key. Confirmed again this session by direct comparison (see Validation).

**Scope discipline.** No football file was modified. `main.py`, `update_results.py`, `sync_server.py`, `run_main.py`, `run_topup.py`, and every `src/*.py` module are byte-for-byte identical to the `legacy-nba-final` tag (`git diff legacy-nba-final -- <file>` returns zero lines for each). Only `config.json` changed, and only by removing the three dead keys.

### Files Modified

| File | Change |
|---|---|
| `fetch_fixtures_nba.py`, `fetch_oddsapi_fixtures_nba.py`, `gerar_picks_nba.py`, `run_job_nba.py`, `prepare_nba_small.py`, `config_nba.json`, `picks_nba_over.csv`, `data_raw/nba.csv` | Deleted |
| `config.json` | Removed `bankroll.nba_over`, `rules.nba_over`, top-level `nba` block — nothing else changed |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-11-nba-removal.md` | New handover for this phase |
| `README.md`, `CLAUDE.md`, `docs/PROJECT_MAP.md` | Verified — no change required (see Documentation Updated in the handover for why) |

### Validation

- **Search.** Full repository search (content + filenames, tracked and untracked, excluding `.venv/`) for `NBA`, `nba`, `basketball`, `basketball_nba`, `picks_nba`, `fixtures_today_nba`, `sent_state_nba`, `config_nba`, `prepare_nba`, `run_job_nba`, `fetch_fixtures_nba`, `generate_nba`, `hoops` — zero genuine matches. The only hits were case-insensitive substring false positives inside unrelated `index.html` identifiers (`actionBadge`, `decisionBadge`, `btnBase`), confirmed by inspecting every match directly.
- **Syntax.** `python -m py_compile` on every tracked `.py` file — zero errors.
- **Test suite.** `pytest tests/` — 29/29 passed (`test_season_model.py`), unaffected by this change.
- **Imports.** `import main`, `run_main`, `run_topup`, `update_results`, `sync_server`, and every module in `src/` — all import cleanly with zero errors.
- **Configuration equivalence.** Loaded `config.json` from both the working tree (post-edit) and the `legacy-nba-final` tag (pre-edit) and called `src.runtime.build_runtime_settings()` / `build_bankroll_settings()` on both. Every football-consumed derived field (`bankroll25`, `rules25`, `bankroll_btts`, `rules_btts`, and the full runtime-settings dict) is identical before and after — the only difference is the raw echoed config no longer contains the now-removed `nba_over` sub-keys, which is the intended effect.
- **Settlement path.** `update_results.py` never reads `config.json` at all, and is byte-for-byte identical to the `legacy-nba-final` tag (`git diff` returns zero lines) — settlement is provably unaffected without needing to exercise it against live provider APIs.
- **Pick generation.** `main.py` is likewise byte-for-byte identical to the tag. Combined with the config-equivalence check above, pick generation's inputs and code are both unchanged. The live pipeline was deliberately not executed as a validation step — it would consume metered API-Football/football-data.org quota and could trigger real Telegram notifications for a change that provably touches none of its logic.
- **Dashboard.** `index.html` has zero diff against the `legacy-nba-final` tag. Both `<script>` blocks (main app, ~672 KB, and a small secondary block) pass `node --check` with no syntax errors.
- **Documentation links.** No document in `docs/`, `CLAUDE.md`, or `README.md` ever referenced any of the deleted files (confirmed in the prior audit and re-confirmed this session), so no link can be broken by their removal.
- **Incidental artifact cleanup.** Running the Python validation commands above regenerated several tracked `__pycache__/*.pyc` bytecode files as a side effect; these were restored (`git checkout --`) before committing so the commit contains only the intended NBA-removal changes.

### Impact

The repository is now exclusively a football betting system. No shared code existed between the two pipelines, so this removal carried none of the risk a genuine shared-infrastructure untangling would have — every deleted file's only callers were other NBA files, and the three removed config keys were provably unread by any football code path both before this session's audit and reconfirmed here.

---

## Phase 26.26 — Repository Hygiene Cleanup

**Implemented:** 2026-07-11

**Goal.** Resolve a set of unexplained working-tree changes and untracked files that had been carried across three consecutive sessions without action (first flagged in the 2026-07-10 handover, repeated in 2026-07-11): two uncommitted root-file deletions, an untracked `.claude/` directory, an untracked `CLAUDE.md`, and four untracked diagnostic `audit_output*.txt` files. Every item was investigated via `git log`/`git show`/file content before any change was made — no assumption was made about intent, and one genuinely ambiguous decision (whether to restore a root `README.md`) was confirmed with the user before acting.

**Findings.**
- `PROJECT_RULES.md` (single commit, 2026-05-21) predates the `docs/` system (first committed 2026-07-01) by over a month. Its content — no-framework rule, page list, UI direction — is superseded by `00_Project_Context.md`, ADR-005, and `03_Dashboard.md`; its page list (`Home/Picks/...`) no longer matches the current dashboard (`Daily Picks/Live Center/Pending/...`), confirming it was stale, not just redundant.
- Root `README.md` (single commit, 2026-05-01) had only ever contained the placeholder `"# force deploy"` — never real documentation. Confirmed with the user: replace with a real, concise landing-page README rather than restore the placeholder or leave the repository without one.
- `.claude/settings.json` and `.claude/settings.local.json` had never been committed. `settings.local.json` is machine-specific by Claude Code's own naming convention and must not be shared; `settings.json` is a low-risk, shared project permission safe to commit.
- `CLAUDE.md` had never been committed, despite `docs/PROJECT_MAP.md`, `08_Change_Log.md` ("Doc System" row), and `07_Current_Status.md` all describing it as an established, permanent part of the repository since 2026-06-29. This was the one confirmed documentation/repository inconsistency — the docs weren't wrong about what should exist, just ahead of what had actually been committed.
- The four `audit_output*.txt` files matched, byte-for-byte in content and structure, the "temporary, read-only audit harness" described in ADR-011 / Phase 26.18 (the API-Football subscription-lapse investigation). That issue has been resolved and fully documented since 2026-07-07; the files were leftover diagnostic instrumentation with no ongoing reference value.

**Actions taken (all approved by the user before execution).**
1. Committed the deletion of `PROJECT_RULES.md`.
2. Replaced the root `README.md` placeholder with a concise landing page: project description, architecture summary, repository structure, and pointers to `docs/README.md` and `CLAUDE.md`.
3. Committed `CLAUDE.md` and `.claude/settings.json` for the first time.
4. Deleted the four `audit_output*.txt` files.
5. Added `.claude/settings.local.json` and `audit_output*.txt` to `.gitignore` to prevent both patterns from recurring uncommitted/unexplained.

**No code, business logic, or runtime behaviour changed.** This phase touched only repository metadata, root-level documentation, and tooling configuration.

### Files Modified

| File | Change |
|---|---|
| `PROJECT_RULES.md` | Deleted (superseded by `docs/`) |
| `README.md` | Replaced placeholder content with a real landing page |
| `CLAUDE.md` | Committed for the first time (content unchanged — already matched the documented workflow) |
| `.claude/settings.json` | Committed for the first time |
| `.gitignore` | Added `.claude/settings.local.json` and `audit_output*.txt` |
| `audit_output.txt`, `audit_output_v3.txt`, `audit_output_v4.txt`, `audit_output_v5.txt` | Deleted (never committed; obsolete diagnostic output from the already-resolved Phase 26.18 investigation) |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase |
| `docs/handovers/handover-2026-07-11-repo-cleanup.md` | New handover for this phase |

### Validation

- `git log --all`, `git show`, and full-content review performed on every item before any recommendation was made — no action taken on assumption.
- Confirmed no remaining reference to `PROJECT_RULES.md` anywhere outside historical (point-in-time) handover records.
- Confirmed `.claude/settings.local.json` and `audit_output*.txt` are excluded by `git status --ignored` after the `.gitignore` update.
- Confirmed `git status` is clean except for the intentional staged changes described above.

### Impact

The repository working tree now matches what the documentation has described for up to three sessions. No further "unexplained leftover" carries forward into the next session.

---

## Phase 26.25 — Full Dashboard Localization to European Portuguese (PT-PT)

**Implemented:** 2026-07-11

**Goal.** `03_Dashboard.md` §1 and `DEVELOPMENT_GUIDELINES.md` have long stated the rule "keep all UI text in PT-PT, do not mix languages" — but the rule had drifted from reality. The Season Archive/Close Season wizard was entirely in English, and the four Opinion analytics features added in Phases 26.20–26.24 (Opinion Validation, Opinion Engine Recommendations, Recommendation Simulator, Strategy Lab) had shipped with English copy throughout, alongside assorted older English labels scattered across the Bot vs Manual and Analytics tabs (table headers, KPI card titles, insight sentences, alerts). This phase closes that gap: every visible string in `index.html` was translated to natural PT-PT, and nothing else changed.

**Scope discipline.** Pure text/localization pass. No calculation, threshold, condition, algorithm, data flow, persistence, API, or HTML structural change (beyond width/wrapping adjustments implied by longer Portuguese phrases in a handful of labels). No variable, function, or object-key was renamed.

**The one structural addition — `ptLabel()`.** Several rule engines (Opinion Validation's calibration/confidence tiers, Opinion Engine Recommendations' severity levels, the League Analytics tier/action badges, the Analytics tab's confidence/knowledge-score badges) store and compare English constants directly — e.g. `calibMeta.label === 'Broken'`, `SEV_ORDER[r.severity]`, `confidence.label === 'Very Low'` — and also render that same string as the visible badge text. Renaming those constants to Portuguese would have meant finding and updating every comparison across four features without being able to verify each one exhaustively, for no functional benefit. Instead, a single shared lookup, `ptLabel(label)` (backed by `PT_LABEL_MAP`, `index.html` near `escapeHtml()`), maps the English constant to its PT-PT display form only at the point of rendering — every `===` comparison, object key, and `SEV_ORDER`/`confMap`/`LEAGUE_ACTION_CODE_LABEL`-style lookup continues to compare the original English string, untouched. `ptLabel()` is called 47 times across the file; anything not in `PT_LABEL_MAP` passes through unchanged (safe no-op for whitelisted terms like `STRONG BUY`/`AVOID`).

**What was translated.** Sidebar navigation, page titles/subtitles, the Strategy Builder card, Settings page; the Season Archive viewer and 4-step Close Season wizard (`renderArchiveDetail()`, `csmRenderStep1()`–`csmGoStep4()`, `csmExecute()`, `validateArchive()`'s error reasons); the Opinion Validation, Opinion Engine Recommendations, Recommendation Simulator, and Strategy Lab sections in full (headers, table columns, insight/recommendation sentences, evidence labels, empty states); the pre-existing Bot vs Manual analytics (League Performance, Drawdown, Score Bands/Calibration/Insights, Edge Realization, Model Quality Score/Trust/Executive Summary, Action Engine) and Analytics tab (League/Market Validation, Knowledge Score, Findings/Lessons, Confidence Score/Alerts); assorted alert/confirm dialogs and empty-state messages throughout.

**Whitelisted, intentionally untranslated:** `ROI`, `Edge`, `Scout`, `Bot`, `Strategy Lab`, `JSON`, `CSV`, `API`, `GitHub`, `Railway`, `Cloudflare`, `R2`, `BTTS`, `Over 2.5`, `STRONG BUY`/`BUY`/`NEUTRAL`/`AVOID`, and a handful of universally-understood table-header abbreviations (`W-L-P`, `WR`, `P/L €`, `Kickoff`, `Man n`/`Bot n`).

### Files Modified

| File | Change |
|---|---|
| `index.html` | ~800 lines touched across the whole file — see above; new `PT_LABEL_MAP`/`ptLabel()` helper added near `escapeHtml()` |
| `docs/03_Dashboard.md`, `docs/DEVELOPMENT_GUIDELINES.md` | No change — both already stated the PT-PT rule correctly; this phase brought the implementation into compliance with an existing, previously-unenforced statement |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase; `07_Current_Status.md` also backfilled missing "Completed Areas" entries for Phases 26.20–26.24, which had never been added |
| `docs/handovers/handover-2026-07-11.md` | New handover for this phase |

### Validation

- `node --check` on the extracted `<script>` block after every batch of edits — zero syntax errors throughout.
- Full-page `innerText` extraction (Playwright) across all 11 tabs with seeded manual-bet data, iteratively grepped for English words/phrases outside the whitelist until clean — several rounds surfaced genuine misses (duplicate English labels sitting inside already-PT section cards, a whole missed `U`–`Y`/`ACTION ENGINE` static-header cluster, `League`/`Market Validation` headers, streak/equity/confidence-score labels) that were fixed and re-verified.
- All 6 existing Playwright regression suites re-run to completion and passing after every significant batch of changes, and once more at the end: `test.js` (Manual Bet lifecycle, 14 checks), `test_opinion_validation.js` (19 checks), `test_calibration_v2.js` (11 checks), `test_recommendations.js` (22 checks), `test_simulator.js` (26 checks), `test_strategylab.js` (34 checks) — 130+ checks total, zero failures, zero console/page errors. Test *assertions that checked literal English UI copy* were updated in the scratchpad copy of these suites to expect the new PT-PT strings (e.g. `'excellent'` → `'excelente'`); no test's underlying *logic/invariant* assertion changed.
- Playwright screenshots captured for all 11 tabs for a final visual spot-check.
- `git diff --stat` confirmed only `index.html` changed in the commit; `update_results.py`/`sync_server.py` untouched, so no Python validation was needed.

### Impact

The dashboard's UI language now actually matches what `03_Dashboard.md` and `DEVELOPMENT_GUIDELINES.md` already specified. Any future feature must be written in PT-PT from the start (per those documents) rather than shipped in English with translation deferred — this phase is the direct cost of that having happened silently across Phases 26.20–26.24 and earlier.

---

## Phase 26.19 — Manual Bet Lifecycle Rework: Duplicate Prevention, Rejected as a Permanent Analytical State

**Implemented:** 2026-07-10

**Goal.** Improve the Manual Bet lifecycle architecture, not just its UI: stop the Scout workspace from letting a user accidentally create a duplicate bet, make the backend independently refuse duplicates, stop treating "Reject" as deletion, and cleanly separate a bet's workflow state from its match outcome — all while reusing the existing shared settlement engine, the existing History page, and the existing `cloud_state.json` persistence model (no second CSV, no second JSON, no new endpoint, no duplicated settlement logic).

**Two pre-existing defects found and fixed as part of this work (see `05_Known_Issues.md` MANUAL-1):**
1. `renderManualScout()`'s hide-key excluded fixtures with a bet in `status ∈ {approved, rejected, settled}` — but not `pending`. A brand-new bet's Scout card stayed visible and clickable until approved/rejected, so a user could create a duplicate before ever approving the first one.
2. `apply_df_results_to_manual_bets()` unconditionally set `status = 'settled'` on any bet that got a result — including bets the user had already rejected — silently erasing the rejection and letting the bet count in bankroll/ROI (`getResolvedManualBets()` only checked `_lucro !== null`, never `status`).

**Scout duplicate prevention.** `renderManualScout()`'s `processedMatchKeys` set now includes every bet in `state.manualBets` regardless of `status` — a card hides the instant "Criar" succeeds and stays hidden through pending/approved/rejected/settled, reappearing only if the bet is removed ("Remover"). No polling or refresh is involved; it's derived from `state.manualBets` on every render, same as before.

**Frontend + backend duplicate protection (ADR-013).** `manualBetOpportunityKey()`/`findManualBetByOpportunity()` (reusing the existing `normalizeLeagueCode()`/`normalizeMarket()` normalisers) identify a bet by fixture + market. Both bet-creation paths (`addManualBetFromFixture()` for Scout, `addManualBet()` for the manual entry form) check this synchronously before pushing — since the check and the push happen in the same, non-yielding function call, a double-click cannot create two records; the second call always observes the first bet already in the array. The backend applies the identical rule independently: `sync_server.py`'s new `_dedupe_manual_bets()` (reusing `update_results._resolve_liga_display_name()` / `_normalize_market_code()` — no second normalisation implementation) runs inside `POST /save` before every write, keeping the earliest bet per `(data, liga, jogo, mercado)` identity. When it drops something, the response carries `duplicatesRemoved`, and `saveCloudState()` calls `_reloadManualBetsFromCloud()` to resync `state.manualBets` to the canonical copy.

**Rejected is now a permanent, terminal lifecycle state (ADR-012).** `mbHandleRowReject()` already only set `status: 'rejected'` (it never spliced the bet — the project's own documentation had drifted from the implementation here; corrected). What was missing was the backend guarantee: `apply_df_results_to_manual_bets()` now only advances `status` to `'settled'` when it was not already `'rejected'` — a rejected bet keeps `status: 'rejected'` forever, even after settlement populates its `resultado`/`lucro`/`placar`. `getResolvedManualBets()` (the single choke point for bankroll/ROI/analytics/versus/KPIs) additionally excludes `status === 'rejected'`, and `getFilteredRealClosedRows()`'s manual branch now builds on `getResolvedManualBets()` instead of a separately-duplicated `_lucro !== null` filter — one change point instead of two.

**Rejected bets settle through the exact same engine (no duplicated settlement logic).** `manual_bets_to_settlement_df()`/`update_dataframe()` never filtered by lifecycle status — every manual bet, rejected or not, was already being fed through settlement. The only code path that needed a change was the one line described above. A new `Placar` column (`"{home_goals}-{away_goals}"`, e.g. `"2-1"`) was added to `CSV_COLUMNS` and written at both settlement write sites (`try_update_row_via_api_football()` and the football-data.org branch in `update_dataframe()`), round-tripped through `manual_bets_to_settlement_df()`/`apply_df_results_to_manual_bets()` — additive and backward-compatible (`ensure_columns()` fills `""` for older rows without it). It is populated identically for bot picks, since the settlement engine is shared (no bot-pick-specific branch was added).

**Fixed during final verification:** `SYNC_RESULT_COLUMNS` (consumed by `sync_daily_from_history()`, the bot-pick catch-up path called from both `main()` and `run_settlement_remote()` — copies settlement results from `picks_history.csv` into `picks_hoje_simplificado.csv` when a pick settles in one file before the other) was not updated when `Placar` was added to `CSV_COLUMNS`. Without this, a bot pick's final score would settle correctly in `picks_history.csv` but never reach the corresponding row in the daily CSV via this catch-up path — and, because `update_dataframe()` skips rows whose `Resultado` is already `W`/`L`/`P` (`ALREADY_DONE`), it would never self-correct on a later run. `Placar` added to `SYNC_RESULT_COLUMNS`; verified with a dedicated round-trip test.

**Rejected History view (reuses the existing History page and table).** The "Fechadas reais filtradas" card gained a Resolvidas/Rejeitadas toggle (`_historyViewMode`, a transient, unpersisted view flag). Resolvidas is the unchanged existing table. Rejeitadas (`renderRejectedHistoryTable()` / `getRejectedHistoryRows()` / `getRejectedManualBets()`) reuses the same card, filter bar, and `<table>` element with a different `<thead>` and row-renderer: Data, Liga, Jogo, Mercado, Odd, Stake, Análise, Opinião, Placar Final, Resultado, Lucro Teórico, Notas.

**Analytics compatibility (no dashboard built, per the request's scope).** Every field needed for future rejected-bet metrics (rejected win rate, theoretical ROI, false-negative rate, by league/market/confidence/opinion) already exists on the bet object (`liga`, `mercado`, `botOpinion`, `scoreAtAnalysis`, `edgeAtAnalysis`, `resultado`, `lucro`, `placar`, permanent `status: 'rejected'`) — no schema change beyond `placar` was needed for this.

### Files Modified

| File | Change |
|---|---|
| `index.html` | Scout hide-key fix; `manualBetOpportunityKey()`/`findManualBetByOpportunity()`; duplicate guard in `addManualBetFromFixture()`/`addManualBet()`; `getResolvedManualBets()`/`getRejectedManualBets()`; `getFilteredRealClosedRows()` manual branch; History Resolvidas/Rejeitadas toggle + `renderRejectedHistoryTable()`/`getRejectedHistoryRows()`; `saveCloudState()` resync on `duplicatesRemoved` |
| `update_results.py` | `Placar` added to `CSV_COLUMNS`; written at both settlement write sites; round-tripped in `manual_bets_to_settlement_df()`; `apply_df_results_to_manual_bets()` preserves `status: 'rejected'` |
| `sync_server.py` | `_manual_bet_identity()`/`_dedupe_manual_bets()`; wired into `POST /save`; `duplicatesRemoved` added to the response |
| `docs/03_Dashboard.md`, `docs/02_Data_Flow.md`, `docs/04_Backend.md` | Manual Bet lifecycle, Scout, settlement, and History sections updated to describe the new behaviour |
| `docs/09_Architecture_Decisions.md` | ADR-012, ADR-013 added |
| `docs/05_Known_Issues.md` | MANUAL-1 added to Resolved Issues |
| `docs/07_Current_Status.md`, `docs/08_Change_Log.md` | Updated for this phase |

### Validation

- Automated Chromium (Playwright) walkthrough of the live `index.html` (network calls blocked; deterministic seeded state) covering: Scout card hidden with no bet → visible again after Remove; Scout card disappears immediately after Create and stays hidden across a re-render; double-click/repeated create does not duplicate; a rejected-and-settled bet keeps `status: 'rejected'` while `resultado`/`placar` are populated; `getResolvedManualBets()` excludes it; `getRejectedManualBets()` includes it with its result; the Rejeitadas table renders game/opinion/final-score/notes; the Resolvidas table does not show the rejected bet. All checks passed.
- Isolated Python checks (no real GitHub/network calls): `_dedupe_manual_bets()` keeps the earliest bet across alias forms (`"premier"` vs `"Premier League"`, `"Over 2.5"` vs `"O2.5"`) and correctly treats a different market or date as not-a-duplicate; `manual_bets_to_settlement_df()` → simulated settlement write → `apply_df_results_to_manual_bets()` round-trip confirmed a rejected bet keeps `status: 'rejected'` with `resultado`/`placar`/`lucro` populated, and confirmed an approved bet still transitions to `status: 'settled'` exactly as before (no regression).
- `python -m py_compile update_results.py sync_server.py` passes. `node --check` on the extracted `<script>` block of `index.html` passes.
- `pytest tests/` — 29 passed, no regressions.
- Backward compatibility: an old CSV row without the `Placar` column loads correctly via `ensure_columns()`, defaulting to `""`.

### Impact

A user can no longer accidentally create a duplicate manual bet from the Scout workspace, and even if a race or a future frontend bug produced one, the backend refuses to persist it. Rejected bets are preserved forever as analytical records — settled by the same engine as any real bet, but structurally incapable of affecting bankroll, ROI, or any financial figure — laying the groundwork for future "rejected opportunity" analytics without any further schema change.

---

## Phase 26.18 — Provider API Error Visibility ("No Matches to Settle" Root Cause + Fix)

**Implemented:** 2026-07-07

**Root cause (diagnosed, no code changed to fix it).** The API-Football subscription had lapsed to the Free plan. Every `/fixtures` request for the 2025/2026 season returned HTTP 200 with an empty `response: []` and an `errors.plan` field explaining the season wasn't covered on that plan. `update_dataframe()` had no code path that inspected `errors` on a successful response — an empty `response` was always treated as "no games today". Every currently-open pick in a league routed through API-Football (all non-EU leagues, and any EU league falling back to it) came back `NO_MATCH`, and the dashboard reported "No matches to settle." with no indication a provider was actually rejecting the request. Diagnosed via a temporary, read-only audit harness that replayed real production data through the real pipeline with zero writes; renewing the subscription fixed settlement immediately with **no code change**, proving the settlement and matching logic itself was correct — the gap was response validation.

**Provider response validation.** `api_football_get()` now checks the `errors` field of every HTTP 200 response (`_extract_meaningful_errors_field()`) and raises a new `ProviderError` exception when it's non-empty, instead of returning the response as if it were a trusted (if empty) result. Genuine HTTP failures (401/403/429/5xx, both providers) are classified by `classify_provider_error()`, which prefers the response body's message content (`"plan"`/`"season"` → `PLAN_LIMIT`, `"quota"`/`"rate limit"` → `QUOTA_EXCEEDED`, `"token"`/`"auth"` → `AUTHENTICATION`, ...) and falls back to the HTTP status code otherwise.

**Normalized error record and structured logging.** Every provider failure — new or pre-existing — is normalized via `build_provider_error()` into `{provider, endpoint, request, category, message, retryable, timestamp}`, always printed as a `[API-FOOTBALL]` / `[FOOTBALL-DATA.ORG]` block (endpoint/category/message), and appended to `shared_state["provider_errors"]`. Successes are tracked via `record_provider_success()` so a provider that wasn't contacted this run can be told apart from one that failed.

**Settlement summary.** `build_settlement_result()` adds `provider_errors` to the `/run-settlement` response whenever any occurred, and — only when `updated == 0` and a provider error occurred — adds `settlement_aborted`/`abort_provider`/`abort_category`/`abort_reason`, picked via `pick_primary_provider_error()` (prefers a non-retryable error over a retryable one). When neither field is present and `updated == 0`, that is a genuine empty result, and "No matches to settle." is the correct message — this is now the *only* situation where that message appears.

**Provider health persistence.** `update_provider_health()` writes a new `cloud_state.json["providerHealth"]` field — `{provider: {status, consecutiveFailures, lastError, lastSuccessAt, lastCheckedAt}}` — so the failure state survives across Railway's stateless requests. Status flips `"ok"` → `"warning"` after `PROVIDER_HEALTH_WARNING_THRESHOLD` (2) consecutive failing runs for that provider, and resets on the next success. `cloud_state.json` is now saved whenever a settlement run contacts any provider, even if zero bets settled — previously it was only saved when a manual bet newly settled.

**Dashboard.** `runSettlement()` now distinguishes three outcomes: `✓ Settlement completed` (updated > 0), `⚠ Settlement unavailable — {provider}: {category text}` (provider error, nothing settled), and `No matches to settle.` (genuine empty result — unchanged from before). A new `#providerHealthLabel` badge next to the Cloud Status badge (Settings page) reads `state.providerHealth` — copied from `cloud_state.json` in `_doLoadCloudState()` and `_reloadManualBetsFromCloud()`, following the same cloud-field-copy pattern established for `state.movements` after the Phase 26.17 SYNC-1 fix — and shows `⚠ {provider}: {category text}` whenever any provider's status is `"warning"`.

**Backward compatibility.** All pre-existing failure reasons (`"HTTP {code}"`, `"OTHER"`, `"NO_LEAGUE_ID"`, `"NO_API_KEY"`) keep their exact strings and control flow; `update_dataframe()`'s precheck/matching/decision logic was not touched. The only behavioural change is the specific "HTTP 200 + meaningful `errors`" case, which previously returned `([], "")` (trusted empty result) and now returns `(None, "PROVIDER_ERROR")` (untrusted failed fetch) — the same code path every other provider failure already used. Validated against 7 required scenarios (valid fixtures; HTTP 200 + plan error; HTTP 200 + quota error; HTTP 401; HTTP 429; HTTP 500; genuinely empty HTTP 200) and against real production data (post-renewal, zero provider errors, settlement behaves exactly as before).

### Impact

A future provider outage — expired subscription, exhausted quota, revoked key, or a genuine API incident — will show up immediately as `⚠ Settlement unavailable` with a specific category, in the settlement summary, in structured logs, and in a persistent dashboard health badge, instead of silently accumulating unsettled picks behind an ambiguous "No matches to settle." message.

### Root Cause

- API-Football's Free plan rejects requests for the 2025/2026 season by returning HTTP 200 with an empty `response` and the real reason inside `errors.plan` — a response shape `update_dataframe()` had no code to distinguish from a genuine empty result.

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
