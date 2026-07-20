"""
tests/test_mls_league_routing.py

Regression coverage for MLS and MLS Next Pro as two independent, first-class
leagues.

Background: src/league_registry.py's "mls" entry was hardcoded to API-Football
league ID 909 (MLS Next Pro) between Phase 26.12 and this fix, while
config.json's api_football.league_ids kept the correct senior-MLS ID (253).
Fixture generation (fetch_oddsapi_fixtures.py) used config.json and therefore
found senior MLS fixtures once the season resumed; settlement (update_results.py)
used the registry and kept querying MLS Next Pro, so those fixtures could never
be found. Generating MLS Next Pro picks was always intentional — the defect was
never that MLS Next Pro fixtures were generated, only that they were obtained
through a silent fallback from MLS and stored under MLS's identity. The fix
gives both competitions their own canonical code and provider ID, both actively
configured for generation, neither ever substituting for the other. See
docs/05_Known_Issues.md and the ADR-004 update for full detail.

Run with:  python -m pytest tests/test_mls_league_routing.py -v
"""
import json
import sys
from pathlib import Path

# Make project root importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.league_registry import (
    REGISTRY_BY_KEY,
    LEAGUE_CODE_MAP,
    API_FOOTBALL_FALLBACK_COMPETITIONS,
    AF_SEASON_MODELS,
)
import update_results


SENIOR_MLS_AF_ID = 253
MLS_NEXT_PRO_AF_ID = 909


# ── Registry: senior MLS and MLS Next Pro are distinct, correctly-IDed entries ─

def test_registry_mls_routes_to_senior_id():
    entry = REGISTRY_BY_KEY["mls"]
    assert entry.af_id == SENIOR_MLS_AF_ID
    assert entry.af_name != "MLS Next Pro"
    assert entry.name == "MLS"

def test_registry_mls_next_pro_is_distinct_entry():
    entry = REGISTRY_BY_KEY["mls_next_pro"]
    assert entry.af_id == MLS_NEXT_PRO_AF_ID
    assert entry.name == "MLS Next Pro"

def test_registry_mls_and_mls_next_pro_use_different_af_ids():
    assert REGISTRY_BY_KEY["mls"].af_id != REGISTRY_BY_KEY["mls_next_pro"].af_id


# ── Derived structures consumed by update_dataframe() ─────────────────────────

def test_league_code_map_distinguishes_mls_and_mls_next_pro():
    assert LEAGUE_CODE_MAP["MLS"] == "mls"
    assert LEAGUE_CODE_MAP["MLS Next Pro"] == "mls_next_pro"
    assert LEAGUE_CODE_MAP["MLS"] != LEAGUE_CODE_MAP["MLS Next Pro"]

def test_api_football_fallback_competitions_mls_is_senior():
    assert API_FOOTBALL_FALLBACK_COMPETITIONS["mls"]["af_id"] == SENIOR_MLS_AF_ID

def test_api_football_fallback_competitions_mls_next_pro():
    assert API_FOOTBALL_FALLBACK_COMPETITIONS["mls_next_pro"]["af_id"] == MLS_NEXT_PRO_AF_ID

def test_af_season_models_has_both_ids_as_calendar():
    assert AF_SEASON_MODELS[SENIOR_MLS_AF_ID] == "calendar"
    assert AF_SEASON_MODELS[MLS_NEXT_PRO_AF_ID] == "calendar"


# ── get_api_football_league_id(): the actual function settlement calls ────────

def test_get_api_football_league_id_resolves_senior_mls(monkeypatch):
    monkeypatch.setattr(update_results, "API_FOOTBALL_KEY", "dummy-test-key")
    shared_state = update_results.make_shared_runtime_state()
    league_id = update_results.get_api_football_league_id("mls", "2026-07-17", shared_state)
    assert league_id == SENIOR_MLS_AF_ID

def test_get_api_football_league_id_resolves_mls_next_pro(monkeypatch):
    monkeypatch.setattr(update_results, "API_FOOTBALL_KEY", "dummy-test-key")
    shared_state = update_results.make_shared_runtime_state()
    league_id = update_results.get_api_football_league_id("mls_next_pro", "2026-06-21", shared_state)
    assert league_id == MLS_NEXT_PRO_AF_ID


# ── Bot picks and manual bets route identically (ADR-002/ADR-009) ─────────────

