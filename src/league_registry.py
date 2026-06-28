"""
League Registry — single source of truth for all league metadata.

To add a new league:
  1. Add a LeagueEntry row to REGISTRY below.
  2. Add the league to config.json (leagues + api_football.league_ids).
  That is all. LEAGUE_CODE_MAP, BLOCKED_FOOTBALL_DATA_CODES, and
  API_FOOTBALL_FALLBACK_COMPETITIONS are all derived automatically.

Field notes
  fd_code      : football-data.org competition code; None = no FD coverage at all.
  fd_blocked   : True = FD code exists but is blocked (HTTP 403); skip FD entirely.
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
    fd_code: str | None # football-data.org competition code; None = not on FD
    fd_blocked: bool    # True = FD code exists but returns errors; bypass FD
    af_country: str     # API-Football country string
    af_name: str        # API-Football competition name (fuzzy fallback)
    af_id: int | None   # API-Football integer ID; short-circuits /leagues API call
    # How game dates map to API-Football season integers:
    #   "european" — season starts in July/August; Jan–Jun -> year-1 (e.g. Feb 2026 -> 2025)
    #   "calendar" — season equals the calendar year the game is played (MLS, Nordic, Asian, etc.)
    season_model: str = "european"


def _settlement_code(e: LeagueEntry) -> str:
    """Routing key for the settlement pipeline.

    Uses the real FD code for leagues that have one, so existing FD plumbing
    continues to work without changes. Uses the internal config.json key for
    non-EU leagues (where no FD code exists) — the key is arbitrary for routing
    because those leagues bypass FD entirely and go straight to API-Football.
    """
    return e.fd_code if e.fd_code else e.key


REGISTRY: list[LeagueEntry] = [
    # ── EU: served by football-data.org ───────────────────────────────────
    LeagueEntry("premier",       "Premier League",                "ENG", "PL",  False, "England",     "Premier League",      39),
    LeagueEntry("espanha",       "LaLiga",                        "ESP", "PD",  False, "Spain",       "La Liga",             140),
    LeagueEntry("franca",        "Ligue 1",                       "FRA", "FL1", False, "France",      "Ligue 1",             61),
    LeagueEntry("italia",        "Serie A",                       "ITA", "SA",  False, "Italy",       "Serie A",             135),
    LeagueEntry("paises_baixos", "Eredivisie",                    "NLD", "DED", False, "Netherlands", "Eredivisie",          88),
    LeagueEntry("championship",  "Championship",                  "ENG", "ELC", False, "England",     "Championship",        40),
    # ── EU: blocked on football-data.org — API-Football direct ────────────
    LeagueEntry("portugal",      "Primeira Liga",                 "PRT", "PPL", True,  "Portugal",    "Primeira Liga",       94),
    LeagueEntry("alemanha",      "Bundesliga",                    "DEU", "BL1", True,  "Germany",     "Bundesliga",          78),
    LeagueEntry("alemanha2",     "2. Bundesliga",                 "DEU", "BL2", True,  "Germany",     "2. Bundesliga",       79),
    LeagueEntry("italia2",       "Serie B",                       "ITA", "SB",  True,  "Italy",       "Serie B",             136),
    LeagueEntry("franca2",       "Ligue 2",                       "FRA", "FL2", True,  "France",      "Ligue 2",             62),
    LeagueEntry("belgica",       "Jupiler Pro League",            "BEL", "BJL", True,  "Belgium",     "Belgian Pro League",  144),
    LeagueEntry("turquia",       "Super Lig",                     "TUR", "TSL", True,  "Turkey",      "Süper Lig",           203),
    # ── Non-EU: no FD coverage — API-Football direct — calendar-year seasons ─
    LeagueEntry("noruega",       "Eliteserien",                   "NOR", None,  False, "Norway",      "Eliteserien",         103, "calendar"),
    LeagueEntry("suecia",        "Allsvenskan",                   "SWE", None,  False, "Sweden",      "Allsvenskan",         113, "calendar"),
    LeagueEntry("finlandia",     "Veikkausliiga",                 "FIN", None,  False, "Finland",     "Veikkausliiga",       244, "calendar"),
    LeagueEntry("islandia",      "Besta deild",                   "ISL", None,  False, "Iceland",     "Úrvalsdeild",         188, "calendar"),
    LeagueEntry("mls",           "MLS",                           "USA", None,  False, "USA",         "MLS Next Pro",        909, "calendar"),
    LeagueEntry("brasil",        "Campeonato Brasileiro Serie A", "BRA", None,  False, "Brazil",      "Série A",             71,  "calendar"),
    LeagueEntry("japao",         "J1 League",                     "JPN", None,  False, "Japan",       "J1 League",           98,  "calendar"),
    LeagueEntry("coreia",        "K League 1",                    "KOR", None,  False, "South Korea", "K League 1",          292, "calendar"),
]

# ── Fast lookups ──────────────────────────────────────────────────────────────
REGISTRY_BY_KEY:  dict[str, LeagueEntry] = {e.key:  e for e in REGISTRY}
REGISTRY_BY_NAME: dict[str, LeagueEntry] = {e.name: e for e in REGISTRY}

# ── Derived settlement structures — consumed by update_results.py ─────────────

# Maps the "Liga" display name in picks CSVs to the internal settlement routing code.
LEAGUE_CODE_MAP: dict[str, str] = {e.name: _settlement_code(e) for e in REGISTRY}

# Historical aliases: some older CSVs and external APIs use these name variants.
_NAME_ALIASES: dict[str, str] = {
    "Süper Lig":          "Super Lig",         # Turkish league with umlaut
    "La Liga":            "LaLiga",            # with space
    "Belgian Pro League": "Jupiler Pro League", # alternative Belgian name
}
for _alias, _canonical in _NAME_ALIASES.items():
    if _canonical in LEAGUE_CODE_MAP:
        LEAGUE_CODE_MAP.setdefault(_alias, LEAGUE_CODE_MAP[_canonical])


# Settlement codes for which football-data.org is bypassed entirely.
# This covers (a) codes whose FD support is known-broken, and
# (b) non-EU leagues that have no FD coverage at all.
BLOCKED_FOOTBALL_DATA_CODES: frozenset[str] = frozenset(
    _settlement_code(e) for e in REGISTRY
    if e.fd_blocked or e.fd_code is None
)

# All leagues with API-Football coverage — used for direct settlement (blocked/non-EU)
# and as a fallback when football-data.org fails for any reason.
# The optional "af_id" key lets get_api_football_league_id() skip the /leagues API call.
API_FOOTBALL_FALLBACK_COMPETITIONS: dict[str, dict] = {
    _settlement_code(e): {
        "country": e.af_country,
        "name":    e.af_name,
        **({"af_id": e.af_id} if e.af_id is not None else {}),
    }
    for e in REGISTRY
}

# Maps API-Football integer league ID -> season model string.
# Consumed by api_football_season_from_date() in update_results.py.
AF_SEASON_MODELS: dict[int, str] = {
    e.af_id: e.season_model
    for e in REGISTRY
    if e.af_id is not None
}
