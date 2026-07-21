"""
tests/test_void_policy.py

Regression coverage for the postponed/cancelled/abandoned/missing-fixture
automatic-void policy (see docs/09_Architecture_Decisions.md ADR-017 and
docs/05_Known_Issues.md).

Background: an approved bet could remain unresolved (and financially exposed)
indefinitely when its fixture was postponed, cancelled, abandoned, or became
undiscoverable through the normal settlement lookup (e.g. rescheduled far
enough from its original date) — the concrete case that prompted this policy
was Chicago Fire vs Vancouver Whitecaps (2026-07-17), never found by
API-Football near its stored kickoff. Two safeguards close this gap:
  1. AUTOMATIC voiding — an explicit non-played provider status (PST/CANC/
     ABD/SUSP/INT) after POSTPONED_VOID_AFTER_HOURS (default 48h), or a
     persistently undiscoverable fixture after MISSING_FIXTURE_VOID_AFTER_HOURS
     (default 72h) with repeated-attempt evidence and a bounded final
     rediscovery search — settles the bet as P (push/void), never W/L.
  2. MANUAL voiding — a frontend-only fallback (Live Center), out of scope
     for this Python suite; see the scratchpad Playwright script referenced
     in the session's final report.

Run with:  python -m pytest tests/test_void_policy.py -v
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import update_results as ur


# ── Helpers ─────────────────────────────────────────────────────────────────

def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def make_row_df(
    liga="MLS",
    jogo="Home Team vs Away Team",
    mercado="O2.5",
    odd="1.55",
    stake="10",
    kickoff_dt: datetime | None = None,
    missing_attempts: str = "",
    resultado: str = "",
    apostada: str = "",
    stake_real: str = "",
    odd_real: str = "",
):
    row = {c: "" for c in ur.CSV_COLUMNS}
    kickoff_dt = kickoff_dt or (datetime.now(timezone.utc) - timedelta(hours=50))
    row.update({
        "Data": kickoff_dt.date().isoformat(),
        "Liga": liga,
        "Jogo": jogo,
        "Mercado": mercado,
        "Odd": odd,
        "Stake€": stake,
        "KickoffUTC": _iso(kickoff_dt),
        "MissingAttempts": missing_attempts,
        "Resultado": resultado,
        "Apostada": apostada,
        "StakeReal€": stake_real,
        "OddReal": odd_real,
    })
    return pd.DataFrame([row]), kickoff_dt


def make_af_fixture(status: str, home: str, away: str, kickoff_dt: datetime,
                     home_goals=None, away_goals=None):
    return {
        "fixture": {"status": {"short": status}, "date": _iso(kickoff_dt)},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "goals": {"home": home_goals, "away": away_goals},
    }


def make_af_fetch_mock(date_to_fixtures: dict):
    """date_to_fixtures: {date_str: [fixtures] | None}. None simulates a
    provider error (fetch failed, not a genuine empty/no-match result).
    Any date not present in the dict returns a genuine empty list."""
    def _fake_fetch(league_code, date_str, shared_state):
        if date_str in date_to_fixtures:
            val = date_to_fixtures[date_str]
            if val is None:
                return None, "PROVIDER_ERROR"
            return val, ""
        return [], ""
    return _fake_fetch


def run_settlement(monkeypatch, df, date_to_fixtures):
    monkeypatch.setattr(ur, "fetch_api_football_fixtures_for_league_date", make_af_fetch_mock(date_to_fixtures))
    shared_state = ur.make_shared_runtime_state()
    out_df, updated, already_done, ignored = ur.update_dataframe(df, "test", shared_state)
    return out_df, updated, already_done, ignored


# ── 1-3: unaffected normal settlement (FT/AET/PEN) ─────────────────────────

def test_ft_still_settles_normally(monkeypatch):
    df, kickoff = make_row_df(kickoff_dt=datetime.now(timezone.utc) - timedelta(hours=5))
    date_str = kickoff.date().isoformat()
    fx = make_af_fixture("FT", "Home Team", "Away Team", kickoff, 2, 1)
    out, updated, _, _ = run_settlement(monkeypatch, df, {date_str: [fx]})
    assert out.iloc[0]["Resultado"] == "W"  # O2.5, total=3
    assert out.iloc[0]["SettlementReason"] == ""
    assert updated == 1


def test_aet_still_settles_normally(monkeypatch):
    df, kickoff = make_row_df(mercado="O1.5", kickoff_dt=datetime.now(timezone.utc) - timedelta(hours=5))
    date_str = kickoff.date().isoformat()
    fx = make_af_fixture("AET", "Home Team", "Away Team", kickoff, 1, 0)
    out, updated, _, _ = run_settlement(monkeypatch, df, {date_str: [fx]})
    assert out.iloc[0]["Resultado"] == "L"  # O1.5, total=1 -> L
    assert updated == 1


def test_pen_still_settles_normally(monkeypatch):
    df, kickoff = make_row_df(mercado="BTTS", kickoff_dt=datetime.now(timezone.utc) - timedelta(hours=5))
    date_str = kickoff.date().isoformat()
    fx = make_af_fixture("PEN", "Home Team", "Away Team", kickoff, 1, 1)
    out, updated, _, _ = run_settlement(monkeypatch, df, {date_str: [fx]})
    assert out.iloc[0]["Resultado"] == "W"  # BTTS, both scored
    assert updated == 1


# ── 4-8: explicit non-played status timeout ────────────────────────────────

def test_postponed_before_48h_remains_unresolved(monkeypatch):
    kickoff = datetime.now(timezone.utc) - timedelta(hours=30)
    df, _ = make_row_df(kickoff_dt=kickoff)
    date_str = kickoff.date().isoformat()
    fx = make_af_fixture("PST", "Home Team", "Away Team", kickoff)
    out, updated, _, ignored = run_settlement(monkeypatch, df, {date_str: [fx]})
    assert out.iloc[0]["Resultado"] == ""
    assert out.iloc[0]["SettlementReason"] == ""
    assert updated == 0
    assert ignored == 1


def test_postponed_after_48h_becomes_p(monkeypatch):
    kickoff = datetime.now(timezone.utc) - timedelta(hours=49)
    df, _ = make_row_df(kickoff_dt=kickoff, stake="10", odd="1.55")
    date_str = kickoff.date().isoformat()
    fx = make_af_fixture("PST", "Home Team", "Away Team", kickoff)
    out, updated, _, _ = run_settlement(monkeypatch, df, {date_str: [fx]})
    assert out.iloc[0]["Resultado"] == "P"
    assert out.iloc[0]["SettlementReason"] == "postponed_timeout"
    assert out.iloc[0]["Placar"] == ""
    assert float(out.iloc[0]["Lucro€"]) == 0.0
    assert updated == 1


def test_cancelled_after_threshold_becomes_p(monkeypatch):
    kickoff = datetime.now(timezone.utc) - timedelta(hours=49)
    df, _ = make_row_df(kickoff_dt=kickoff)
    date_str = kickoff.date().isoformat()
    fx = make_af_fixture("CANC", "Home Team", "Away Team", kickoff)
    out, updated, _, _ = run_settlement(monkeypatch, df, {date_str: [fx]})
    assert out.iloc[0]["Resultado"] == "P"
    assert out.iloc[0]["SettlementReason"] == "cancelled_timeout"


def test_abandoned_after_threshold_becomes_p(monkeypatch):
    kickoff = datetime.now(timezone.utc) - timedelta(hours=49)
    df, _ = make_row_df(kickoff_dt=kickoff)
    date_str = kickoff.date().isoformat()
    fx = make_af_fixture("ABD", "Home Team", "Away Team", kickoff)
    out, updated, _, _ = run_settlement(monkeypatch, df, {date_str: [fx]})
    assert out.iloc[0]["Resultado"] == "P"
    assert out.iloc[0]["SettlementReason"] == "abandoned_timeout"


def test_suspended_interrupted_after_48h_remains_unresolved(monkeypatch):
    # Pre-commit safety audit correction: an earlier version of this policy
    # grouped SUSP/INT with PST/CANC/ABD under the same 48h explicit-status
    # timeout. The audit found this unsafe — a match interrupted Monday and still
    # reporting INT/SUSP on Wednesday (48h later) may legitimately resume
    # and finish Friday; voiding it at the 48h mark would incorrectly void a
    # wager whose match is still going to produce a real result. SUSP/INT
    # must NOT auto-void via the explicit-status pathway at any age — see
    # ADR-017's corrected classification matrix.
    kickoff = datetime.now(timezone.utc) - timedelta(hours=49)
    for status in ("SUSP", "INT"):
        df, _ = make_row_df(kickoff_dt=kickoff)
        date_str = kickoff.date().isoformat()
        fx = make_af_fixture(status, "Home Team", "Away Team", kickoff)
        out, updated, _, ignored = run_settlement(monkeypatch, df, {date_str: [fx]})
        assert out.iloc[0]["Resultado"] == "", status
        assert out.iloc[0]["SettlementReason"] == "", status
        assert updated == 0, status
        assert ignored == 1, status


def test_fd_suspended_after_48h_remains_unresolved(monkeypatch):
    # Same correction, football-data.org side (SUSPENDED is FD's only
    # suspended/interrupted-equivalent status). Must use a football-data.org
    # league (MLS has no FD coverage at all and would route straight to AF).
    kickoff = datetime.now(timezone.utc) - timedelta(hours=49)
    df, _ = make_row_df(liga="Premier League", kickoff_dt=kickoff)
    date_str = kickoff.date().isoformat()
    fx = {
        "utcDate": _iso(kickoff),
        "status": "SUSPENDED",
        "homeTeam": {"name": "Home Team"},
        "awayTeam": {"name": "Away Team"},
        "score": {"fullTime": {"home": None, "away": None}},
    }
    monkeypatch.setattr(ur, "fetch_matches_for_league_date", lambda league_code, date, shared_state: [fx])
    shared_state = ur.make_shared_runtime_state()
    out, updated, _, ignored = ur.update_dataframe(df, "test", shared_state)
    assert out.iloc[0]["Resultado"] == ""
    assert out.iloc[0]["SettlementReason"] == ""
    assert updated == 0
    assert ignored == 1


def test_suspended_interrupted_very_old_fixture_still_never_auto_voids(monkeypatch):
    # Age alone must never be sufficient — even a SUSP/INT fixture several
    # days old (well past every configured threshold) stays unresolved via
    # the automatic path. This is the crucial safety rule applied to SUSP/INT
    # specifically, not just to IN_PROGRESS/SCHEDULED_UNKNOWN.
    kickoff = datetime.now(timezone.utc) - timedelta(days=10)
    for status in ("SUSP", "INT"):
        df, _ = make_row_df(kickoff_dt=kickoff)
        date_str = kickoff.date().isoformat()
        fx = make_af_fixture(status, "Home Team", "Away Team", kickoff)
        out, updated, _, _ = run_settlement(monkeypatch, df, {date_str: [fx]})
        assert out.iloc[0]["Resultado"] == "", status
        assert updated == 0, status


def test_suspended_interrupted_classification_falls_through_to_scheduled_unknown():
    # Confirms the "reuse the existing safe bucket" implementation choice
    # (per the safety audit) rather than a new dedicated classification branch.
    assert ur.classify_af_status("SUSP") == "SCHEDULED_UNKNOWN"
    assert ur.classify_af_status("INT") == "SCHEDULED_UNKNOWN"
    assert ur.classify_fd_status("SUSPENDED") == "SCHEDULED_UNKNOWN"
    # And are documented, not silently absent.
    assert "SUSP" in ur.AF_SUSPENDED_INTERRUPTED_STATUS
    assert "INT" in ur.AF_SUSPENDED_INTERRUPTED_STATUS
    assert "SUSPENDED" in ur.FD_SUSPENDED_INTERRUPTED_STATUS
    # And are no longer present in the auto-void-eligible sets or reason maps.
    assert "SUSP" not in ur.AF_NON_PLAYED_STATUS
    assert "INT" not in ur.AF_NON_PLAYED_STATUS
    assert "SUSPENDED" not in ur.FD_NON_PLAYED_STATUS
    assert "SUSP" not in ur.AF_VOID_REASON_BY_STATUS
    assert "INT" not in ur.AF_VOID_REASON_BY_STATUS
    assert "SUSPENDED" not in ur.FD_VOID_REASON_BY_STATUS


def test_in_progress_never_voids_regardless_of_age(monkeypatch):
    # The crucial safety rule (Part 2): "not FT" alone must never be enough.
    kickoff = datetime.now(timezone.utc) - timedelta(hours=200)
    df, _ = make_row_df(kickoff_dt=kickoff)
    date_str = kickoff.date().isoformat()
    fx = make_af_fixture("2H", "Home Team", "Away Team", kickoff)
    out, updated, _, ignored = run_settlement(monkeypatch, df, {date_str: [fx]})
    assert out.iloc[0]["Resultado"] == ""
    assert updated == 0
    assert ignored == 1


def test_scheduled_unknown_never_voids_regardless_of_age(monkeypatch):
    kickoff = datetime.now(timezone.utc) - timedelta(hours=200)
    df, _ = make_row_df(kickoff_dt=kickoff)
    date_str = kickoff.date().isoformat()
    fx = make_af_fixture("NS", "Home Team", "Away Team", kickoff)
    out, updated, _, ignored = run_settlement(monkeypatch, df, {date_str: [fx]})
    assert out.iloc[0]["Resultado"] == ""
    assert updated == 0


# ── 9-12: persistent missing-fixture safeguards ────────────────────────────

def test_single_missing_attempt_does_not_void(monkeypatch):
    # Age already past 72h, but this is the FIRST genuine NO_MATCH — the
    # attempts-evidence gate must block voiding regardless of age.
    kickoff = datetime.now(timezone.utc) - timedelta(hours=80)
    df, _ = make_row_df(kickoff_dt=kickoff, missing_attempts="")
    out, updated, _, _ = run_settlement(monkeypatch, df, {})
    assert out.iloc[0]["Resultado"] == ""
    assert out.iloc[0]["MissingAttempts"] == "1"
    assert updated == 0


def test_missing_fixture_before_72h_does_not_void_even_with_attempts(monkeypatch):
    kickoff = datetime.now(timezone.utc) - timedelta(hours=50)  # >48h, <72h
    df, _ = make_row_df(kickoff_dt=kickoff, missing_attempts="5")
    out, updated, _, _ = run_settlement(monkeypatch, df, {})
    assert out.iloc[0]["Resultado"] == ""
    assert out.iloc[0]["MissingAttempts"] == "6"
    assert updated == 0


def test_persistent_missing_fixture_after_72h_with_evidence_voids(monkeypatch):
    kickoff = datetime.now(timezone.utc) - timedelta(hours=80)
    df, _ = make_row_df(kickoff_dt=kickoff, missing_attempts="2")  # -> 3 after increment
    # Nothing anywhere — narrow fetch, date-1 fallback, and the entire
    # rediscovery window all come back empty.
    out, updated, _, _ = run_settlement(monkeypatch, df, {})
    assert out.iloc[0]["Resultado"] == "P"
    assert out.iloc[0]["SettlementReason"] == "missing_fixture_timeout"
    assert out.iloc[0]["MissingAttempts"] == "3"
    assert float(out.iloc[0]["Lucro€"]) == 0.0
    assert updated == 1


def test_provider_outage_is_never_counted_as_missing_evidence(monkeypatch):
    kickoff = datetime.now(timezone.utc) - timedelta(hours=80)
    date_str = kickoff.date().isoformat()
    prev_date_str = (kickoff.date() - timedelta(days=1)).isoformat()
    df, _ = make_row_df(kickoff_dt=kickoff, missing_attempts="2")
    # Both the narrow date and its date-1 fallback fail as a provider error
    # (None), never a genuine empty/no-match result.
    out, updated, _, _ = run_settlement(monkeypatch, df, {date_str: None, prev_date_str: None})
    assert out.iloc[0]["Resultado"] == ""
    assert out.iloc[0]["MissingAttempts"] == "2"  # unchanged — not incremented
    assert updated == 0


# ── 13: rescheduled-fixture rediscovery ────────────────────────────────────

def test_rediscovery_finds_not_finished_fixture_prevents_void(monkeypatch):
    kickoff = datetime.now(timezone.utc) - timedelta(hours=80)
    df, _ = make_row_df(kickoff_dt=kickoff, missing_attempts="2")
    rescheduled_date = kickoff.date() + timedelta(days=5)
    fx = make_af_fixture("NS", "Home Team", "Away Team", kickoff)
    out, updated, _, _ = run_settlement(monkeypatch, df, {rescheduled_date.isoformat(): [fx]})
    assert out.iloc[0]["Resultado"] == ""
    assert out.iloc[0]["MissingAttempts"] == "0"  # reset — no longer "missing"
    assert updated == 0


def test_rediscovery_finds_finished_fixture_settles_normally(monkeypatch):
    kickoff = datetime.now(timezone.utc) - timedelta(hours=80)
    df, _ = make_row_df(kickoff_dt=kickoff, missing_attempts="2", mercado="O2.5")
    rescheduled_date = kickoff.date() + timedelta(days=5)
    fx = make_af_fixture("FT", "Home Team", "Away Team", kickoff, 2, 1)
    out, updated, _, _ = run_settlement(monkeypatch, df, {rescheduled_date.isoformat(): [fx]})
    assert out.iloc[0]["Resultado"] == "W"
    assert out.iloc[0]["Placar"] == "2-1"
    assert out.iloc[0]["SettlementReason"] == ""  # a genuine result, not a void
    assert out.iloc[0]["MissingAttempts"] == "0"
    assert updated == 1


def test_rediscovery_is_bounded_and_forward_only(monkeypatch):
    # A fixture 20 days after the original kickoff is outside the bounded
    # +2..+14 day rediscovery window and must never be found.
    kickoff = datetime.now(timezone.utc) - timedelta(hours=80)
    df, _ = make_row_df(kickoff_dt=kickoff, missing_attempts="2")
    too_far_date = kickoff.date() + timedelta(days=20)
    fx = make_af_fixture("NS", "Home Team", "Away Team", kickoff)
    out, updated, _, _ = run_settlement(monkeypatch, df, {too_far_date.isoformat(): [fx]})
    # Nothing found within the bounded window -> voided, not "kept waiting".
    assert out.iloc[0]["Resultado"] == "P"
    assert out.iloc[0]["SettlementReason"] == "missing_fixture_timeout"


# ── 14-15: bot/manual share the exact same void semantics (ADR-002/009) ────

def test_bot_and_manual_void_produce_identical_financial_result(monkeypatch):
    kickoff = datetime.now(timezone.utc) - timedelta(hours=49)
    date_str = kickoff.date().isoformat()
    fx = make_af_fixture("PST", "Home Team", "Away Team", kickoff)
    monkeypatch.setattr(ur, "fetch_api_football_fixtures_for_league_date", make_af_fetch_mock({date_str: [fx]}))
    shared_state = ur.make_shared_runtime_state()

    bot_df, _ = make_row_df(kickoff_dt=kickoff, stake="10", odd="1.55")
    bot_out, _, _, _ = ur.update_dataframe(bot_df, "history", shared_state)

    manual_bets = [{
        "data": kickoff.date().isoformat(), "liga": "mls",
        "jogo": "Home Team vs Away Team", "mercado": "Over 2.5",
        "odd": "1.55", "stake": "10", "resultado": "",
        "kickoffUTC": _iso(kickoff),
    }]
    manual_df = ur.manual_bets_to_settlement_df(manual_bets)
    manual_out, _, _, _ = ur.update_dataframe(manual_df, "manual", shared_state)
    newly_settled, evidence_changed = ur.apply_df_results_to_manual_bets(manual_bets, manual_out)

    assert bot_out.iloc[0]["Resultado"] == "P"
    assert manual_bets[0]["resultado"] == "P"
    assert manual_bets[0]["lucro"] == 0.0
    assert manual_bets[0]["settlementReason"] == "postponed_timeout"
    assert newly_settled == 1


# ── Manual-bet MissingAttempts evidence bridge survives across runs ────────

def test_manual_bet_missing_attempts_persist_across_runs_even_unsettled(monkeypatch):
    kickoff = datetime.now(timezone.utc) - timedelta(hours=50)
    manual_bets = [{
        "data": kickoff.date().isoformat(), "liga": "mls",
        "jogo": "Home Team vs Away Team", "mercado": "Over 2.5",
        "odd": "1.55", "stake": "10", "resultado": "",
        "kickoffUTC": _iso(kickoff), "missingAttempts": 2,
    }]
    monkeypatch.setattr(ur, "fetch_api_football_fixtures_for_league_date", make_af_fetch_mock({}))
    shared_state = ur.make_shared_runtime_state()
    manual_df = ur.manual_bets_to_settlement_df(manual_bets)
    assert manual_df.iloc[0]["MissingAttempts"] == "2"
    manual_out, _, _, _ = ur.update_dataframe(manual_df, "manual", shared_state)
    newly_settled, evidence_changed = ur.apply_df_results_to_manual_bets(manual_bets, manual_out)

    assert manual_bets[0]["resultado"] == ""  # still unresolved (<72h)
    assert manual_bets[0]["missingAttempts"] == 3
    assert newly_settled == 0
    assert evidence_changed == 1  # caller must still save cloud_state.json


# ── Existing manual-result bridge / CSV-wins precedence (ADR-015) untouched ─

def test_market_result_never_auto_generates_p():
    # ADR-017 explicitly reuses, and must never bypass, market_result()'s
    # existing invariant that P is never produced by ordinary score-based
    # settlement — only void_result_row() writes P, and only for the two
    # policy-gated reasons this suite exercises above.
    assert ur.market_result("O2.5", 2, 1) in {"W", "L"}
    assert ur.market_result("O2.5", 0, 0) == "L"
    assert ur.market_result("BTTS", 1, 1) == "W"


# ── Config: get_void_policy() defensive validation ─────────────────────────

def test_get_void_policy_defaults_when_missing():
    from src.config import get_void_policy, DEFAULT_POSTPONED_VOID_AFTER_HOURS
    policy = get_void_policy({})
    assert policy["postponed_void_after_hours"] == DEFAULT_POSTPONED_VOID_AFTER_HOURS


def test_get_void_policy_rejects_invalid_values():
    from src.config import get_void_policy, DEFAULT_MISSING_FIXTURE_VOID_AFTER_HOURS
    cfg = {"settlement": {"void_policy": {
        "missing_fixture_void_after_hours": -5,
        "postponed_void_after_hours": "not-a-number",
    }}}
    policy = get_void_policy(cfg)
    assert policy["missing_fixture_void_after_hours"] == DEFAULT_MISSING_FIXTURE_VOID_AFTER_HOURS
    assert policy["postponed_void_after_hours"] == 48.0


def test_get_void_policy_accepts_valid_override():
    from src.config import get_void_policy
    cfg = {"settlement": {"void_policy": {"manual_void_available_after_hours": 12}}}
    policy = get_void_policy(cfg)
    assert policy["manual_void_available_after_hours"] == 12.0


# ── CSV schema: additive columns round-trip cleanly (Part 12/16) ──────────

def test_ensure_columns_adds_new_fields_to_legacy_rows():
    legacy_df = pd.DataFrame([{
        "Data": "2026-01-01", "Liga": "MLS", "Jogo": "A vs B", "Mercado": "O2.5",
        "Odd": "1.5", "Stake€": "10", "Resultado": "W", "Lucro€": "5",
    }])
    out = ur.ensure_columns(legacy_df)
    assert out.iloc[0]["SettlementReason"] == ""
    assert out.iloc[0]["MissingAttempts"] == ""
    assert list(out.columns) == ur.CSV_COLUMNS


def test_sync_daily_from_history_propagates_settlement_reason():
    history_df = pd.DataFrame([{
        "Data": "2026-01-01", "Liga": "MLS", "Jogo": "A vs B", "Mercado": "O2.5",
        "Odd": "1.5", "Stake€": "10", "Resultado": "P", "Lucro€": "0.0",
        "SettlementReason": "postponed_timeout",
    }])
    daily_df = pd.DataFrame([{
        "Data": "2026-01-01", "Liga": "MLS", "Jogo": "A vs B", "Mercado": "O2.5",
        "Odd": "1.5", "Stake€": "10", "Resultado": "", "Lucro€": "",
    }])
    out, synced = ur.sync_daily_from_history(daily_df, history_df)
    assert out.iloc[0]["Resultado"] == "P"
    assert out.iloc[0]["SettlementReason"] == "postponed_timeout"
    assert synced == 1
