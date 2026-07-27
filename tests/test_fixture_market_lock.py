"""
tests/test_fixture_market_lock.py

Regression coverage for Policy A -- the fixture-level bot-pick market lock
(ADR-018): once one market (O2.5 or BTTS) has been persisted as the
recommendation for a fixture in picks_history.csv, that fixture must never
later receive the competing bot market. See docs/09_Architecture_Decisions.md
ADR-018 and the read-only lifecycle investigation that preceded this fix.

This does NOT redesign the same-run cross-market selection rule
(dedupe_correlated_picks() -- Edge DESC -> KellyTrue DESC -> ProbModel DESC ->
Odd DESC) and does NOT touch Policy B (pre-approval re-evaluation, explicitly
out of scope). The lock is a pre-filter that runs BEFORE that same-run
selection, on the concatenated O2.5+BTTS candidate set, in the single shared
code path both the main (17:00 UTC) and top-up (23:00 UTC) generation jobs
execute (main.py's main(), called with topup_mode=False / True respectively).

Run with:  python -m pytest tests/test_fixture_market_lock.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import src.output_utils as ou
import src.pipeline as pl
from src.history import HISTORY_COLUMNS
from src.market_rules import dedupe_correlated_picks, limit_picks_per_day, apply_stakes
from src.pipeline import (
    apply_fixture_market_lock,
    build_locked_fixture_markets,
    persist_history,
    save_all_outputs,
)


# ── Fixtures / helpers ──────────────────────────────────────────────────────

def _patch_history_path(monkeypatch, tmp_path):
    """Same pattern established in tests/test_history_schema.py: load_history()/
    merge_into_history() read the module-level HISTORY_PATH bound inside
    src.output_utils; persist_history() writes to the one bound inside
    src.pipeline. Both must point at the same temp file."""
    fake_path = tmp_path / "picks_history.csv"
    monkeypatch.setattr(ou, "HISTORY_PATH", fake_path)
    monkeypatch.setattr(pl, "HISTORY_PATH", fake_path)
    return fake_path


def _history_row(date, liga, jogo, mercado, resultado="", settlement_reason="", apostada=""):
    row = {c: "" for c in HISTORY_COLUMNS}
    row.update({
        "Data": date, "Liga": liga, "Jogo": jogo, "Mercado": mercado,
        "Odd": "1.80", "Stake€": "5", "Edge%": "5.0",
        "Apostada": apostada, "Resultado": resultado, "SettlementReason": settlement_reason,
    })
    return row


def _write_history(path, rows):
    pd.DataFrame(rows, columns=HISTORY_COLUMNS).to_csv(path, index=False, sep=";", encoding="utf-8")


def _cand(date, league_key, league_name, home, away, market, edge, odd=1.80, kelly=0.05, prob=0.55):
    """A candidate row shaped exactly like main.py's combo_pre (post
    apply_market_rules, pre same-run dedupe)."""
    return {
        "Date": date, "League": league_key, "LeagueName": league_name,
        "HomeTeam": home, "AwayTeam": away, "Market": market,
        "Edge": edge, "KellyTrue": kelly, "ProbModel": prob,
        "ProbMarket": prob - edge, "Odd": odd,
        "LambdaHome": 1.2, "LambdaAway": 1.1, "LambdaTotal": 2.3,
        "KickoffUTC": f"{date}T19:00:00+00:00",
    }


def _rules():
    return {"kelly_fraction": 1.0, "cap_frac": 1.0, "daily_cap_frac": 1.0, "min_picks": 0}


def _run_generation_like_main(candidates, tmp_path, topup_mode=False):
    """Reproduces main.py's exact post-apply_market_rules sequence:
    concat -> apply_fixture_market_lock -> dedupe_correlated_picks ->
    limit_picks_per_day -> split by market -> apply_stakes -> save_all_outputs
    -> persist_history. Candidates already represent the per-market
    apply_market_rules() output (that stage's own filtering is untouched by
    this feature and is out of scope here)."""
    combo_pre = pd.DataFrame(candidates) if candidates else pd.DataFrame()

    if not combo_pre.empty:
        combo_pre = apply_fixture_market_lock(combo_pre)
    if not combo_pre.empty:
        combo_pre = dedupe_correlated_picks(combo_pre)
        combo_pre = limit_picks_per_day(combo_pre, max_per_day=50, max_global=50)

    if combo_pre.empty:
        out25_final = pd.DataFrame()
        out_btts_final = pd.DataFrame()
        combo = pd.DataFrame()
    else:
        out25_candidates = combo_pre[combo_pre["Market"] == "O2.5"].copy()
        out_btts_candidates = combo_pre[combo_pre["Market"] == "BTTS"].copy()
        out25_final = apply_stakes(out25_candidates, 1000.0, _rules(), "O2.5")
        out_btts_final = apply_stakes(out_btts_candidates, 1000.0, _rules(), "BTTS")
        combo = pd.concat([out25_final, out_btts_final], ignore_index=True) if (len(out25_final) or len(out_btts_final)) else pd.DataFrame()

    simple, *_paths = save_all_outputs(out25_final, out_btts_final, combo, base_dir=tmp_path, topup_mode=topup_mode)
    history = persist_history(simple)
    return {
        "combo_pre": combo_pre, "out25_final": out25_final, "out_btts_final": out_btts_final,
        "combo": combo, "simple": simple, "history": history,
    }


FIXTURE = dict(date="2026-08-01", league_key="premier", league_name="Premier League",
                home="Team A", away="Team B")


# ── 1. Same run, both qualify, no prior history: same-run selection unchanged ──

def test_same_run_no_prior_history_highest_edge_wins_unchanged(monkeypatch, tmp_path):
    _patch_history_path(monkeypatch, tmp_path)
    o25 = _cand(**FIXTURE, market="O2.5", edge=0.08)
    btts = _cand(**FIXTURE, market="BTTS", edge=0.11)
    result = _run_generation_like_main([o25, btts], tmp_path)
    assert list(result["combo_pre"]["Market"]) == ["BTTS"], (
        "With no prior history the fixture lock must be a complete no-op -- "
        "dedupe_correlated_picks() must still pick BTTS (higher Edge) exactly "
        "as before this feature existed."
    )


# ── 2/3/4. Direct apply_fixture_market_lock(): competing market rejected ──────

def test_lock_rejects_competing_market_when_o25_already_in_history(monkeypatch, tmp_path):
    history_path = _patch_history_path(monkeypatch, tmp_path)
    _write_history(history_path, [_history_row(**{"date": FIXTURE["date"], "liga": FIXTURE["league_name"],
                                                    "jogo": f"{FIXTURE['home']} vs {FIXTURE['away']}", "mercado": "O2.5"})])
    btts = _cand(**FIXTURE, market="BTTS", edge=0.20)  # much higher edge -- must still be rejected
    out = apply_fixture_market_lock(pd.DataFrame([btts]))
    assert out.empty, "BTTS must be rejected once O2.5 is already persisted for this fixture, regardless of Edge"


def test_lock_rejects_competing_market_when_btts_already_in_history(monkeypatch, tmp_path):
    history_path = _patch_history_path(monkeypatch, tmp_path)
    _write_history(history_path, [_history_row(FIXTURE["date"], FIXTURE["league_name"],
                                                 f"{FIXTURE['home']} vs {FIXTURE['away']}", "BTTS")])
    o25 = _cand(**FIXTURE, market="O2.5", edge=0.20)
    out = apply_fixture_market_lock(pd.DataFrame([o25]))
    assert out.empty, "O2.5 must be rejected once BTTS is already persisted for this fixture, regardless of Edge"


# ── 5. Same market regeneration: allowed through, no duplicate history row ────

def test_same_market_regeneration_passes_lock_and_does_not_duplicate_history(monkeypatch, tmp_path):
    history_path = _patch_history_path(monkeypatch, tmp_path)
    _write_history(history_path, [_history_row(FIXTURE["date"], FIXTURE["league_name"],
                                                 f"{FIXTURE['home']} vs {FIXTURE['away']}", "O2.5")])
    o25_again = _cand(**FIXTURE, market="O2.5", edge=0.09)
    out = apply_fixture_market_lock(pd.DataFrame([o25_again]))
    assert len(out) == 1, "The already-locked market must be allowed to keep flowing through the pipeline"

    result = _run_generation_like_main([o25_again], tmp_path)
    assert len(result["out25_final"]) == 1, "Locked market must still reach the daily-file/current-state pipeline"
    fixture_rows = result["history"][result["history"]["Jogo"] == f"{FIXTURE['home']} vs {FIXTURE['away']}"]
    assert len(fixture_rows) == 1, "No second history row may be created for the same fixture+market"


# ── 6/7/8. Lock applies regardless of Apostada / approval / cancel state ──────

@pytest.mark.parametrize("apostada", ["", "sim"])
def test_lock_ignores_apostada_unapproved_and_approved_both_lock(monkeypatch, tmp_path, apostada):
    history_path = _patch_history_path(monkeypatch, tmp_path)
    _write_history(history_path, [_history_row(FIXTURE["date"], FIXTURE["league_name"],
                                                 f"{FIXTURE['home']} vs {FIXTURE['away']}", "O2.5",
                                                 apostada=apostada)])
    btts = _cand(**FIXTURE, market="BTTS", edge=0.30)
    out = apply_fixture_market_lock(pd.DataFrame([btts]))
    assert out.empty, (
        f"Lock must trigger identically regardless of Apostada={apostada!r} -- "
        "the backend never reads Apostada to decide whether the lock applies "
        "(approval/cancel are frontend-only cloud_state.json concepts that "
        "never reach picks_history.csv at all)."
    )


# ── 9/10/11. W / L / P lock the fixture ────────────────────────────────────

@pytest.mark.parametrize("resultado", ["W", "L", "P"])
def test_settled_result_locks_fixture(monkeypatch, tmp_path, resultado):
    history_path = _patch_history_path(monkeypatch, tmp_path)
    _write_history(history_path, [_history_row(FIXTURE["date"], FIXTURE["league_name"],
                                                 f"{FIXTURE['home']} vs {FIXTURE['away']}", "O2.5",
                                                 resultado=resultado)])
    btts = _cand(**FIXTURE, market="BTTS", edge=0.30)
    out = apply_fixture_market_lock(pd.DataFrame([btts]))
    assert out.empty, f"Resultado={resultado} must still lock the fixture against the competing market"


# ── 12/13/14. Void reasons (manual_void / postponed_timeout / missing_fixture_timeout) lock ──

@pytest.mark.parametrize("reason", ["manual_void", "postponed_timeout", "missing_fixture_timeout"])
def test_void_reason_locks_fixture(monkeypatch, tmp_path, reason):
    history_path = _patch_history_path(monkeypatch, tmp_path)
    _write_history(history_path, [_history_row(FIXTURE["date"], FIXTURE["league_name"],
                                                 f"{FIXTURE['home']} vs {FIXTURE['away']}", "O2.5",
                                                 resultado="P", settlement_reason=reason)])
    btts = _cand(**FIXTURE, market="BTTS", edge=0.30)
    out = apply_fixture_market_lock(pd.DataFrame([btts]))
    assert out.empty, f"SettlementReason={reason} must still lock the fixture against the competing market"
    # ADR-017/ADR-015 safety: this test does not call update_dataframe() or touch
    # SettlementReason/MissingAttempts semantics at all -- the lock works purely
    # because the historical recommendation already exists, exactly as required.


# ── 15/16. Cross-run flip cannot persist second market (main AND top-up) ──────

@pytest.mark.parametrize("topup_mode", [False, True])
def test_cross_run_flip_cannot_persist_second_market(monkeypatch, tmp_path, topup_mode):
    history_path = _patch_history_path(monkeypatch, tmp_path)

    # Run 1: O2.5 wins and is persisted (non-topup, matching real production).
    run1 = _run_generation_like_main([_cand(**FIXTURE, market="O2.5", edge=0.07)], tmp_path, topup_mode=False)
    assert list(run1["history"]["Mercado"]) == ["O2.5"]

    # Run 2 (main or top-up): BTTS now has the higher Edge.
    run2 = _run_generation_like_main([_cand(**FIXTURE, market="BTTS", edge=0.11)], tmp_path, topup_mode=topup_mode)

    assert run2["out_btts_final"].empty, "BTTS must never reach out_btts_final on the cross-run flip"
    assert "BTTS" not in set(run2["history"]["Mercado"]), "BTTS must never be persisted to picks_history.csv"
    assert list(run2["history"]["Mercado"]) == ["O2.5"], "picks_history.csv must still contain only the original O2.5 row"


# ── 17. Top-up cannot leave both markets in the daily files ───────────────────

def test_topup_does_not_leave_both_markets_in_daily_files(monkeypatch, tmp_path):
    _patch_history_path(monkeypatch, tmp_path)

    # Main run (17:00 UTC): O2.5 selected and written to picks_hoje_simplificado.csv.
    _run_generation_like_main([_cand(**FIXTURE, market="O2.5", edge=0.06)], tmp_path, topup_mode=False)

    # Top-up run (23:00 UTC) later the same day: BTTS now wins.
    _run_generation_like_main([_cand(**FIXTURE, market="BTTS", edge=0.15)], tmp_path, topup_mode=True)

    simple_path = tmp_path / "picks_hoje_simplificado.csv"
    daily = pd.read_csv(simple_path, sep=";", dtype=str).fillna("")
    fixture_rows = daily[daily["Jogo"] == f"{FIXTURE['home']} vs {FIXTURE['away']}"]
    assert list(fixture_rows["Mercado"]) == ["O2.5"], (
        "Top-up's append/upsert semantics must not leave BTTS sitting alongside "
        "the locked O2.5 row in picks_hoje_simplificado.csv"
    )


# ── 18. Rolling days_ahead re-evaluation never creates a second market ────────

def test_rolling_reevaluation_never_creates_second_market(monkeypatch, tmp_path):
    _patch_history_path(monkeypatch, tmp_path)

    day_n = _run_generation_like_main([_cand(**FIXTURE, market="O2.5", edge=0.05)], tmp_path)
    assert list(day_n["history"]["Mercado"]) == ["O2.5"]

    day_n1 = _run_generation_like_main([_cand(**FIXTURE, market="BTTS", edge=0.09)], tmp_path)
    assert list(day_n1["history"]["Mercado"]) == ["O2.5"]

    day_n2 = _run_generation_like_main([_cand(**FIXTURE, market="BTTS", edge=0.14)], tmp_path)
    assert list(day_n2["history"]["Mercado"]) == ["O2.5"], (
        "Even a third re-evaluation with a still-higher BTTS Edge must never "
        "create a second history row for this fixture"
    )
    assert len(day_n2["history"]) == 1


# ── 19. Telegram cannot receive the rejected competing candidate ──────────────

def test_rejected_competing_candidate_never_reaches_notification_inputs(monkeypatch, tmp_path):
    _patch_history_path(monkeypatch, tmp_path)
    _run_generation_like_main([_cand(**FIXTURE, market="O2.5", edge=0.07)], tmp_path)

    run2 = _run_generation_like_main([_cand(**FIXTURE, market="BTTS", edge=0.20)], tmp_path)
    # process_notifications(out25_final=..., out_btts_final=...) is called with
    # exactly these two frames in main.py -- if BTTS is absent here, Telegram
    # structurally cannot have been offered it.
    assert run2["out_btts_final"].empty


# ── 23. MLS / MLS Next Pro remain independently lockable ──────────────────────

def test_mls_and_mls_next_pro_lock_independently(monkeypatch, tmp_path):
    _patch_history_path(monkeypatch, tmp_path)
    mls_fixture = dict(date="2026-08-01", league_key="mls", league_name="MLS", home="Home X", away="Away Y")
    mls_np_fixture = dict(date="2026-08-01", league_key="mls_next_pro", league_name="MLS Next Pro", home="Home X", away="Away Y")

    _run_generation_like_main([_cand(**mls_fixture, market="O2.5", edge=0.06)], tmp_path)

    # MLS Next Pro's own O2.5/BTTS candidates for a same-named fixture must be
    # completely unaffected by senior MLS's lock -- different League/LeagueName
    # means a different fixture id (ADR-004: never collapsed).
    result = _run_generation_like_main(
        [_cand(**mls_np_fixture, market="O2.5", edge=0.05), _cand(**mls_np_fixture, market="BTTS", edge=0.09)],
        tmp_path,
    )
    assert list(result["combo_pre"]["Market"]) == ["BTTS"], "MLS Next Pro's own same-run selection must proceed normally"

    history = pd.read_csv(tmp_path / "picks_history.csv", sep=";", dtype=str).fillna("")
    mls_rows = history[history["Liga"] == "MLS"]
    mls_np_rows = history[history["Liga"] == "MLS Next Pro"]
    assert list(mls_rows["Mercado"]) == ["O2.5"]
    assert list(mls_np_rows["Mercado"]) == ["BTTS"]


# ── 25. Legacy dual-market fixtures: both markets remain allowed, never migrated ──

def test_legacy_dual_market_fixture_both_markets_remain_allowed_no_third_market_possible(monkeypatch, tmp_path):
    """Simulates the ALREADY-EXISTING production shape of West Ham vs Leeds /
    Gnistan vs Mariehamn (both O2.5 and BTTS already persisted for one fixture,
    from before this fix existed) using synthetic data only -- the real
    picks_history.csv is never read or written by this test. Proves the lock
    does not attempt to retroactively collapse such a fixture down to one
    market (which would require deleting/migrating a real row -- explicitly
    out of scope), while confirming there is no THIRD market either market
    could ever "flip" to."""
    history_path = _patch_history_path(monkeypatch, tmp_path)
    jogo = f"{FIXTURE['home']} vs {FIXTURE['away']}"
    _write_history(history_path, [
        _history_row(FIXTURE["date"], FIXTURE["league_name"], jogo, "O2.5"),
        _history_row(FIXTURE["date"], FIXTURE["league_name"], jogo, "BTTS"),
    ])
    locked = build_locked_fixture_markets(pd.read_csv(history_path, sep=";", dtype=str).fillna(""))
    fid = f"{FIXTURE['date']}|{FIXTURE['league_name']}|{jogo}"
    assert locked[fid] == {"O2.5", "BTTS"}

    o25_again = _cand(**FIXTURE, market="O2.5", edge=0.05)
    btts_again = _cand(**FIXTURE, market="BTTS", edge=0.05)
    out = apply_fixture_market_lock(pd.DataFrame([o25_again, btts_again]))
    assert len(out) == 2, "Both markets remain allowed to continue (no third market exists to reject)"


# ── build_locked_fixture_markets() / apply_fixture_market_lock() basics ───────

def test_build_locked_fixture_markets_empty_history_returns_empty_dict():
    assert build_locked_fixture_markets(pd.DataFrame(columns=HISTORY_COLUMNS)) == {}


def test_apply_fixture_market_lock_noop_on_empty_history(monkeypatch, tmp_path):
    _patch_history_path(monkeypatch, tmp_path)  # no file written -> load_history() returns empty
    df = pd.DataFrame([_cand(**FIXTURE, market="O2.5", edge=0.05)])
    out = apply_fixture_market_lock(df)
    assert len(out) == 1


def test_apply_fixture_market_lock_noop_on_empty_candidates(monkeypatch, tmp_path):
    _patch_history_path(monkeypatch, tmp_path)
    out = apply_fixture_market_lock(pd.DataFrame())
    assert out.empty


# ── Manual bets: no shared code path (source-level guard) ─────────────────────

def test_fixture_lock_module_never_references_manual_bets_or_cloud_state():
    """The fix must remain bot-only. apply_fixture_market_lock()/
    build_locked_fixture_markets() operate exclusively on picks_history.csv and
    in-memory bot candidate DataFrames -- proven by construction here: neither
    function references cloud_state.json, manualBets, or localEdits anywhere
    in src/pipeline.py."""
    source = (ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")
    for forbidden in ("manualBets", "cloud_state", "localEdits"):
        assert forbidden not in source


# ── main.py wiring: single shared boundary, correct ordering ──────────────────
# main() itself is not practically unit-testable (live fixture fetch over
# HTTP) -- these are source-level guards, the same established pattern used by
# tests/test_league_stats_persistence.py for the same reason.

def test_main_py_calls_fixture_lock_exactly_once_unconditionally():
    """There must be exactly ONE call site, reached identically whether
    topup_mode is True or False -- i.e. it must NOT sit inside an
    `if topup_mode` / `if not topup_mode` branch. This is what makes it a
    single shared mechanism rather than two independent implementations."""
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert source.count("apply_fixture_market_lock(") == 2, (
        "Expected exactly one import reference + one call site"
    )
    call_idx = source.index("combo_pre = apply_fixture_market_lock(")
    preceding = source[:call_idx]
    # The nearest enclosing `if` block above the call must be the unconditional
    # `if not combo_pre.empty:` every other stage in this section already uses
    # -- found by locating the last top-level `if` before the call.
    nearest_if_idx = preceding.rfind("\n    if ")
    nearest_if_line = preceding[nearest_if_idx + 1:].splitlines()[0]
    assert "if not combo_pre.empty:" in nearest_if_line, (
        f"The call's nearest enclosing guard must be the unconditional "
        f"combo_pre.empty check, not a topup-specific branch. Found: {nearest_if_line!r}"
    )
    between = preceding[nearest_if_idx:]
    assert "topup_mode" not in between, (
        "No topup_mode conditional should sit between the enclosing guard and the "
        "lock call -- it must run identically for both main and top-up invocations"
    )


def test_main_py_fixture_lock_runs_before_combined_dedupe():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    lock_idx = source.index("combo_pre = apply_fixture_market_lock(")
    dedupe_idx = source.index("combo_pre = dedupe_correlated_picks(combo_pre)")
    assert lock_idx < dedupe_idx, (
        "The fixture lock must run BEFORE the same-run cross-market dedupe, so an "
        "unlocked fixture's Edge/Kelly/Prob/Odd comparison is completely untouched"
    )


def test_no_second_fixture_id_implementation_exists_in_repo():
    """Guards against a second, slightly-different fixture-key implementation
    being introduced anywhere (e.g. duplicated string construction in
    main.py) -- fixture_id_from_* must be defined exactly once, in
    src/history.py, and imported everywhere else it is used."""
    import subprocess
    result = subprocess.run(
        ["git", "grep", "-n", "^def fixture_id_from"],
        cwd=ROOT, capture_output=True, text=True,
    )
    def_lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert all("src/history.py" in l or "src\\history.py" in l for l in def_lines), (
        f"fixture_id_from_* must only be defined in src/history.py, found: {def_lines}"
    )
    assert len(def_lines) == 3, f"Expected exactly 3 definitions (parts/simple/candidate), found: {def_lines}"
