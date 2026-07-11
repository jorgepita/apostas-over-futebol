# Session Handover

---

## Session Information

```
Date:     2026-07-12
Branch:   main
Commit:   ccc42eb8 "fix(manual-bets): persist fixture metadata for consistent settlement eligibility" — pushed, merged as 6f6c44ea (zero file overlap with concurrent automated GitHub Actions data commits)
```

---

## Session Objective

Investigate a reported settlement inconsistency: for the same fixture, with both a bot pick and a manual bet on the same market, "Executar Resolução" settled the manual bet immediately while the bot pick stayed `LIVE`, only settling correctly on a later, unattended run. Determine the root cause before making any code change, then implement the smallest, safest correction.

---

## Root Cause

**Not a settlement-engine bug.** `run_settlement_remote()` processes bot picks and manual bets in the same synchronous `/run-settlement` request, through the identical `update_dataframe()` function, sharing one provider-response cache — both bet types are already handled atomically by one shared engine (ADR-002/ADR-009). Traced the complete call graph to confirm this before looking anywhere else.

The actual divergence: `update_dataframe()`'s `KICKOFF_TOO_EARLY` gate (`now < KickoffUTC + RESULT_READY_DELAY`, 2h15m) only executes `if kickoff_str:` — it's skipped entirely when a row has no `KickoffUTC` value. Bot picks always have it (propagated end-to-end since Phase 26.7–26.9). Manual bets never did — `addManualBetFromFixture()` never set a `kickoffUTC` field on the bet object. A manual bet therefore became eligible for settlement as soon as its date matched, with no safety margin, while the bot pick for the identical fixture correctly waited out the delay.

**Documentation correction:** Phase 26.7–26.9's own Change Log entry claimed `KickoffUTC` was "propagated through... manual bet objects." That was inaccurate — only a transient, render-time-only placeholder (`kickoffUTC: ''`, for display formatting) ever existed; the field was never actually persisted or read by settlement before this phase. Annotated (not silently rewritten) in `08_Change_Log.md`.

---

## Implementation

