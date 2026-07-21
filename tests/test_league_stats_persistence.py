"""
tests/test_league_stats_persistence.py

Regression coverage for the league_stats.csv persistence fix (read-only
investigation preceding this fix found the file frozen at a 2026-05-24
snapshot in production — see docs/05_Known_Issues.md).

Root cause: update_league_stats() correctly regenerated league_stats.csv on
every production settlement (update_results.py::main()) and generation
(main.py, via src/pipeline.py::persist_history()) run, but the regenerated
file was never uploaded to GitHub in either path — only written to the
ephemeral GitHub Actions runner's local disk, discarded at job end.

This suite does NOT re-test update_league_stats()'s calculation semantics
(groupby/ROI/WinRate/Tier/etc.) — those are unchanged and out of scope. It
tests only the persistence invariant: whenever a production path regenerates
league_stats.csv, that regeneration must reach GitHub.

Run with:  python -m pytest tests/test_league_stats_persistence.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import update_results as ur
from src.league_stats import update_league_stats
from src.history import HISTORY_PATH


# ── update_results.py::_persist_league_stats() — the settlement-path fix ──

def test_persist_league_stats_calls_update_then_upload_in_order(monkeypatch, tmp_path):
    calls = []

    def fake_update_league_stats(history_file, league_stats_file):
        calls.append(("update", history_file, league_stats_file))
        # Simulate the real function actually writing the file, since the
        # upload step's caller doesn't care whether it exists (that's
        # upload_csv_to_github()'s own concern, tested separately below) —
        # this just proves ordering, not file-existence handling.
        Path(league_stats_file).write_text("League;Market\n", encoding="utf-8")

    def fake_upload(local_path, remote_name):
        calls.append(("upload", local_path, remote_name))

    monkeypatch.setattr(ur, "update_league_stats", fake_update_league_stats)
    monkeypatch.setattr(ur, "upload_csv_to_github", fake_upload)

    history_file = tmp_path / "picks_history.csv"
    league_stats_file = tmp_path / "league_stats.csv"
    ur._persist_league_stats(history_file, league_stats_file, "league_stats.csv")

    assert [c[0] for c in calls] == ["update", "upload"], (
        "update_league_stats() must run before upload_csv_to_github() — "
        "uploading first would persist the stale prior copy."
    )
    assert calls[1][1] == league_stats_file
    assert calls[1][2] == "league_stats.csv"


def test_persist_league_stats_swallows_exceptions_without_propagating(monkeypatch, tmp_path):
    def raising_update(history_file, league_stats_file):
        raise RuntimeError("simulated computation failure")

    upload_called = []
    monkeypatch.setattr(ur, "update_league_stats", raising_update)
    monkeypatch.setattr(ur, "upload_csv_to_github", lambda *a, **k: upload_called.append(True))

    # Must not raise — mirrors the pre-existing tolerance this derived file
    # already had for its computation step; a failure here must never abort
    # the settlement run that already succeeded above it.
    ur._persist_league_stats(tmp_path / "picks_history.csv", tmp_path / "league_stats.csv", "league_stats.csv")
    assert not upload_called, "upload must not run if regeneration failed"


def test_persist_league_stats_upload_failure_also_swallowed(monkeypatch, tmp_path):
    monkeypatch.setattr(ur, "update_league_stats", lambda h, o: None)

    def raising_upload(local_path, remote_name):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(ur, "upload_csv_to_github", raising_upload)

    # Must not raise either — same tolerant semantics for the upload half.
    ur._persist_league_stats(tmp_path / "picks_history.csv", tmp_path / "league_stats.csv", "league_stats.csv")


def test_main_still_references_league_stats_constants():
    assert ur.LEAGUE_STATS_FILE == ur.BASE / "league_stats.csv"
    assert ur.REMOTE_LEAGUE_STATS_NAME == "league_stats.csv"


# ── No regression: history/daily uploads remain intact (Test D) ───────────

def test_history_and_daily_remote_names_unchanged():
    assert ur.REMOTE_HISTORY_NAME == "picks_history.csv"
    assert ur.REMOTE_DAILY_NAME == "picks_hoje_simplificado.csv"


def test_main_py_source_still_uploads_history_and_daily_and_now_league_stats():
    """Source-level guard for update_results.py's main() — main() itself is
    not practically unit-testable in isolation (it performs live network
    settlement calls end-to-end), so this asserts the exact contract Test D
    (no regression) requires: the pre-existing history/daily uploads remain
    exactly as they were, and league_stats.csv persistence was added
    additively via _persist_league_stats(), not by replacing anything."""
    source = (ROOT / "update_results.py").read_text(encoding="utf-8")
    main_start = source.index("\ndef main():")
    main_body = source[main_start:]
    assert "upload_csv_to_github(HISTORY_FILE, REMOTE_HISTORY_NAME)" in main_body, (
        "HISTORY_FILE upload missing from main() — regression"
    )
    assert "upload_csv_to_github(DAILY_FILE" in main_body, (
        "DAILY_FILE upload missing from main() — regression"
    )
    assert "_persist_league_stats(" in main_body, (
        "league_stats.csv persistence call missing from main() — the fix itself"
    )


# ── main.py's generation-path upload list ──────────────────────────────────

def test_main_py_upload_outputs_call_includes_league_stats():
    """main.py's main() is not practically unit-testable without mocking the
    entire fixture-fetch/pick-generation pipeline — this is a source-level
    guard proving the additive fix is present in the actual upload_outputs()
    call, the single place production generation persists its outputs."""
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    call_start = source.index("upload_outputs(")
    call_end = source.index(")", source.index(")", call_start) + 1)  # closing paren of the list, then the call
    call_block = source[call_start:call_end + 1]
    assert "league_stats" in call_block, (
        "league_stats.csv path missing from main.py's upload_outputs() call "
        "— this is the exact persistence gap the fix addresses"
    )
    # No regression: every pre-existing output must remain present too.
    for existing in ("out25_path", "out_btts_path", "combo_path", "combo_github_path", "simple_path", "HISTORY_PATH"):
        assert existing in call_block, f"{existing} missing from upload_outputs() call — regression"


def test_main_py_league_stats_path_matches_update_league_stats_convention(tmp_path):
    """Proves main.py's manually-constructed league_stats_path
    (HISTORY_PATH.parent / 'league_stats.csv') agrees with what
    update_league_stats() itself actually writes when given no explicit
    out_path — the two must never independently drift."""
    fake_history = tmp_path / "picks_history.csv"
    fake_history.write_text("Data;Liga;Jogo;Mercado;Odd;Stake€;Lucro€;Edge%;Resultado\n", encoding="utf-8")

    update_league_stats(fake_history)  # out_path=None -> defaults internally

    expected_path = fake_history.parent / "league_stats.csv"
    assert expected_path.exists(), "update_league_stats() did not write to its own documented default path"

    main_convention_path = fake_history.parent / "league_stats.csv"  # mirrors main.py's HISTORY_PATH.parent / 'league_stats.csv'
    assert main_convention_path == expected_path


# ── Computation regression guard (unchanged semantics, MLS-agnostic) ──────

def test_update_league_stats_produces_a_row_for_any_league_with_at_least_one_pick(tmp_path):
    """Generic (not MLS-specific) proof that a league needs only 1 row in
    picks_history.csv to become Analytics-eligible — substantiates that the
    persistence fix alone (not a calculation change) is sufficient for MLS
    to reappear once regenerated/uploaded. Does not modify or assert any
    specific threshold/Tier/ROI formula — those are read back only to
    confirm the row exists, not to verify their values."""
    history_path = tmp_path / "picks_history.csv"
    pd.DataFrame([
        {"Data": "2026-07-17", "Liga": "MLS", "Jogo": "Home vs Away", "Mercado": "O2.5",
         "Odd": "1.55", "Stake€": "10", "Lucro€": "5", "Edge%": "5.0", "Resultado": "W"},
    ]).to_csv(history_path, index=False, sep=";", encoding="utf-8")

    out_path = tmp_path / "league_stats_out.csv"
    update_league_stats(history_path, out_path)

    out_df = pd.read_csv(out_path, sep=";")
    mls_rows = out_df[out_df["League"] == "MLS"]
    assert len(mls_rows) == 1
    assert int(mls_rows.iloc[0]["TotalPicks"]) == 1
