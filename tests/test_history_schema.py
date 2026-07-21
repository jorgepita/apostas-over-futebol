"""
tests/test_history_schema.py

Regression coverage for Blocker 3 of Phase 26.43's pre-commit safety audit:
src/history.py's HISTORY_COLUMNS was never updated when Placar was added
(Phase 26.19), so the daily generation path (main.py -> persist_history() ->
merge_into_history() -> ensure_simple_columns()) silently stripped Placar
from every settled row on each generation cycle — confirmed already active
in production (90/93 settled rows in the real picks_history.csv had an empty
Placar at the time of the audit). Phase 26.43's new SettlementReason/
MissingAttempts columns were exposed to the identical erasure path.

This fix is preventative only — it stops future loss. It does NOT and must
NOT attempt to reconstruct already-lost historical Placar values; that would
require querying providers for old fixture data, which is explicitly out of
scope for this correction (see the session's final report).

Run with:  python -m pytest tests/test_history_schema.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import update_results as ur
from src.history import HISTORY_COLUMNS
import src.output_utils as ou


# ── HISTORY_COLUMNS must stay a superset-compatible mirror of CSV_COLUMNS ──

def test_history_columns_matches_canonical_csv_columns():
    # update_results.py's CSV_COLUMNS is the canonical settlement schema
    # (see its own docstring). HISTORY_COLUMNS must describe exactly the
    # same set of fields — this is the specific assertion that would have
    # caught the Placar-loss bug immediately when Placar was added in
    # Phase 26.19, and must catch the next schema drift too.
    assert set(HISTORY_COLUMNS) == set(ur.CSV_COLUMNS), (
        "HISTORY_COLUMNS has drifted from update_results.CSV_COLUMNS — "
        "any settlement-written field missing here will be silently "
        "stripped by ensure_simple_columns() on the next daily generation "
        "run (see merge_into_history())."
    )


def test_history_columns_includes_the_three_audit_fields():
    for col in ("Placar", "SettlementReason", "MissingAttempts"):
        assert col in HISTORY_COLUMNS, f"{col} missing from HISTORY_COLUMNS"


# ── ensure_simple_columns(): legacy rows tolerate missing columns ─────────

def test_ensure_simple_columns_fills_legacy_row_without_new_fields():
    legacy = pd.DataFrame([{
        "Data": "2026-01-01", "Liga": "MLS", "Jogo": "A vs B", "Mercado": "O2.5",
        "Odd": "1.5", "Stake€": "10", "Resultado": "W", "Lucro€": "5",
    }])
    out = ou.ensure_simple_columns(legacy)
    assert list(out.columns) == HISTORY_COLUMNS
    assert out.iloc[0]["Placar"] == ""
    assert out.iloc[0]["SettlementReason"] == ""
    assert out.iloc[0]["MissingAttempts"] == ""
    assert out.iloc[0]["Resultado"] == "W"  # untouched


# ── merge_into_history(): realistic merge/write/read cycle ────────────────

def _patch_history_path(monkeypatch, tmp_path):
    fake_path = tmp_path / "picks_history.csv"
    monkeypatch.setattr(ou, "HISTORY_PATH", fake_path)
    return fake_path


def test_merge_into_history_preserves_placar_settlementreason_missingattempts(monkeypatch, tmp_path):
    history_path = _patch_history_path(monkeypatch, tmp_path)

    existing = pd.DataFrame([{
        "Data": "2026-07-17", "Liga": "MLS", "Jogo": "Chicago Fire vs Vancouver Whitecaps",
        "Mercado": "O2.5", "Odd": "1.55", "Stake€": "0.31", "Edge%": "5.08",
        "Apostada": "", "OddReal": "", "StakeReal€": "",
        "Resultado": "P", "Placar": "", "Lucro€": "0.0", "LucroReal€": "",
        "KickoffUTC": "2026-07-17T00:30:00+00:00",
        "SettlementReason": "missing_fixture_timeout", "MissingAttempts": "3",
    }])
    existing.to_csv(history_path, index=False, sep=";", encoding="utf-8")

    new_picks = pd.DataFrame([{
        "Data": "2026-07-21", "Liga": "Premier League", "Jogo": "New Home vs New Away",
        "Mercado": "O2.5", "Odd": "1.80", "Stake€": "5", "Edge%": "4.0",
        "KickoffUTC": "2026-07-21T19:00:00+00:00",
    }])

    merged = ou.merge_into_history(new_picks)
    assert set(merged.columns) == set(HISTORY_COLUMNS)

    chicago = merged[merged["Jogo"].str.contains("Chicago Fire", na=False)].iloc[0]
    assert chicago["Resultado"] == "P"
    assert chicago["SettlementReason"] == "missing_fixture_timeout"
    assert chicago["MissingAttempts"] == "3"

    new_row = merged[merged["Jogo"] == "New Home vs New Away"].iloc[0]
    assert new_row["SettlementReason"] == ""
    assert new_row["MissingAttempts"] == ""


def test_merge_into_history_preserves_placar_on_a_normally_settled_fixture(monkeypatch, tmp_path):
    history_path = _patch_history_path(monkeypatch, tmp_path)

    existing = pd.DataFrame([{
        "Data": "2026-07-20", "Liga": "Allsvenskan", "Jogo": "Kalmar FF vs Malmo FF",
        "Mercado": "O2.5", "Odd": "1.60", "Stake€": "2", "Edge%": "3.0",
        "Apostada": "", "OddReal": "", "StakeReal€": "",
        "Resultado": "W", "Placar": "2-2", "Lucro€": "1.2", "LucroReal€": "",
        "KickoffUTC": "2026-07-20T17:00:00+00:00",
        "SettlementReason": "", "MissingAttempts": "",
    }])
    existing.to_csv(history_path, index=False, sep=";", encoding="utf-8")

    merged = ou.merge_into_history(pd.DataFrame(columns=HISTORY_COLUMNS))
    row = merged[merged["Jogo"] == "Kalmar FF vs Malmo FF"].iloc[0]
    assert row["Placar"] == "2-2", "Placar must survive the merge — this is the bug that was already live in production"


def test_merge_into_history_tolerates_a_legacy_row_missing_all_new_columns(monkeypatch, tmp_path):
    # An OLD picks_history.csv row from before Placar/SettlementReason/
    # MissingAttempts existed at all (no such columns in the file).
    history_path = _patch_history_path(monkeypatch, tmp_path)
    legacy_only_cols = [
        "Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€", "Edge%",
        "Apostada", "OddReal", "StakeReal€", "Resultado", "Lucro€", "LucroReal€", "KickoffUTC",
    ]
    existing = pd.DataFrame([{
        "Data": "2026-05-01", "Liga": "J1 League", "Jogo": "Legacy Home vs Legacy Away",
        "Mercado": "O2.5", "Odd": "1.70", "Stake€": "3", "Edge%": "2.0",
        "Apostada": "", "OddReal": "", "StakeReal€": "",
        "Resultado": "L", "Lucro€": "-3.0", "LucroReal€": "", "KickoffUTC": "2026-05-01T10:00:00+00:00",
    }], columns=legacy_only_cols)
    existing.to_csv(history_path, index=False, sep=";", encoding="utf-8")

    merged = ou.merge_into_history(pd.DataFrame(columns=HISTORY_COLUMNS))
    assert set(merged.columns) == set(HISTORY_COLUMNS)
    row = merged[merged["Jogo"] == "Legacy Home vs Legacy Away"].iloc[0]
    assert row["Resultado"] == "L"
    assert row["Placar"] == ""
    assert row["SettlementReason"] == ""
    assert row["MissingAttempts"] == ""


# ── save_all_outputs(): generation must not raise on the extended schema ──

def test_save_all_outputs_does_not_raise_with_extended_history_columns(tmp_path):
    from src.pipeline import save_all_outputs

    combo = pd.DataFrame([{
        "HomeTeam": "Home A", "AwayTeam": "Away B", "Date": "2026-08-01",
        "LeagueName": "Premier League", "Market": "O2.5", "Odd": "1.9",
        "Stake€": "5", "Edge": "0.08", "KickoffUTC": "2026-08-01T19:00:00+00:00",
    }])
    out25 = combo.copy()
    btts = pd.DataFrame(columns=combo.columns)

    simple, *_ = save_all_outputs(out25, btts, combo, tmp_path, topup_mode=False)
    assert list(simple.columns) == HISTORY_COLUMNS
    assert simple.iloc[0]["Placar"] == ""
    assert simple.iloc[0]["SettlementReason"] == ""
    assert simple.iloc[0]["MissingAttempts"] == ""


# ── Multi-run MissingAttempts persistence through the ACTUAL history-merge
#    lifecycle (not just update_dataframe() in isolation) ─────────────────

def make_af_fetch_mock(date_to_fixtures):
    def _fake_fetch(league_code, date_str, shared_state):
        if date_str in date_to_fixtures:
            val = date_to_fixtures[date_str]
            if val is None:
                return None, "PROVIDER_ERROR"
            return val, ""
        return [], ""
    return _fake_fetch


def test_missing_attempts_survives_three_runs_through_history_merge(monkeypatch, tmp_path):
    """Re-validates the safety audit's multi-run persistence proof, but
    routed through the REAL history_merge lifecycle (ensure_simple_columns()/
    merge_into_history()) instead of a raw safe_read_csv()/to_csv() round trip
    — this is the exact path the audit found was independently capable of
    erasing MissingAttempts even though update_dataframe() itself was proven
    correct."""
    from datetime import datetime, timedelta, timezone

    history_path = _patch_history_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ur, "fetch_api_football_fixtures_for_league_date", make_af_fetch_mock({}))

    kickoff = datetime.now(timezone.utc) - timedelta(hours=80)
    row = {c: "" for c in ur.CSV_COLUMNS}
    row.update({
        "Data": kickoff.date().isoformat(), "Liga": "MLS", "Jogo": "History Merge Home vs History Merge Away",
        "Mercado": "O2.5", "Odd": "1.55", "Stake€": "10",
        "KickoffUTC": kickoff.astimezone(timezone.utc).isoformat(),
    })
    pd.DataFrame([row]).to_csv(history_path, index=False, sep=";", encoding="utf-8")

    for run_no in (1, 2, 3):
        # Fresh "process": read exactly as load_history() would (ensure_simple_columns applied).
        history_df = ou.load_history()
        this_row = history_df[history_df["Jogo"] == "History Merge Home vs History Merge Away"]
        pre_attempts = this_row.iloc[0]["MissingAttempts"]
        print(f"RUN {run_no} pre  MissingAttempts={pre_attempts!r}")

        shared_state = ur.make_shared_runtime_state()
        settled_df, updated, _, _ = ur.update_dataframe(history_df, "history", shared_state)

        # Write back exactly as main.py's settlement write site does.
        settled_df.to_csv(history_path, index=False, sep=";", encoding="utf-8")

        # Then simulate the SAME-DAY generation cycle's merge_into_history()
        # call running afterward (no new picks this run — just the merge
        # pass-through) — this is the step that used to erase the field.
        merged = ou.merge_into_history(pd.DataFrame(columns=HISTORY_COLUMNS))
        merged.to_csv(history_path, index=False, sep=";", encoding="utf-8")

        post_row = merged[merged["Jogo"] == "History Merge Home vs History Merge Away"].iloc[0]
        print(f"RUN {run_no} post MissingAttempts={post_row['MissingAttempts']!r} Resultado={post_row['Resultado']!r}")

        if run_no < 3:
            assert post_row["MissingAttempts"] == str(run_no)
            assert post_row["Resultado"] == ""
        else:
            assert post_row["MissingAttempts"] == "3"
            assert post_row["Resultado"] == "P"
            assert post_row["SettlementReason"] == "missing_fixture_timeout"


def test_settlement_reason_and_placar_survive_generation_cycle_after_void(monkeypatch, tmp_path):
    """Explicit-status void (not missing-fixture) case: settle a row as P via
    the explicit-status pathway, then run it through a generation-cycle merge
    (as if main.py ran later the same day), and confirm SettlementReason
    survives. Also proves Placar survives on a normal W/L settlement passed
    through the same cycle — the prospective fix for the pre-existing bug."""
    from datetime import datetime, timedelta, timezone

    history_path = _patch_history_path(monkeypatch, tmp_path)

    kickoff = datetime.now(timezone.utc) - timedelta(hours=49)
    date_str = kickoff.date().isoformat()

    void_row = {c: "" for c in ur.CSV_COLUMNS}
    void_row.update({
        "Data": date_str, "Liga": "MLS", "Jogo": "Void Home vs Void Away",
        "Mercado": "O2.5", "Odd": "1.55", "Stake€": "10",
        "KickoffUTC": kickoff.astimezone(timezone.utc).isoformat(),
    })
    win_row = {c: "" for c in ur.CSV_COLUMNS}
    win_row.update({
        "Data": date_str, "Liga": "MLS", "Jogo": "Win Home vs Win Away",
        "Mercado": "O2.5", "Odd": "1.55", "Stake€": "10",
        "KickoffUTC": kickoff.astimezone(timezone.utc).isoformat(),
    })
    df = pd.DataFrame([void_row, win_row])

    def fake_fetch(league_code, date, shared_state):
        return [
            {
                "fixture": {"status": {"short": "PST"}, "date": kickoff.astimezone(timezone.utc).isoformat()},
                "teams": {"home": {"name": "Void Home"}, "away": {"name": "Void Away"}},
                "goals": {"home": None, "away": None},
            },
            {
                "fixture": {"status": {"short": "FT"}, "date": kickoff.astimezone(timezone.utc).isoformat()},
                "teams": {"home": {"name": "Win Home"}, "away": {"name": "Win Away"}},
                "goals": {"home": 2, "away": 1},
            },
        ], ""
    monkeypatch.setattr(ur, "fetch_api_football_fixtures_for_league_date", fake_fetch)

    shared_state = ur.make_shared_runtime_state()
    settled_df, updated, _, _ = ur.update_dataframe(df, "history", shared_state)
    assert updated == 2
    settled_df.to_csv(history_path, index=False, sep=";", encoding="utf-8")

    # Simulate the next generation cycle's merge pass.
    merged = ou.merge_into_history(pd.DataFrame(columns=HISTORY_COLUMNS))

    void_after = merged[merged["Jogo"] == "Void Home vs Void Away"].iloc[0]
    win_after = merged[merged["Jogo"] == "Win Home vs Win Away"].iloc[0]

    assert void_after["Resultado"] == "P"
    assert void_after["SettlementReason"] == "postponed_timeout", "SettlementReason must survive the generation cycle"

    assert win_after["Resultado"] == "W"
    assert win_after["Placar"] == "2-1", "Placar must survive the generation cycle — the prospective fix for the pre-existing bug"