**Scope correction before implementing:** the originally-proposed field list (`fixtureId`, `kickoffUTC`, `league`, `leagueId`, `season`) included three fields bot picks themselves don't persist either — confirmed `HISTORY_COLUMNS` has no `FixtureId`/`LeagueId`/`Season` columns, and `update_results.py` never reads any of the three from a row (`season` is derived fresh from `Data` + league lookup at settlement time, identically for both bet types already). `fixtureId` additionally isn't available anywhere in the client-side data model (`fixtures_today.csv`'s schema never included it). Presented this finding and got explicit approval to scope down to what bot picks actually provide plus what's genuinely available.

**What was built:**
- `findFixtureRecord(date, liga, jogo)` — new shared helper (`index.html`) that looks up the matching `state.fixtures` entry. `findFixtureKickoff()` refactored to delegate to it (no duplicated matching logic — the project's own "minimal duplication" principle).
- `loadModelConfig()` extended to also expose `apiFootballLeagueIds` from the already-fetched `config.json` (no new network call).
- `mbHandleCreate()` (Scout "Criar" flow) made `async`; looks up the fixture record and resolves `leagueId`, passes both into `addManualBetFromFixture()`.
- `addManualBetFromFixture()` now accepts and persists `kickoffUTC`, `homeTeam`, `awayTeam`, `leagueId` on the bet object at creation time — immutable, never re-derived from `state.fixtures` later.
- **Zero changes** to the settlement engine, `RESULT_READY_DELAY`, matching logic, or persistence architecture. `manual_bets_to_settlement_df()` already read `bet.get('kickoffUTC')` — it had simply never been given real data. Confirmed `sync_server.py`'s `/save` and `_dedupe_manual_bets()` never strip unrecognized fields, so no backend change was needed either.
- The free-form "Apostas Manuais" text-entry form (`addManualBet()`) is completely untouched — no fixture to source metadata from; preserved exactly as before, per explicit instruction not to invent a workaround.

---

## Files Modified

| File | Reason for change |
|---|---|
| `index.html` | New `findFixtureRecord()`; `findFixtureKickoff()` refactored; `loadModelConfig()` extended; `mbHandleCreate()` made async and resolves fixture metadata; `addManualBetFromFixture()` persists the four new fields |
| `docs/03_Dashboard.md` | `state.manualBets` schema description updated to list the new fixture-backed-only fields and the free-form limitation |
| `docs/04_Backend.md` | `KICKOFF_TOO_EARLY` step and manual-bet-settlement bridge notes updated |
| `docs/05_Known_Issues.md` | New `SETTLEMENT-2` resolved entry |
| `docs/08_Change_Log.md` | Phase 26.7–26.9 entry annotated (inaccurate claim corrected, not rewritten); new Phase 26.32 entry |
| `docs/07_Current_Status.md` | Updated for Phase 26.32 |
| `docs/handovers/handover-2026-07-12-manual-bet-fixture-metadata.md` | This document |

---

## Documentation Updated

- `docs/03_Dashboard.md` — `state.manualBets` field list now distinguishes fixture-backed fields from the always-present ones, and states the free-form limitation explicitly.
- `docs/04_Backend.md` — the settlement row-processing flow and the manual-bet-settlement bridge description both updated to reflect that manual bets now supply `KickoffUTC` too.
- `docs/05_Known_Issues.md` — new `SETTLEMENT-2` resolved entry with full root cause and fix detail.
- `docs/08_Change_Log.md` — Phase 26.7–26.9's entry annotated with a dated note correcting the inaccurate "propagated to manual bet objects" claim (the entry itself was not rewritten, consistent with treating historical Change Log entries as point-in-time records — see the same pattern used for `DASHBOARD-2`/`DASHBOARD-3` in Phase 26.31); new Phase 26.32 entry added.
- `docs/07_Current_Status.md` — updated narrative and the Settlement "Completed Areas" bullet.
- `docs/09_Architecture_Decisions.md` — **no change required.** ADR-002/ADR-009 (shared settlement engine) are exactly what this investigation confirmed still holds true — no architectural decision changed; this was a data-completeness fix at the input layer, not an engine change.
- `docs/PROJECT_MAP.md`, `docs/01_Architecture.md`, `docs/06_Roadmap.md` — **no change required.** None describe this specific field-level detail.

---

## Architectural Decisions

None. No ADR created or changed — the fix operates entirely within ADR-002/ADR-009's existing "one shared settlement engine, fed correct input" model; it doesn't introduce, reverse, or modify an architectural decision.

---

## Current Project State

**Stable.** A bot pick and a manual bet for the same fixture now become eligible for settlement at exactly the same moment. No Python file was modified. No data migration was performed or is required — existing manual bets (with or without the new fields) continue to work exactly as before.

---

## Outstanding Issues

None opened. `SETTLEMENT-2` added to `05_Known_Issues.md` as resolved this session. Pre-existing, unrelated: ST-3, ST-2 (both already on the roadmap).

---

## Validation Performed

- **Python, direct proof (no code modified — this validates the existing engine against new input):** ran the real `update_dataframe()` against three synthetic manual-bet rows — recent kickoff (30 min ago, within the 2h15m delay), old kickoff (3 hours ago, past it), and no `kickoffUTC` at all (simulating a pre-fix bet). Result: the recent-kickoff row was correctly ignored with reason `KICKOFF_TOO_EARLY`; the other two proceeded past the precheck exactly as before. This is definitive proof the fix closes the gap using the completely unmodified settlement engine.
- **`python -m pytest tests/`** — 186/186 passed (unchanged; no Python file was modified).
- **New targeted JS script (15 checks, scratchpad, not committed):** `findFixtureRecord()`/`findFixtureKickoff()` both correct after the refactor; `loadModelConfig()` correctly exposes the real `config.json`'s league IDs; a full Scout "Criar" click persists all four fields with correct values; `fixtureId`/`season` confirmed absent (scope discipline held); the free-form form still creates bets with none of the new fields; a pre-existing bet with none of the new fields still loads/renders without error (no migration needed); zero new console errors.
- **Full existing 6-suite Playwright regression harness** — all 6 suites pass completely, unaffected (no settlement, persistence, or analytics code was touched).
- `node --check` clean on both extracted `<script>` blocks throughout every edit.

---

## Remaining Limitations

- **Free-form manual bets** (created via the "Apostas Manuais" text-entry form, not Scout) have no associated fixture and therefore no `kickoffUTC`/`homeTeam`/`awayTeam`/`leagueId` — they continue to bypass the `RESULT_READY_DELAY` gate exactly as before this phase. This is a documented, accepted limitation, not a bug: there is no fixture to source the metadata from, and no workaround was invented per explicit instruction.
- **Pre-existing manual bets** (created before this phase, even if originally Scout-sourced) also have none of the new fields and are unaffected — no backfill/migration was performed or requested. They'll continue to settle without the kickoff gate until naturally superseded (e.g. if ever recreated).
- **`fixtureId`, `leagueId` (as a settlement input), and `season`** remain outside the settlement engine's actual data contract — bot picks don't persist them either, and nothing currently reads `leagueId` from a manual bet at settlement time. `leagueId` was still added as cheap, harmless, forward-looking metadata; `fixtureId`/`season` were correctly left out per the approved scope.

---

## Next Recommended Task

ST-3 (SHA conflict retry in `sync_server.py`) is next on the roadmap.

---

## Notes for the Next Session

- **If a future settlement-timing question comes up again:** check whether the row actually has `KickoffUTC` populated before suspecting the settlement engine itself — `update_dataframe()` is proven to be one shared, atomic function for both bet types (ADR-002/ADR-009); asymmetries live in the input data, not the engine.
- `findFixtureRecord()` is now the single source of truth for "does this manual bet correspond to a known fixture" — reuse it rather than re-implementing the date/liga/home/away match predicate a third time.
- If `fixtureId` is ever genuinely needed (e.g. for a future feature that can't work from team-name matching alone), it requires extending `fetch_oddsapi_fixtures.py`'s Phase-1 CSV schema — a separate, larger, Bot-side change, not something to bolt onto the manual bet creation flow.

---

## End-of-Session Checklist

- [x] Code committed and pushed — `ccc42eb8`, merged as `6f6c44ea`
- [x] `07_Current_Status.md` updated
- [x] `05_Known_Issues.md` updated (`SETTLEMENT-2` added)
- [x] `08_Change_Log.md` updated (Phase 26.32 entry added; Phase 26.7–26.9 annotated)
- [x] `09_Architecture_Decisions.md` — no change required (ADR-002/ADR-009 unaffected)
- [x] `06_Roadmap.md` — no change required (nothing referenced this work; no priority shifted)
- [x] This handover document filled and saved
- [x] Next session can start from "Next Recommended Task" without reading chat history