def test_bot_pick_and_manual_bet_mls_row_share_same_routing_code():
    # Bot picks store the display name directly in the "Liga" CSV column.
    bot_liga_code = LEAGUE_CODE_MAP["MLS"]

    # Manual bets are converted through the same bridge used by settlement.
    manual_bets = [{
        "data": "2026-07-17", "liga": "mls", "jogo": "Chicago Fire vs Vancouver Whitecaps",
        "mercado": "Over 2.5", "odd": "1.53", "stake": "1", "resultado": "",
        "kickoffUTC": "2026-07-17T01:30:00+01:00",
    }]
    manual_df = update_results.manual_bets_to_settlement_df(manual_bets)
    manual_liga_display = manual_df.iloc[0]["Liga"]
    manual_liga_code = LEAGUE_CODE_MAP[manual_liga_display]

    assert bot_liga_code == manual_liga_code == "mls"
    assert API_FOOTBALL_FALLBACK_COMPETITIONS[manual_liga_code]["af_id"] == SENIOR_MLS_AF_ID

def test_manual_bet_leagueid_field_is_not_consumed_by_settlement_routing():
    # A manual bet's own persisted `leagueId` (e.g. 253, captured at creation
    # time for display/audit) must have no bearing on settlement routing —
    # routing is driven exclusively by the registry via the "Liga" string, so
    # that bot and manual bets can never silently diverge (ADR-002/ADR-009).
    manual_bets = [{
        "data": "2026-07-17", "liga": "mls", "jogo": "St. Louis City vs Sporting Kansas City",
        "mercado": "Over 2.5", "odd": "1.42", "stake": "1", "resultado": "",
        "kickoffUTC": "2026-07-17T01:30:00+01:00", "leagueId": 999999,  # deliberately bogus
    }]
    manual_df = update_results.manual_bets_to_settlement_df(manual_bets)
    assert "LeagueId" not in manual_df.columns
    assert "leagueId" not in manual_df.columns
    liga_display = manual_df.iloc[0]["Liga"]
    assert LEAGUE_CODE_MAP[liga_display] == "mls"


# ── MLS Next Pro is a fully active, first-class league (Part 2) ───────────────

def test_mls_next_pro_present_in_generation_config():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert "mls_next_pro" in cfg.get("leagues", {})
    assert cfg["leagues"]["mls_next_pro"]["name"] == "MLS Next Pro"
    assert "mls_next_pro" in cfg.get("api_football", {}).get("league_ids", {})
    assert cfg["api_football"]["league_ids"]["mls_next_pro"] == MLS_NEXT_PRO_AF_ID

def test_mls_and_mls_next_pro_both_present_in_generation_config():
    # Both leagues configured for generation independently of one another —
    # neither one's presence depends on the other.
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    league_ids = cfg["api_football"]["league_ids"]
    assert league_ids["mls"] == SENIOR_MLS_AF_ID
    assert league_ids["mls_next_pro"] == MLS_NEXT_PRO_AF_ID
    assert league_ids["mls"] != league_ids["mls_next_pro"]

def test_mls_next_pro_history_file_exists_for_lambda_projection():
    # process_league_fixtures() silently skips a league with no data_raw/{key}.csv
    # (see src/pick_generation.py) — a missing file would mean MLS Next Pro is
    # "configured" but never actually produces a pick.
    assert (ROOT / "data_raw" / "mls_next_pro.csv").exists()

def test_config_mls_id_still_matches_registry_senior_mls():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert cfg["api_football"]["league_ids"]["mls"] == SENIOR_MLS_AF_ID == REGISTRY_BY_KEY["mls"].af_id

def test_config_mls_next_pro_id_matches_registry():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert cfg["api_football"]["league_ids"]["mls_next_pro"] == MLS_NEXT_PRO_AF_ID == REGISTRY_BY_KEY["mls_next_pro"].af_id


# ── Fixture generation: independent, never one substituting for the other ─────

