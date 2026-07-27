"""
tests/test_fixture_id.py

Unit coverage for the fixture-only identity helpers added to src/history.py
for the Policy A fixture-level market lock (ADR-018):

    fixture_id_from_parts(date, liga, jogo)
    fixture_id_from_simple(row)      -- Data/Liga/Jogo schema (history/simple rows)
    fixture_id_from_candidate(row)   -- Date/LeagueName/HomeTeam/AwayTeam schema
                                         (main.py's in-memory combo_pre rows)

These three are the ONLY fixture-identity implementation in the codebase --
this suite proves normalization behaviour and, critically, that the
candidate-side and history-side constructors agree on the same fixture,
which is what allows apply_fixture_market_lock() to compare a freshly
generated candidate row against an already-persisted history row correctly.

Run with:  python -m pytest tests/test_fixture_id.py -v
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.history import (
    fixture_id_from_candidate,
    fixture_id_from_parts,
    fixture_id_from_simple,
    history_pick_id_from_simple,
)


# ── fixture_id_from_parts(): basic shape ───────────────────────────────────

def test_fixture_id_from_parts_joins_three_fields_with_pipe():
    assert fixture_id_from_parts("2026-08-01", "Premier League", "Team A vs Team B") == \
        "2026-08-01|Premier League|Team A vs Team B"


def test_fixture_id_from_parts_strips_each_field():
    assert fixture_id_from_parts("  2026-08-01 ", " Premier League ", " Team A vs Team B ") == \
        "2026-08-01|Premier League|Team A vs Team B"


def test_fixture_id_from_parts_deterministic_same_input_same_output():
    a = fixture_id_from_parts("2026-08-01", "MLS", "Chicago Fire vs Vancouver Whitecaps")
    b = fixture_id_from_parts("2026-08-01", "MLS", "Chicago Fire vs Vancouver Whitecaps")
    assert a == b


# ── Market is excluded from the fixture id ─────────────────────────────────

def test_fixture_id_from_simple_excludes_market():
    row_o25 = {"Data": "2026-08-01", "Liga": "MLS", "Jogo": "A vs B", "Mercado": "O2.5"}
    row_btts = {"Data": "2026-08-01", "Liga": "MLS", "Jogo": "A vs B", "Mercado": "BTTS"}
    assert fixture_id_from_simple(row_o25) == fixture_id_from_simple(row_btts), (
        "Same fixture, different Market, must resolve to the SAME fixture id — "
        "this is the entire point of the lock: it must see O2.5 and BTTS "
        "candidates for one fixture as the same fixture."
    )


def test_history_pick_id_from_simple_still_includes_market():
    # The pre-existing, market-specific identity used by merge_into_history()
    # must be UNCHANGED by this refactor (it is built on top of
    # fixture_id_from_simple(), not replaced by it).
    row_o25 = {"Data": "2026-08-01", "Liga": "MLS", "Jogo": "A vs B", "Mercado": "O2.5"}
    row_btts = {"Data": "2026-08-01", "Liga": "MLS", "Jogo": "A vs B", "Mercado": "BTTS"}
    assert history_pick_id_from_simple(row_o25) != history_pick_id_from_simple(row_btts)
    assert history_pick_id_from_simple(row_o25) == "2026-08-01|MLS|A vs B|O2.5"
    assert history_pick_id_from_simple(row_btts) == "2026-08-01|MLS|A vs B|BTTS"


# ── Candidate-side vs. history-side equivalence ─────────────────────────────

def test_fixture_id_from_candidate_matches_fixture_id_from_simple_for_same_fixture():
    """This is the load-bearing equivalence: a freshly generated candidate row
    (main.py's combo_pre schema) must resolve to the exact same fixture id as
    the history row it will eventually become once persisted by
    save_all_outputs()/persist_history() — otherwise the lock could never
    recognise its own previously-persisted picks."""
    candidate = {
        "Date": "2026-08-01",
        "League": "mls",
        "LeagueName": "MLS",
        "HomeTeam": "Chicago Fire",
        "AwayTeam": "Vancouver Whitecaps",
        "Market": "O2.5",
    }
    # Exactly how save_all_outputs() derives Data/Liga/Jogo from a candidate row.
    history_row = {
        "Data": candidate["Date"],
        "Liga": candidate["LeagueName"],
        "Jogo": f"{candidate['HomeTeam']} vs {candidate['AwayTeam']}",
        "Mercado": candidate["Market"],
    }
    assert fixture_id_from_candidate(candidate) == fixture_id_from_simple(history_row)


def test_fixture_id_from_candidate_uses_league_name_not_internal_key():
    # "League" (internal registry key, e.g. "mls") must NOT be used for the
    # fixture id — history's "Liga" column holds the display name ("MLS"),
    # never the internal key. Using the wrong field would make the lock never
    # recognise its own history rows.
    candidate = {
        "Date": "2026-08-01", "League": "mls", "LeagueName": "MLS",
        "HomeTeam": "A", "AwayTeam": "B", "Market": "O2.5",
    }
    assert fixture_id_from_candidate(candidate) == "2026-08-01|MLS|A vs B"
    assert "mls" not in fixture_id_from_candidate(candidate)


# ── MLS vs MLS Next Pro must never collapse (ADR-004) ───────────────────────

def test_mls_and_mls_next_pro_never_collapse_to_the_same_fixture_id():
    mls_candidate = {
        "Date": "2026-08-01", "League": "mls", "LeagueName": "MLS",
        "HomeTeam": "Team X", "AwayTeam": "Team Y", "Market": "O2.5",
    }
    mls_np_candidate = {
        "Date": "2026-08-01", "League": "mls_next_pro", "LeagueName": "MLS Next Pro",
        "HomeTeam": "Team X", "AwayTeam": "Team Y", "Market": "O2.5",
    }
    assert fixture_id_from_candidate(mls_candidate) != fixture_id_from_candidate(mls_np_candidate)


def test_mls_and_mls_next_pro_distinct_even_with_identical_team_names_and_date():
    # Deliberately identical Date/HomeTeam/AwayTeam, only League differs --
    # proves separation comes entirely from the League component, not from
    # any incidental team-name difference.
    a = fixture_id_from_parts("2026-08-01", "MLS", "Home vs Away")
    b = fixture_id_from_parts("2026-08-01", "MLS Next Pro", "Home vs Away")
    assert a != b


# ── No fuzzy matching: whitespace/casing differences are NOT normalized ────
# (deliberate -- see docs/09_Architecture_Decisions.md ADR-018 "Normalization
# safety": the fixture id reuses the exact same unnormalized HomeTeam/AwayTeam
# concatenation save_all_outputs() already uses everywhere else in this
# codebase, so it never diverges from what dedupe_correlated_picks() or
# merge_into_history() already treat as "the same fixture".)

def test_fixture_id_does_not_fuzzy_match_different_casing():
    a = fixture_id_from_parts("2026-08-01", "MLS", "team a vs team b")
    b = fixture_id_from_parts("2026-08-01", "MLS", "Team A vs Team B")
    assert a != b, "Casing differences must NOT be silently normalized (no fuzzy matching)"


def test_fixture_id_does_not_fuzzy_match_internal_whitespace_variance():
    a = fixture_id_from_parts("2026-08-01", "MLS", "Team A vs Team B")
    b = fixture_id_from_parts("2026-08-01", "MLS", "Team A  vs Team B")  # double space
    assert a != b, "Internal whitespace differences must NOT be silently normalized"
