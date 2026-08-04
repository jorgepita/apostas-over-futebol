"""
tests/test_phase28_new_leagues.py

Regression coverage for Phase 28.2 — three new first-class leagues:
  - Switzerland Super League      ("suica",     af_id=207)
  - Spain Segunda División        ("espanha2",  af_id=141)
  - Portugal Liga Portugal 2      ("portugal2", af_id=95)

France Ligue 2 was requested in the same phase but found already fully
integrated (registry + config.json + data_raw/franca2.csv) — audited, not
re-added. See docs/09_Architecture_Decisions.md ADR-004 update (Phase 28.2)
and docs/08_Change_Log.md.

Run with:  python -m pytest tests/test_phase28_new_leagues.py -v
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.league_registry import (
    REGISTRY_BY_KEY,
    LEAGUE_CODE_MAP,
    API_FOOTBALL_COMPETITIONS,
    AF_SEASON_MODELS,
)
import update_results
from main import NON_EU_TOPUP_LEAGUES

NEW_LEAGUES = {
    "suica":     {"af_id": 207, "country": "CHE", "name": "Super League"},
    "espanha2":  {"af_id": 141, "country": "ESP", "name": "Segunda División"},
    "portugal2": {"af_id": 95,  "country": "PRT", "name": "Liga Portugal 2"},
}


# ── Registry ────────────────────────────────────────────────────────────────

def test_registry_contains_all_three_leagues():
    for key in NEW_LEAGUES:
        assert key in REGISTRY_BY_KEY, f"{key} missing from REGISTRY_BY_KEY"


def test_registry_entries_have_correct_af_id_and_country():
    for key, expected in NEW_LEAGUES.items():
        entry = REGISTRY_BY_KEY[key]
        assert entry.af_id == expected["af_id"]
        assert entry.country == expected["country"]
        assert entry.name == expected["name"]


def test_registry_entries_use_european_season_model():
    # All three run Jul/Aug-May/Jun, like every other EU league already registered.
    for key in NEW_LEAGUES:
        assert REGISTRY_BY_KEY[key].season_model == "european"


def test_new_leagues_are_not_in_non_eu_topup_set():
    # European season-model leagues must never receive the non-EU top-up
    # treatment (that set is reserved for calendar-model leagues).
    for key in NEW_LEAGUES:
        assert key not in NON_EU_TOPUP_LEAGUES


# ── Derived structures (auto-generated from REGISTRY) ──────────────────────

def test_derived_structures_include_new_leagues():
    for key, expected in NEW_LEAGUES.items():
        entry = REGISTRY_BY_KEY[key]
        assert LEAGUE_CODE_MAP[entry.name] == entry.code
        assert API_FOOTBALL_COMPETITIONS[entry.code]["af_id"] == expected["af_id"]
        assert AF_SEASON_MODELS[expected["af_id"]] == "european"


# ── config.json wiring (generation eligibility, per ADR-004) ───────────────

def test_config_json_leagues_and_league_ids_sections():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    for key, expected in NEW_LEAGUES.items():
        assert key in cfg["leagues"], f"{key} missing from config.json leagues"
        assert cfg["leagues"][key]["country"] == expected["country"]
        assert cfg["api_football"]["league_ids"][key] == expected["af_id"]


def test_config_json_historical_seasons_configured():
    # Needed because the "current" (2026/27) season had ~0 finished matches at
    # the time these leagues were bootstrapped — without an explicit season
    # list the default fallback would have produced an almost-empty history.
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    seasons_by_league = cfg["historical"]["seasons_by_league"]
    for key in NEW_LEAGUES:
        assert key in seasons_by_league
        assert len(seasons_by_league[key]) >= 1


# ── Settlement routing (real code path, not a re-implementation) ──────────

def test_settlement_resolves_league_id_from_registry():
    state = update_results.make_shared_runtime_state()
    for key, expected in NEW_LEAGUES.items():
        resolved = update_results.get_api_football_league_id(key, "2026-08-03", shared_state=state)
        assert resolved == expected["af_id"]


def test_settlement_season_model_applies_correctly():
    # European model: a February fixture belongs to the season that started
    # the previous August (2026-02-15 -> season 2025).
    state = update_results.make_shared_runtime_state()
    for expected in NEW_LEAGUES.values():
        season = update_results.api_football_season_from_date(
            "2026-02-15", league_id=expected["af_id"], shared_state=state
        )
        assert season == 2025


def test_manual_bet_league_display_name_resolves():
    for key, expected in NEW_LEAGUES.items():
        name = update_results._resolve_liga_display_name(key)
        assert name == expected["name"]


# ── data_raw history files (Poisson lambda calculation input) ─────────────

def test_data_raw_history_files_exist_with_correct_schema():
    required_cols = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    for key in NEW_LEAGUES:
        path = ROOT / "data_raw" / f"{key}.csv"
        assert path.exists(), f"data_raw/{key}.csv is missing"
        header = path.read_text(encoding="utf-8").splitlines()[0]
        cols = set(c.strip() for c in header.split(","))
        assert required_cols.issubset(cols), f"data_raw/{key}.csv missing required columns"


def test_data_raw_history_files_have_substantial_real_data():
    # Two full seasons of a professional league easily exceeds the model's
    # min_games thresholds; this guards against an empty/near-empty fetch
    # silently shipping as a "supported" league.
    for key in NEW_LEAGUES:
        path = ROOT / "data_raw" / f"{key}.csv"
        rows = path.read_text(encoding="utf-8").splitlines()
        assert len(rows) > 100, f"data_raw/{key}.csv has suspiciously few rows ({len(rows)})"