def test_fetch_fixtures_mls_zero_does_not_affect_mls_next_pro(monkeypatch):
    import fetch_oddsapi_fixtures as fx

    calls = []

    def fake_http_get(path, params):
        calls.append(dict(params))
        # MLS (253) has nothing this date; MLS Next Pro (909) has a real fixture.
        if params["league"] == 253:
            return {"response": [], "results": 0, "errors": []}
        if params["league"] == 909:
            return {"response": [{"fixture": {"id": 1}, "teams": {
                "home": {"name": "Chattanooga"}, "away": {"name": "Chicago Fire II"}}}],
                "results": 1, "errors": []}
        raise AssertionError(f"unexpected league id {params['league']}")

    def fake_search(league_key, season):
        raise AssertionError("search_league_id_by_api must never be called — no fallback substitution")

    monkeypatch.setattr(fx, "http_get_json_api_football", fake_http_get)
    monkeypatch.setattr(fx, "search_league_id_by_api", fake_search)

    mls_response, _ = fx.fetch_fixtures_for_league_date(253, 2026, "2026-07-21", league_key="mls")
    mnp_response, _ = fx.fetch_fixtures_for_league_date(909, 2026, "2026-07-21", league_key="mls_next_pro")

    assert mls_response == []
    assert len(mnp_response) == 1
    # Both were queried with their own, independent league id — no cross-influence.
    leagues_queried = sorted(c["league"] for c in calls)
    assert leagues_queried == [253, 909]

def test_fetch_fixtures_both_leagues_have_fixtures_same_date(monkeypatch):
    import fetch_oddsapi_fixtures as fx

    def fake_http_get(path, params):
        if params["league"] == 253:
            return {"response": [{"fixture": {"id": 1}, "teams": {
                "home": {"name": "Philadelphia Union"}, "away": {"name": "New York Red Bulls"}}}],
                "results": 1, "errors": []}
        if params["league"] == 909:
            return {"response": [{"fixture": {"id": 2}, "teams": {
                "home": {"name": "Vancouver Whitecaps II"}, "away": {"name": "Austin II"}}}],
                "results": 1, "errors": []}
        raise AssertionError(f"unexpected league id {params['league']}")

    monkeypatch.setattr(fx, "http_get_json_api_football", fake_http_get)

    mls_response, _ = fx.fetch_fixtures_for_league_date(253, 2026, "2026-07-23", league_key="mls")
    mnp_response, _ = fx.fetch_fixtures_for_league_date(909, 2026, "2026-07-23", league_key="mls_next_pro")

    assert len(mls_response) == 1
    assert len(mnp_response) == 1

def test_season_for_date_mls_next_pro_is_calendar_year():
    import fetch_oddsapi_fixtures as fx
    from datetime import date
    assert fx.season_for_date(date(2026, 7, 21), "mls_next_pro") == 2026
    assert fx.season_for_date(date(2026, 1, 10), "mls_next_pro") == 2026

def test_topup_league_set_includes_mls_next_pro():
    # US leagues kick off late UTC; the 23:00 top-up run exists precisely to
    # catch late odds for them — MLS Next Pro needs the same treatment as MLS.
    import main as bot_main
    assert "mls" in bot_main.NON_EU_TOPUP_LEAGUES
    assert "mls_next_pro" in bot_main.NON_EU_TOPUP_LEAGUES


# ── Manual bets on MLS Next Pro settle through the same shared engine ─────────

def test_manual_bet_mls_next_pro_routes_to_909():
    manual_bets = [{
        "data": "2026-06-21", "liga": "mls_next_pro", "jogo": "Huntsville City vs Crown Legacy",
        "mercado": "Over 2.5", "odd": "1.55", "stake": "1", "resultado": "",
    }]
    manual_df = update_results.manual_bets_to_settlement_df(manual_bets)
    liga_display = manual_df.iloc[0]["Liga"]
    assert liga_display == "MLS Next Pro"
    assert LEAGUE_CODE_MAP[liga_display] == "mls_next_pro"
    assert API_FOOTBALL_FALLBACK_COMPETITIONS["mls_next_pro"]["af_id"] == MLS_NEXT_PRO_AF_ID


# ── Other leagues are unaffected by this fix ───────────────────────────────────

def test_non_mls_leagues_unaffected():
    assert REGISTRY_BY_KEY["premier"].af_id == 39
    assert REGISTRY_BY_KEY["brasil"].af_id == 71
    assert REGISTRY_BY_KEY["japao"].af_id == 98
    assert REGISTRY_BY_KEY["finlandia"].af_id == 244

def test_config_and_registry_agree_for_every_league():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    league_ids = cfg["api_football"]["league_ids"]
    for key, af_id in league_ids.items():
        assert REGISTRY_BY_KEY[key].af_id == af_id, f"{key}: config={af_id} vs registry={REGISTRY_BY_KEY[key].af_id}"
