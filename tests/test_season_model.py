"""
tests/test_season_model.py

Automated tests for api_football_season_from_date() season model.

Run with:  python -m pytest tests/test_season_model.py -v
"""
import sys
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from update_results import api_football_season_from_date
from src.league_registry import AF_SEASON_MODELS

# ── League IDs referenced by tests ──────────────────────────────────────────
MLS_ID            = 909   # calendar-year (MLS Next Pro — all "MLS" picks are this tier)
VEIKKAUSLIIGA_ID  = 244   # calendar-year (Finland)
ELITESERIEN_ID    = 103   # calendar-year (Norway)
ALLSVENSKAN_ID    = 113   # calendar-year (Sweden)
URVALSDEID_ID     = 188   # calendar-year (Iceland)
SERIE_A_BR_ID     = 71    # calendar-year (Brazil)
J1_LEAGUE_ID      = 98    # calendar-year (Japan)
K_LEAGUE_ID       = 292   # calendar-year (South Korea)

PREMIER_LEAGUE_ID = 39    # european
LIGUE_1_ID        = 61    # european
SERIE_A_IT_ID     = 135   # european
BUNDESLIGA_ID     = 78    # european


# ── AF_SEASON_MODELS registry checks ────────────────────────────────────────

def test_registry_mls_is_calendar():
    assert AF_SEASON_MODELS[MLS_ID] == "calendar"

def test_registry_veikkausliiga_is_calendar():
    assert AF_SEASON_MODELS[VEIKKAUSLIIGA_ID] == "calendar"

def test_registry_eliteserien_is_calendar():
    assert AF_SEASON_MODELS[ELITESERIEN_ID] == "calendar"

def test_registry_allsvenskan_is_calendar():
    assert AF_SEASON_MODELS[ALLSVENSKAN_ID] == "calendar"

def test_registry_brazil_is_calendar():
    assert AF_SEASON_MODELS[SERIE_A_BR_ID] == "calendar"

def test_registry_j1_is_calendar():
    assert AF_SEASON_MODELS[J1_LEAGUE_ID] == "calendar"

def test_registry_k_league_is_calendar():
    assert AF_SEASON_MODELS[K_LEAGUE_ID] == "calendar"

def test_registry_premier_league_is_european():
    assert AF_SEASON_MODELS[PREMIER_LEAGUE_ID] == "european"

def test_registry_ligue1_is_european():
    assert AF_SEASON_MODELS[LIGUE_1_ID] == "european"

def test_registry_serie_a_it_is_european():
    assert AF_SEASON_MODELS[SERIE_A_IT_ID] == "european"

def test_registry_bundesliga_is_european():
    assert AF_SEASON_MODELS[BUNDESLIGA_ID] == "european"


# ── MLS (calendar) ───────────────────────────────────────────────────────────

def test_mls_june_2026():
    """MLS game in June 2026 -> 2026 (was returning 2025 before fix)."""
    assert api_football_season_from_date("2026-06-13", league_id=MLS_ID) == 2026

def test_mls_september_2026():
    """MLS game in September 2026 -> 2026."""
    assert api_football_season_from_date("2026-09-15", league_id=MLS_ID) == 2026

def test_mls_january_2026():
    """MLS pre-season in January 2026 -> 2026 (not 2025)."""
    assert api_football_season_from_date("2026-01-10", league_id=MLS_ID) == 2026

def test_mls_march_2025():
    """MLS season opener March 2025 -> 2025."""
    assert api_football_season_from_date("2025-03-01", league_id=MLS_ID) == 2025


# ── Veikkausliiga (calendar) ─────────────────────────────────────────────────

def test_veikkausliiga_may_2026():
    """Finnish game in May -> 2026 (was returning 2025 before fix)."""
    assert api_football_season_from_date("2026-05-20", league_id=VEIKKAUSLIIGA_ID) == 2026

def test_veikkausliiga_june_2026():
    """Finnish game in June -> 2026."""
    assert api_football_season_from_date("2026-06-23", league_id=VEIKKAUSLIIGA_ID) == 2026

def test_veikkausliiga_october_2026():
    """Finnish game in October -> 2026."""
    assert api_football_season_from_date("2026-10-05", league_id=VEIKKAUSLIIGA_ID) == 2026


# ── Premier League (european) ─────────────────────────────────────────────────

def test_premier_league_february_2026():
    """PL game in Feb 2026 -> 2025 (ongoing 2025-26 season)."""
    assert api_football_season_from_date("2026-02-15", league_id=PREMIER_LEAGUE_ID) == 2025

def test_premier_league_august_2025():
    """PL season opener Aug 2025 -> 2025."""
    assert api_football_season_from_date("2025-08-15", league_id=PREMIER_LEAGUE_ID) == 2025

def test_premier_league_july_2025():
    """July is the cutoff month; July 2025 -> 2025."""
    assert api_football_season_from_date("2025-07-01", league_id=PREMIER_LEAGUE_ID) == 2025

def test_premier_league_june_2025():
    """June (end of season) -> previous year: June 2025 -> 2024."""
    assert api_football_season_from_date("2025-06-30", league_id=PREMIER_LEAGUE_ID) == 2024


# ── No league_id (default = european) ────────────────────────────────────────

def test_no_league_id_june_defaults_european():
    """Without a league_id the function defaults to european model."""
    assert api_football_season_from_date("2026-06-13") == 2025

def test_no_league_id_august_defaults_european():
    assert api_football_season_from_date("2026-08-01") == 2026

def test_no_league_id_january_defaults_european():
    assert api_football_season_from_date("2026-01-01") == 2025


# ── Unknown league_id also defaults to european ───────────────────────────────

def test_unknown_league_id_june():
    """An unrecognised league_id falls back to european."""
    assert api_football_season_from_date("2026-06-01", league_id=99999) == 2025

def test_unknown_league_id_august():
    assert api_football_season_from_date("2026-08-01", league_id=99999) == 2026


# ── Year boundary ─────────────────────────────────────────────────────────────

def test_calendar_december():
    """December stays in the current year for calendar leagues."""
    assert api_football_season_from_date("2026-12-01", league_id=MLS_ID) == 2026

def test_european_december():
    """December is still current season for european leagues."""
    assert api_football_season_from_date("2026-12-01", league_id=PREMIER_LEAGUE_ID) == 2026
