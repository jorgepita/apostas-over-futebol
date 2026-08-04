"""
League Registry — single source of truth for all league metadata.

To add a new league:
  1. Add a LeagueEntry row to REGISTRY below.
  2. Add the league to config.json (leagues + api_football.league_ids).
  That is all. LEAGUE_CODE_MAP and API_FOOTBALL_COMPETITIONS are both
  derived automatically.

Field notes
  code         : internal settlement routing code (an opaque identifier —
                 for several EU leagues this happens to match football-data.org's
                 old competition code, purely for historical continuity; it
                 carries no provider meaning since football-data.org was
                 removed entirely in Phase 27.4, see
                 docs/09_Architecture_Decisions.md ADR-004 update).
  af_id        : API-Football integer league ID. When set, skips the /leagues API
                 lookup in get_api_football_league_id() and uses this directly.
  af_country   : API-Football /leagues?country= value (fallback if af_id missing).
  af_name      : API-Football competition name for fuzzy match (fallback if af_id missing).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueEntry:
    key: str            # config.json internal key
    name: str           # display name in picks CSV "Liga" column
    country: str        # 3-char ISO code
    code: str            # internal settlement routing code — see module docstring
    af_country: str     # API-Football country string
    af_name: str        # API-Football competition name (fuzzy fallback)
    af_id: int          # API-Football integer ID; short-circuits /leagues API call
    # How game dates map to API-Football season integers:
    #   "european" — season starts in July/August; Jan–Jun -> year-1 (e.g. Feb 2026 -> 2025)
    #   "calendar" — season equals the calendar year the game is played (MLS, Nordic, Asian, etc.)
    season_model: str = "european"


REGISTRY: list[LeagueEntry] = [
    # ── EU leagues ──────────────────────────────────────────────────────────
    LeagueEntry("premier",       "Premier League",                "ENG", "PL",  "England",     "Premier League",      39),
    LeagueEntry("espanha",       "LaLiga",                        "ESP", "PD",  "Spain",       "La Liga",             140),
    LeagueEntry("franca",        "Ligue 1",                       "FRA", "FL1", "France",      "Ligue 1",             61),
    LeagueEntry("italia",        "Serie A",                       "ITA", "SA",  "Italy",       "Serie A",             135),
    LeagueEntry("paises_baixos", "Eredivisie",                    "NLD", "DED", "Netherlands", "Eredivisie",          88),
    LeagueEntry("championship",  "Championship",                  "ENG", "ELC", "England",     "Championship",        40),
    LeagueEntry("portugal",      "Primeira Liga",                 "PRT", "PPL", "Portugal",    "Primeira Liga",       94),
    LeagueEntry("alemanha",      "Bundesliga",                    "DEU", "BL1", "Germany",     "Bundesliga",          78),
    LeagueEntry("alemanha2",     "2. Bundesliga",                 "DEU", "BL2", "Germany",     "2. Bundesliga",       79),
    LeagueEntry("italia2",       "Serie B",                       "ITA", "SB",  "Italy",       "Serie B",             136),
    LeagueEntry("franca2",       "Ligue 2",                       "FRA", "FL2", "France",      "Ligue 2",             62),
    LeagueEntry("belgica",       "Jupiler Pro League",            "BEL", "BJL", "Belgium",     "Belgian Pro League",  144),
    LeagueEntry("turquia",       "Super Lig",                     "TUR", "TSL", "Turkey",      "Süper Lig",           203),
    # ── Non-EU — calendar-year seasons ─────────────────────────────────────
    LeagueEntry("noruega",       "Eliteserien",                   "NOR", "noruega",      "Norway",      "Eliteserien",         103, "calendar"),
    LeagueEntry("suecia",        "Allsvenskan",                   "SWE", "suecia",       "Sweden",      "Allsvenskan",         113, "calendar"),
    LeagueEntry("finlandia",     "Veikkausliiga",                 "FIN", "finlandia",    "Finland",     "Veikkausliiga",       244, "calendar"),
    LeagueEntry("islandia",      "Besta deild",                   "ISL", "islandia",     "Iceland",     "Úrvalsdeild",         188, "calendar"),
    LeagueEntry("mls",           "MLS",                           "USA", "mls",          "USA",         "Major League Soccer", 253, "calendar"),
    # Genuinely distinct competition, distinct API-Football ID, fully supported
    # end-to-end (fixture fetch, generation, dashboard, settlement) exactly
    # like every other league below — see ADR-004 update. Also registered in
    # config.json's `leagues` / `api_football.league_ids` so
    # fetch_oddsapi_fixtures.py generates picks for it independently of MLS.
    # The two must never be substituted for one another (see
    # docs/05_Known_Issues.md SETTLEMENT-3 for the incident this prevents).
    LeagueEntry("mls_next_pro",  "MLS Next Pro",                  "USA", "mls_next_pro", "USA",         "MLS Next Pro",        909, "calendar"),
    LeagueEntry("brasil",        "Campeonato Brasileiro Serie A", "BRA", "brasil",       "Brazil",      "Série A",             71,  "calendar"),
    LeagueEntry("japao",         "J1 League",                     "JPN", "japao",        "Japan",       "J1 League",           98,  "calendar"),
    LeagueEntry("coreia",        "K League 1",                    "KOR", "coreia",       "South Korea", "K League 1",          292, "calendar"),
    # ── EU leagues (Phase 28.2) ─────────────────────────────────────────────
    # All three are "european" season model (Jul/Aug-May/Jun); confirmed live
    # against API-Football's /leagues endpoint 2026-08-03. "code" follows the
    # post-Phase-27.4 convention of using the key itself (no football-data.org
    # legacy code exists for these, unlike the older EU entries above).
    LeagueEntry("suica",         "Super League",                  "CHE", "suica",        "Switzerland", "Super League",        207),
    LeagueEntry("espanha2",      "Segunda División",              "ESP", "espanha2",     "Spain",       "Segunda División",    141),
    LeagueEntry("portugal2",     "Liga Portugal 2",               "PRT", "portugal2",    "Portugal",    "Segunda Liga",        95),
]

# ── Fast lookups ──────────────────────────────────────────────────────────────
REGISTRY_BY_KEY:  dict[str, LeagueEntry] = {e.key:  e for e in REGISTRY}
REGISTRY_BY_NAME: dict[str, LeagueEntry] = {e.name: e for e in REGISTRY}

# ── Derived settlement structures — consumed by update_results.py ─────────────

# Maps the "Liga" display name in picks CSVs to the internal settlement routing code.
LEAGUE_CODE_MAP: dict[str, str] = {e.name: e.code for e in REGISTRY}

# Historical aliases: some older CSVs and external APIs use these name variants.
_NAME_ALIASES: dict[str, str] = {
    "Süper Lig":          "Super Lig",         # Turkish league with umlaut
    "La Liga":            "LaLiga",            # with space
    "Belgian Pro League": "Jupiler Pro League", # alternative Belgian name
}
for _alias, _canonical in _NAME_ALIASES.items():
    if _canonical in LEAGUE_CODE_MAP:
        LEAGUE_CODE_MAP.setdefault(_alias, LEAGUE_CODE_MAP[_canonical])


# Every league's API-Football routing info, keyed by its settlement code.
# The sole provider mapping as of Phase 27.4 (football-data.org removed).
# The "af_id" key lets get_api_football_league_id() skip the /leagues API call.
API_FOOTBALL_COMPETITIONS: dict[str, dict] = {
    e.code: {
        "country": e.af_country,
        "name":    e.af_name,
        "af_id":   e.af_id,
    }
    for e in REGISTRY
}

# Maps API-Football integer league ID -> season model string.
# Consumed by api_football_season_from_date() in update_results.py.
AF_SEASON_MODELS: dict[int, str] = {
    e.af_id: e.season_model
    for e in REGISTRY
}
