import base64
import json
import os
import re
import tempfile
import time
import unicodedata
from pathlib import Path
from urllib import request, parse, error
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

import pandas as pd
from dotenv import load_dotenv
from src.league_stats import update_league_stats
from src.league_registry import (
    LEAGUE_CODE_MAP,
    API_FOOTBALL_COMPETITIONS,
    AF_SEASON_MODELS,
    REGISTRY_BY_KEY,
)
from src.config import load_config, get_void_policy

load_dotenv()

BASE = Path(__file__).resolve().parent
DAILY_FILE = BASE / "picks_hoje_simplificado.csv"
HISTORY_FILE = BASE / "picks_history.csv"
LEAGUE_STATS_FILE = BASE / "league_stats.csv"

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

GITHUB_OWNER = "jorgepita"
GITHUB_REPO = "apostas-over-futebol"
GITHUB_BRANCH = "main"

REMOTE_DAILY_NAME = "picks_hoje_simplificado.csv"
REMOTE_HISTORY_NAME = "picks_history.csv"
REMOTE_LEAGUE_STATS_NAME = "league_stats.csv"
CLOUD_STATE_NAME = "cloud_state.json"

# LEAGUE_CODE_MAP and API_FOOTBALL_COMPETITIONS are imported from
# src.league_registry above.
# To add or change a league mapping, edit src/league_registry.py — not this file.

SUPPORTED_MARKETS = {"O1.5", "O2.5", "O3.5", "BTTS"}

CSV_COLUMNS = [
    "Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€", "Edge%",
    "Apostada", "OddReal", "StakeReal€",
    "Resultado", "Placar", "Lucro€", "LucroReal€", "KickoffUTC",
    # Additive (Part 11/ADR-017): SettlementReason records *why* a P was
    # written (postponed_timeout/cancelled_timeout/abandoned_timeout/
    # interrupted_timeout/missing_fixture_timeout/manual_void), blank for
    # every normal W/L/P. MissingAttempts is a working counter — consecutive
    # genuine NO_MATCH observations since kickoff, the persisted evidence the
    # missing-fixture safeguard requires before it will ever auto-void (see
    # _evaluate_missing_fixture_void()). Existing rows read both back as ""
    # via ensure_columns(), exactly like Placar did when it was added.
    "SettlementReason", "MissingAttempts",
]

SYNC_RESULT_COLUMNS = [
    "Apostada", "OddReal", "StakeReal€",
    "Resultado", "Placar", "Lucro€", "LucroReal€", "SettlementReason"
]

HTTP_TIMEOUT = 30

# API-Football — the sole result provider (Phase 27.4; football-data.org
# was removed entirely, see docs/09_Architecture_Decisions.md ADR-004 update).
AF_MAX_RETRIES = 4
AF_BASE_SLEEP = 1.2
AF_CALL_MIN_INTERVAL = 0.50
AF_BASE_URL = "https://v3.football.api-sports.io"

# Confirmado pelos teus testes

AF_FINISHED_STATUS = {"FT", "AET", "PEN"}

RESULT_READY_DELAY = timedelta(hours=2, minutes=15)
EARLY_STATUS_IGNORE = {"NS", "TBD", "SCHEDULED", "TIMED", "1H", "HT", "2H", "ET", "BT", "LIVE", "IN_PLAY"}

# =============================
# Fixture status classification (postponed/cancelled/missing-fixture voiding)
#
# A provider status is never enough on its own to decide whether a pick is
# "done" — see docs/09_Architecture_Decisions.md ADR-017. Four buckets,
# in addition to the pre-existing *_FINISHED_STATUS sets above:
#
#   IN_PROGRESS         — the match is currently being played (or between
#                          periods). Never a void candidate at any age.
#   NON_PLAYED           — the provider says, with reasonable finality, that
#                          the match will not complete under this fixture:
#                          postponed (not yet played, effectively
#                          rescheduled), cancelled, or abandoned (API-Football
#                          semantics: a final "will not continue under this
#                          fixture ID" determination, not "may still resume").
#                          Eligible for the 48h explicit-status auto-void.
#   SUSPENDED_INTERRUPTED — a match that started and was temporarily halted
#                          (weather, floodlights, crowd trouble, ...) and is
#                          commonly expected to resume, same day or on a
#                          later date, often continuing from the same score
#                          under the SAME fixture ID. Voiding this merely
#                          because 48h have elapsed since the ORIGINAL
#                          kickoff would incorrectly void a wager whose match
#                          is still going to finish and produce a real result
#                          (e.g. interrupted Monday, resumes and finishes
#                          Friday — 48h lands mid-week, before resumption).
#                          A prior version of this policy grouped these with
#                          NON_PLAYED; a dedicated safety re-audit (Phase
#                          26.44) found that unsafe and corrected it. These
#                          statuses are deliberately NOT given their own
#                          separate timeout — they fall through to the same
#                          treatment as SCHEDULED_UNKNOWN below (never an
#                          automatic-void trigger). The 24h manual "Anular
#                          aposta" fallback remains available if the user
#                          knows the real bookmaker has already voided the
#                          wager despite the fixture nominally being able to
#                          resume.
#   (anything else)     — SCHEDULED/UNKNOWN (NS, TBD, or an unrecognised
#                          code — this bucket is also where
#                          SUSPENDED_INTERRUPTED statuses actually land,
#                          since no separate classify_*_status() return value
#                          exists for them; see the *_SUSPENDED_INTERRUPTED_
#                          STATUS sets below, kept only for documentation and
#                          test clarity). Treated exactly like today: "not
#                          finished yet", never itself a void trigger. AWD/WO
#                          (technical loss/walkover) are deliberately left
#                          unclassified — rare, and their goal data is not
#                          reliable enough to either settle or void
#                          automatically; they remain open (manual void
#                          after 24h still applies to them).
# =============================
AF_IN_PROGRESS_STATUS = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
AF_NON_PLAYED_STATUS = {"PST", "CANC", "ABD"}
# Documentation-only — NOT consulted by classify_af_status(); these statuses
# are intentionally absent from AF_NON_PLAYED_STATUS above and therefore
# already fall through to the safe SCHEDULED_UNKNOWN default. Listed here so
# a future edit doesn't accidentally re-add them to AF_NON_PLAYED_STATUS
# without re-reading why they were removed (see the comment block above).
AF_SUSPENDED_INTERRUPTED_STATUS = {"SUSP", "INT"}

AF_VOID_REASON_BY_STATUS = {
    "PST": "postponed_timeout",
    "CANC": "cancelled_timeout",
    "ABD": "abandoned_timeout",
}

MISSING_FIXTURE_VOID_REASON = "missing_fixture_timeout"
MANUAL_VOID_REASON = "manual_void"

# Void policy thresholds — canonical values live in config.json
# ["settlement"]["void_policy"]; DEFAULT_* fallbacks live in src/config.py
# (ADR-010's pattern for every other config-driven value). Loaded once at
# import time, like every other module-level settlement constant.
_VOID_POLICY = get_void_policy(load_config(BASE))
POSTPONED_VOID_AFTER_HOURS = _VOID_POLICY["postponed_void_after_hours"]
MISSING_FIXTURE_VOID_AFTER_HOURS = _VOID_POLICY["missing_fixture_void_after_hours"]
MANUAL_VOID_AVAILABLE_AFTER_HOURS = _VOID_POLICY["manual_void_available_after_hours"]
MISSING_FIXTURE_MIN_ATTEMPTS = _VOID_POLICY["missing_fixture_min_attempts"]

POSTPONED_VOID_TIMEDELTA = timedelta(hours=POSTPONED_VOID_AFTER_HOURS)
MISSING_FIXTURE_VOID_TIMEDELTA = timedelta(hours=MISSING_FIXTURE_VOID_AFTER_HOURS)

# Bounded, forward-only rediscovery window for a mature missing-fixture void
# candidate (Part 5 / ADR-017) — see attempt_rediscovery_af(). Deliberately
# not configurable: it is a search-cost bound, not a policy decision.
REDISCOVERY_MAX_FORWARD_DAYS = 14

TEAM_ALIAS_CACHE_FILE = str(BASE / "team_alias_cache.json")

MATCH_MIN_TOTAL_SCORE = 140
MATCH_MIN_SIDE_SCORE = 62

BASE_TEAM_ALIASES = {
    # Championship
    "qpr": "queens park rangers",
    "queens park rangers": "queens park rangers",

    # Bélgica
    "antwerp": "royal antwerp",
    "royal antwerp": "royal antwerp",
    "royal antwerp fc": "royal antwerp",
    "antwerp fc": "royal antwerp",

    "genk": "krc genk",
    "krc genk": "krc genk",
    "racing genk": "krc genk",

    "charleroi": "sporting charleroi",
    "sporting charleroi": "sporting charleroi",
    "royal charleroi": "sporting charleroi",

    "gent": "kaa gent",
    "kaa gent": "kaa gent",

    "kv mechelen": "mechelen",
    "mechelen": "mechelen",

    "club brugge": "club brugge",
    "club brugge kv": "club brugge",
    "anderlecht": "anderlecht",
    "rsc anderlecht": "anderlecht",

    # França
    "lyon": "olympique lyonnais",
    "olympique lyon": "olympique lyonnais",
    "olympique lyonnais": "olympique lyonnais",

    "angers": "angers sco",
    "angers sco": "angers sco",

    "stade brestois 29": "brest",
    "stade brestois": "brest",
    "brest": "brest",

    "rennes": "stade rennais",
    "stade rennais": "stade rennais",
    "stade rennais fc": "stade rennais",

    "paris sg": "paris saint germain",
    "psg": "paris saint germain",
    "paris saint germain": "paris saint germain",

    # Alemanha
    "1 fc nurnberg": "nurnberg",
    "1. fc nurnberg": "nurnberg",
    "fc nurnberg": "nurnberg",
    "nurnberg": "nurnberg",
    "nuernberg": "nurnberg",

    "fc schalke 04": "schalke",
    "schalke 04": "schalke",
    "schalke": "schalke",

    "hannover 96": "hannover",
    "hannover": "hannover",

    "eintracht braunschweig": "braunschweig",
    "braunschweig": "braunschweig",

    "hertha bsc": "hertha berlin",
    "hertha": "hertha berlin",
    "hertha berlin": "hertha berlin",

    "1 fc koln": "koln",
    "1. fc koln": "koln",
    "fc koln": "koln",
    "koln": "koln",
    "koeln": "koln",

    "bayer leverkusen": "leverkusen",
    "leverkusen": "leverkusen",

    "vfl wolfsburg": "wolfsburg",
    "wolfsburg": "wolfsburg",

    # Holanda
    "az alkmaar": "az",
    "az": "az",
    "fortuna sittard": "fortuna sittard",

    "nec nijmegen": "nec",
    "nec": "nec",

    "go ahead eagles": "go ahead eagles",
    "pec zwolle": "pec zwolle",

    # Portugal
    "benfica": "benfica",
    "sport lisboa e benfica": "benfica",
    "sporting": "sporting cp",
    "sporting cp": "sporting cp",
    "porto": "fc porto",
    "fc porto": "fc porto",

    "estoril": "estoril",
    "estoril praia": "estoril",
    "gd estoril praia": "estoril",

    "moreirense": "moreirense",
    "moreirense fc": "moreirense",

    "estrela": "estrela",
    "estrela da amadora": "estrela",
    "cf estrela da amadora": "estrela",

    "guimaraes": "vitoria sc",
    "guimarães": "vitoria sc",
    "vitoria guimaraes": "vitoria sc",
    "vitória guimarães": "vitoria sc",
    "vitoria sc": "vitoria sc",

    "nacional": "cd nacional",
    "cd nacional": "cd nacional",

    "braga": "sc braga",
    "sc braga": "sc braga",

    "famalicao": "famalicao",
    "famalicão": "famalicao",
    "fc famalicao": "famalicao",

    "rio ave": "rio ave",
    "rio ave fc": "rio ave",

    "gil vicente": "gil vicente",
    "gil vicente fc": "gil vicente",

    # Itália
    "inter": "inter",
    "inter milan": "inter",
    "internazionale": "inter",
    "internazionale milano": "inter",

    "milan": "ac milan",
    "ac milan": "ac milan",

    # Turquia
    "galatasaray": "galatasaray",
    "fenerbahce": "fenerbahce",
    "besiktas": "besiktas",
    "trabzonspor": "trabzonspor",
    "gaziantep": "gaziantep fk",
    "gaziantep fk": "gaziantep fk",
    "alanyaspor": "alanyaspor",
    "antalyaspor": "antalyaspor",
    "eyupspor": "eyupspor",
    "eyupspor istanbul": "eyupspor",
    "eyupspor fk": "eyupspor",
    "eyupspor kulubu": "eyupspor",
    "eyuspor": "eyupspor",

    # Inglaterra
    "west ham": "west ham united",
    "west ham united": "west ham united",

    "wolves": "wolverhampton wanderers",
    "wolverhampton": "wolverhampton wanderers",
    "wolverhampton wanderers": "wolverhampton wanderers",

    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "tottenham hotspur": "tottenham hotspur",

    "man utd": "manchester united",
    "man united": "manchester united",
    "manchester utd": "manchester united",
    "manchester united": "manchester united",

    "man city": "manchester city",
    "manchester city": "manchester city",

    "newcastle": "newcastle united",
    "newcastle united": "newcastle united",

    "leeds": "leeds united",
    "leeds united": "leeds united",

    "forest": "nottingham forest",
    "nottingham forest": "nottingham forest",

    "brighton": "brighton hove albion",
    "brighton hove albion": "brighton hove albion",

    "west brom": "west bromwich albion",
    "west bromwich albion": "west bromwich albion",

    "sheff utd": "sheffield united",
    "sheffield united": "sheffield united",

    "sheff wed": "sheffield wednesday",
    "sheffield wednesday": "sheffield wednesday",

    "preston": "preston north end",
    "preston north end": "preston north end",

    "stoke": "stoke city",
    "stoke city": "stoke city",

    "birmingham": "birmingham city",
    "birmingham city": "birmingham city",

    "norwich": "norwich city",
    "norwich city": "norwich city",

    "leicester": "leicester city",
    "leicester city": "leicester city",
    
    # genéricos frequentes
    "spvgg greuther furth": "greuther furth",
    "greuther furth": "greuther furth",
    "fortuna dusseldorf": "fortuna dusseldorf",
    "dusseldorf": "fortuna dusseldorf",
    "kaiserslautern": "kaiserslautern",
    "1 fc kaiserslautern": "kaiserslautern",
    "magdeburg": "magdeburg",
    "1 fc magdeburg": "magdeburg",
    "paderborn": "paderborn",
    "sc paderborn 07": "paderborn",
}

TEAM_STOPWORDS = {
    "fc", "cf", "sc", "sv", "fk", "ac", "as", "rc", "kv", "kvc",
    "afc", "sco", "calcio", "club", "de", "the", "nk", "sk", "if",
    "bk", "jk", "cd", "ud", "sd", "real", "sporting", "athletic"
}

SHARED_STATE_DEFAULTS = {
    "team_aliases_runtime": {},
    "team_aliases_dirty": False,
    "normalized_team_cache": {},
    "similarity_cache": {},
    "canonical_pair_cache": {},
    "date_parse_cache": {},
}

# Temporary diagnostics — enable with UPDATE_RESULTS_DEBUG=1
UPDATE_RESULTS_DEBUG = os.getenv("UPDATE_RESULTS_DEBUG", "").strip().lower() in {
    "1", "true", "yes", "on",
}


# =============================
# Provider error handling
#
# API-Football can return HTTP 200
# with an empty `response`/`matches` list while carrying a non-empty
# `errors` object describing *why* nothing was returned (wrong plan tier,
# quota exceeded, bad auth, ...). Left unhandled, that is indistinguishable
# from "no games today" and settlement silently reports "No matches to
# settle." even though the provider never actually looked at the fixture.
#
# Everything below normalises both that case and outright HTTP failures
# (401/403/429/5xx) into one record shape so the failure reason survives
# from the API client up through the settlement summary to the dashboard.
# =============================
PROVIDER_ERROR_CATEGORIES = {
    "PLAN_LIMIT", "QUOTA_EXCEEDED", "AUTHENTICATION",
    "INVALID_REQUEST", "NETWORK", "SERVER_ERROR", "UNKNOWN",
}
RETRYABLE_PROVIDER_CATEGORIES = {"QUOTA_EXCEEDED", "NETWORK", "SERVER_ERROR"}
PROVIDER_HEALTH_WARNING_THRESHOLD = 2  # consecutive failing settlement runs before status flips to "warning"


class ProviderError(Exception):
    """Raised when a provider responded, but the response itself signals the
    request failed (bad plan/quota/auth/etc) rather than a genuine empty result.
    Carries a normalized error record in `.record`."""

    def __init__(self, record: dict):
        self.record = record
        super().__init__(record.get("message", "provider error"))


def build_provider_error(provider: str, endpoint: str, request_params, category: str, message: str) -> dict:
    return {
        "provider": provider,
        "endpoint": endpoint,
        "request": request_params,
        "category": category if category in PROVIDER_ERROR_CATEGORIES else "UNKNOWN",
        "message": message,
        "retryable": category in RETRYABLE_PROVIDER_CATEGORIES,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _extract_meaningful_errors_field(errors_obj) -> str:
    """API-Football's `errors` field is a dict of {field: message} (or, on
    older responses, a list of such dicts). Returns a flattened human-readable
    string, or '' if there is nothing meaningful in it."""
    if not errors_obj:
        return ""
    parts = []
    if isinstance(errors_obj, dict):
        parts = [f"{k}: {v}" for k, v in errors_obj.items() if v]
    elif isinstance(errors_obj, list):
        for item in errors_obj:
            if isinstance(item, dict):
                parts.extend(f"{k}: {v}" for k, v in item.items() if v)
            elif item:
                parts.append(str(item))
    else:
        parts = [str(errors_obj)]
    return " | ".join(parts)


def _extract_message_from_http_error_body(body_text: str) -> str:
    """Best-effort extraction of a human-readable message from an HTTP error
    response body — understands both API-Football's `errors` shape and a
    plain `{"message": "..."}` shape. Falls back to raw text."""
    if not body_text:
        return ""
    try:
        obj = json.loads(body_text)
    except Exception:
        return body_text[:300]

    if isinstance(obj, dict):
        parts = []
        errors_msg = _extract_meaningful_errors_field(obj.get("errors"))
        if errors_msg:
            parts.append(errors_msg)
        if obj.get("message"):
            parts.append(str(obj["message"]))
        if parts:
            return " | ".join(parts)

    return body_text[:300]


def _read_http_error_body(e: "error.HTTPError") -> str:
    try:
        return e.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def classify_provider_message(message: str) -> str:
    m = (message or "").lower()
    if any(term in m for term in ("plan", "season", "subscription")):
        return "PLAN_LIMIT"
    if any(term in m for term in ("quota", "rate limit", "too many requests")):
        return "QUOTA_EXCEEDED"
    if "requests" in m and ("limit" in m or "exceeded" in m):
        return "QUOTA_EXCEEDED"
    if any(term in m for term in ("token", "api key", "invalid key", "unauthorized", "authentication", "credentials")):
        return "AUTHENTICATION"
    if any(term in m for term in ("invalid", "not found", "unknown league", "bad request")):
        return "INVALID_REQUEST"
    return "UNKNOWN"


def classify_provider_status(status_code) -> str:
    if status_code in (401, 403):
        return "AUTHENTICATION"
    if status_code == 429:
        return "QUOTA_EXCEEDED"
    if isinstance(status_code, int) and 500 <= status_code < 600:
        return "SERVER_ERROR"
    if isinstance(status_code, int) and 400 <= status_code < 500:
        return "INVALID_REQUEST"
    return "UNKNOWN"


def classify_provider_error(status_code, message_text: str) -> tuple[str, str]:
    """Combines message-content classification (authoritative when present)
    with an HTTP-status fallback. Returns (category, message)."""
    message_text = message_text or ""
    category = classify_provider_message(message_text) if message_text else "UNKNOWN"
    if category == "UNKNOWN":
        category = classify_provider_status(status_code)
    if not message_text:
        message_text = f"HTTP {status_code}" if status_code is not None else "Unknown provider error"
    return category, message_text


def log_provider_error(record: dict):
    """Always-on structured log — this is the visibility the silent
    'HTTP 200 + empty response' failure mode never had before."""
    print(
        f"\n[{record['provider'].upper()}]\n"
        f"Endpoint:\n{record['endpoint']}\n"
        f"Category:\n{record['category']}\n"
        f"Message:\n{record['message']}\n"
    )


def record_provider_error(shared_state: dict, record: dict):
    shared_state.setdefault("provider_errors", []).append(record)
    log_provider_error(record)


def record_provider_success(shared_state: dict, provider: str):
    shared_state.setdefault("provider_success_seen", set()).add(provider)


# =============================
# Helpers
# =============================
def ensure_shared_state_defaults(shared_state: dict | None) -> dict:
    if shared_state is None:
        shared_state = {}

    for k, v in SHARED_STATE_DEFAULTS.items():
        if k not in shared_state:
            shared_state[k] = v.copy() if isinstance(v, dict) else v

    return shared_state


def debug_log(msg: str):
    print(f"[DBG] {msg}")


def diag_log(msg: str):
    if UPDATE_RESULTS_DEBUG:
        print(f"[DIAG] {msg}")


def get_fixture_id(fixture: dict | None) -> str:
    if not isinstance(fixture, dict):
        return ""
    nested = fixture.get("fixture") or {}
    fid = nested.get("id") or fixture.get("id")
    return str(fid) if fid is not None else ""


def format_fixture_diag(fixture: dict | None) -> str:
    if not isinstance(fixture, dict):
        return "fixture=None"
    home, away = extract_fixture_team_names(fixture)
    status = get_fixture_status(fixture)
    home_goals, away_goals = get_fixture_score(fixture)
    kickoff_dt = get_fixture_kickoff_dt(fixture)
    kickoff_txt = kickoff_dt.isoformat() if kickoff_dt else "n/a"
    return (
        f"fixture_id={get_fixture_id(fixture)} | api='{home} vs {away}' | "
        f"status={status} | score={home_goals}-{away_goals} | kickoff_utc={kickoff_txt}"
    )


def log_pick_diag(
    label: str,
    idx,
    row,
    stage: str,
    reason: str,
    **extra,
):
    if not UPDATE_RESULTS_DEBUG:
        return
    data = str(row.get("Data", "")).strip()
    liga = str(row.get("Liga", "")).strip()
    jogo = str(row.get("Jogo", "")).strip()
    mercado = str(row.get("Mercado", "")).strip()
    parts = [
        f"{label}[{idx}] stage={stage} reason={reason}",
        f"pick={data} | {liga} | {jogo} | {mercado}",
    ]
    for key, value in extra.items():
        parts.append(f"{key}={value}")
    diag_log(" | ".join(parts))


def warn_log(msg: str):
    print(f"[WARN] {msg}")


def ok_log(msg: str):
    print(f"[OK] {msg}")


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _pre_clean_team_name(text: str) -> str:
    s = strip_accents(text).lower()

    s = s.replace("&", " and ")
    s = s.replace("'", " ")
    s = s.replace("’", " ")
    s = s.replace("-", " ")
    s = s.replace("/", " ")

    s = re.sub(r"[^\w\s]", " ", s)

    s = s.replace("1 fc", "1 fc ")
    s = s.replace("1  fc", "1 fc ")
    s = s.replace("st.", "saint")
    s = s.replace("st ", "saint ")
    s = s.replace("mtz", "metz")

    s = normalize_whitespace(s)
    return s


def load_team_alias_cache() -> dict:
    if not os.path.exists(TEAM_ALIAS_CACHE_FILE):
        return {}

    try:
        with open(TEAM_ALIAS_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            out = {}
            for k, v in data.items():
                k2 = normalize_whitespace(_pre_clean_team_name(k))
                v2 = normalize_whitespace(_pre_clean_team_name(v))
                if k2 and v2:
                    out[k2] = v2
            return out
    except Exception as e:
        warn_log(f"team alias cache: erro ao ler {TEAM_ALIAS_CACHE_FILE}: {e}")

    return {}


def save_team_alias_cache(shared_state: dict | None = None):
    shared_state = ensure_shared_state_defaults(shared_state)

    if not shared_state.get("team_aliases_dirty"):
        return

    aliases = shared_state.get("team_aliases_runtime", {})

    try:
        with open(TEAM_ALIAS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(aliases.items())), f, ensure_ascii=False, indent=2)

        shared_state["team_aliases_dirty"] = False
        debug_log(f"team alias cache: guardado {len(aliases)} aliases em {TEAM_ALIAS_CACHE_FILE}")
    except Exception as e:
        warn_log(f"team alias cache: erro ao guardar {TEAM_ALIAS_CACHE_FILE}: {e}")


def get_team_aliases(shared_state: dict | None = None) -> dict:
    shared_state = ensure_shared_state_defaults(shared_state)

    if shared_state["team_aliases_runtime"]:
        return shared_state["team_aliases_runtime"]

    aliases = {}

    for k, v in BASE_TEAM_ALIASES.items():
        k2 = normalize_whitespace(_pre_clean_team_name(k))
        v2 = normalize_whitespace(_pre_clean_team_name(v))
        if k2 and v2:
            aliases[k2] = v2

    for k, v in load_team_alias_cache().items():
        aliases[k] = v

    shared_state["team_aliases_runtime"] = aliases
    return aliases


def normalize_team_name(text: str, shared_state: dict | None = None) -> str:
    original_text = text
    shared_state = ensure_shared_state_defaults(shared_state)
    cache = shared_state["normalized_team_cache"]

    cache_key = str(text or "")
    if cache_key in cache:
        return cache[cache_key]

    aliases = get_team_aliases(shared_state)

    s = _pre_clean_team_name(text)
    if not s:
        cache[cache_key] = ""
        return ""

    if s in aliases:
        cache[cache_key] = aliases[s]

        if os.getenv("UPDATE_RESULTS_DEBUG") == "1":
            print(f"[DBG] normalize_team_name | original='{original_text}' -> normalized='{cache[cache_key]}'")
        
        return cache[cache_key]

    tokens = [t for t in s.split() if t not in TEAM_STOPWORDS]
    s2 = normalize_whitespace(" ".join(tokens))

    if s2 in aliases:
        cache[cache_key] = aliases[s2]

        if os.getenv("UPDATE_RESULTS_DEBUG") == "1":
            print(f"[DBG] normalize_team_name | original='{original_text}' -> normalized='{cache[cache_key]}'")
        
        return cache[cache_key]

    s2 = s2.replace("saint ", "st ")
    s2 = normalize_whitespace(s2)

    if s2 in aliases:
        cache[cache_key] = aliases[s2]
        return cache[cache_key]

    cache[cache_key] = s2
    return cache[cache_key]


def similarity_score(a: str, b: str, shared_state: dict | None = None) -> int:
    shared_state = ensure_shared_state_defaults(shared_state)
    cache = shared_state["similarity_cache"]

    cache_key = (str(a or ""), str(b or ""))
    if cache_key in cache:
        return cache[cache_key]

    na = normalize_team_name(a, shared_state)
    nb = normalize_team_name(b, shared_state)

    if not na or not nb:
        cache[cache_key] = 0
        return 0

    if na == nb:
        cache[cache_key] = 100
        return 100

    if na in nb or nb in na:
        shorter = min(len(na), len(nb))
        longer = max(len(na), len(nb))
        if longer > 0:
            frac = shorter / longer
            if frac >= 0.70:
                cache[cache_key] = 94
                return 94
            if frac >= 0.55:
                cache[cache_key] = 90
                return 90

    ta = set(na.split())
    tb = set(nb.split())

    if ta and tb:
        inter = len(ta & tb)
        union = len(ta | tb)
        jacc = inter / union if union else 0.0
        if jacc >= 0.80:
            cache[cache_key] = 92
            return 92
        if jacc >= 0.60:
            cache[cache_key] = 88
            return 88

    ratio = SequenceMatcher(None, na, nb).ratio()
    score = int(round(ratio * 100))
    cache[cache_key] = score
    return score


def canonical_pair(home: str, away: str, shared_state: dict | None = None) -> tuple[str, str]:
    shared_state = ensure_shared_state_defaults(shared_state)
    cache = shared_state["canonical_pair_cache"]

    cache_key = (str(home or ""), str(away or ""))
    if cache_key in cache:
        return cache[cache_key]

    result = (
        normalize_team_name(home, shared_state),
        normalize_team_name(away, shared_state),
    )
    cache[cache_key] = result
    return result


def maybe_learn_team_alias(
    raw_name: str,
    api_name: str,
    score: int,
    shared_state: dict | None = None,
    min_learn_score: int = 94,
):
    shared_state = ensure_shared_state_defaults(shared_state)
    aliases = get_team_aliases(shared_state)

    raw_clean = normalize_whitespace(_pre_clean_team_name(raw_name))
    api_canon = normalize_team_name(api_name, shared_state)

    if not raw_clean or not api_canon:
        return

    if len(raw_clean) < 3 or len(api_canon) < 3:
        return

    if raw_clean in aliases and aliases[raw_clean] == api_canon:
        return

    if score >= min_learn_score:
        aliases[raw_clean] = api_canon
        shared_state["team_aliases_dirty"] = True
        shared_state["normalized_team_cache"].clear()
        shared_state["similarity_cache"].clear()
        shared_state["canonical_pair_cache"].clear()
        debug_log(f"team alias learned | '{raw_clean}' -> '{api_canon}' | score={score}")


def extract_fixture_team_names(fixture: dict) -> tuple[str, str]:
    if not isinstance(fixture, dict):
        return "", ""

    home = fixture.get("home_name", "") or fixture.get("homeTeam", "") or fixture.get("home", "")
    away = fixture.get("away_name", "") or fixture.get("awayTeam", "") or fixture.get("away", "")

    if isinstance(home, dict):
        home = home.get("name", "")
    if isinstance(away, dict):
        away = away.get("name", "")

    if not home or not away:
        teams = fixture.get("teams", {}) or {}
        home = home or ((teams.get("home") or {}).get("name", ""))
        away = away or ((teams.get("away") or {}).get("name", ""))

    return str(home or ""), str(away or "")


def get_fixture_status(fixture: dict) -> str:
    if not isinstance(fixture, dict):
        return ""

    fx = fixture.get("fixture") or {}
    status = fx.get("status") or {}
    short = status.get("short")
    if short:
        return str(short)

    if fixture.get("status"):
        return str(fixture.get("status"))

    return ""


def get_fixture_score(fixture: dict) -> tuple[int | None, int | None]:
    if not isinstance(fixture, dict):
        return None, None

    goals = fixture.get("goals")
    if isinstance(goals, dict):
        home = goals.get("home")
        away = goals.get("away")
        if home is not None or away is not None:
            return home, away

    score = fixture.get("score") or {}
    full_time = score.get("fullTime") or {}
    home = full_time.get("home")
    away = full_time.get("away")
    if home is not None or away is not None:
        return home, away

    return None, None

def get_fixture_kickoff_dt(fixture: dict) -> datetime | None:
    if not isinstance(fixture, dict):
        return None

    # API-Football
    fx = fixture.get("fixture") or {}
    raw = fx.get("date")
    if raw:
        try:
            text = str(raw).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass

    # Dormant fallback shape (no longer produced by any active provider as
    # of Phase 27.4's football-data.org removal — left in place as a
    # harmless, generic fallback rather than touched, per that phase's
    # explicit "do not redesign the settlement engine" constraint).
    raw = fixture.get("utcDate")
    if raw:
        try:
            text = str(raw).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass

    return None


def should_try_result_update_from_fixture(
    fixture: dict,
    now_dt: datetime | None = None,
) -> tuple[bool, datetime | None]:
    kickoff_dt = get_fixture_kickoff_dt(fixture)
    if kickoff_dt is None:
        # Se não houver kickoff disponível, não bloqueamos
        return True, None

    now_dt = now_dt or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    return now_dt >= (kickoff_dt + RESULT_READY_DELAY), kickoff_dt


# =============================
# Postponed/cancelled/missing-fixture voiding — see ADR-017
# =============================

def parse_kickoff_utc(value) -> datetime | None:
    """Parses a row's own persisted KickoffUTC (the ORIGINAL scheduled
    kickoff — see try_update_row_via_api_football(), which only ever
    overwrites this field once a fixture is matched AND finished, so it
    stays stable for the entire lifetime of an unresolved void candidate).
    Returns None on empty/unparseable input — callers must treat that as
    "cannot safely compute an age", never as "age is zero"."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def hours_since(dt: datetime, now_dt: datetime | None = None) -> float:
    now_dt = now_dt or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    return (now_dt - dt).total_seconds() / 3600.0


def classify_af_status(status_upper: str) -> str:
    if status_upper in AF_FINISHED_STATUS:
        return "FINISHED"
    if status_upper in AF_NON_PLAYED_STATUS:
        return "NON_PLAYED"
    if status_upper in AF_IN_PROGRESS_STATUS:
        return "IN_PROGRESS"
    return "SCHEDULED_UNKNOWN"


def _parse_int(value, default: int = 0) -> int:
    try:
        s = str(value).strip()
        return int(s) if s else default
    except (TypeError, ValueError):
        return default


def void_result_row(df: pd.DataFrame, idx, row, reason: str) -> float:
    """Writes P (push/void) to a row using the exact same fields/formulas
    normal settlement writes (calc_profit/calc_real_profit — Part 9: no
    special-case arithmetic, reuse the existing, already-correct P handling)
    plus the additive SettlementReason audit field (Part 11). Returns the
    model profit written (always 0.0 for P)."""
    stake = parse_float(row.get("Stake€", ""), 0.0)
    odd = parse_float(row.get("Odd", ""), 0.0)

    lucro = calc_profit("P", stake, odd)
    df.at[idx, "Resultado"] = "P"
    df.at[idx, "Placar"] = ""
    df.at[idx, "Lucro€"] = str(lucro)
    df.at[idx, "SettlementReason"] = reason

    lucro_real = calc_real_profit(
        row.get("Apostada", ""),
        "P",
        parse_float(row.get("StakeReal€", ""), 0.0),
        parse_float(row.get("OddReal", ""), 0.0),
    )
    if lucro_real != "":
        df.at[idx, "LucroReal€"] = lucro_real

    return lucro


def attempt_rediscovery_af(
    league_code: str,
    home_csv: str,
    away_csv: str,
    original_kickoff_dt: datetime,
    shared_state: dict,
    label: str,
):
    """One bounded, forward-only wide-date search for a fixture that may
    have been rescheduled far enough from its original kickoff that the
    normal same-date (+/- 1 day) lookup never finds it (Part 5 — the
    Chicago Fire vs Vancouver Whitecaps case). Only ever called once a bet
    has become a *mature* missing-fixture void candidate (see
    _evaluate_missing_fixture_void()) — never on every settlement run for
    every open pick, so the extra API cost is bounded to rare stragglers,
    not multiplied across the whole board (Part 15).

    Searches AF only: by the time a row reaches this function, AF is always
    the provider that most recently said NO_MATCH (every league has an AF
    fallback — see league_registry.py — so a genuine NO_MATCH this deep into
    the pipeline was already an AF answer). Forward-only because postponed
    fixtures are rescheduled later, not earlier. Reuses
    fetch_api_football_fixtures_for_league_date()'s own per-run
    (league, date) cache, so multiple mature candidates in the same league
    share the same handful of extra requests.

    Returns the matched fixture dict, or None if nothing was found in the
    window. Team-name matching uses the exact same thresholds as every other
    match in this file (MATCH_MIN_TOTAL_SCORE/MATCH_MIN_SIDE_SCORE) — no
    loosening for this "last resort" search, per Part 5's explicit warning
    against fuzzy-matching a different fixture.
    """
    if not league_code or not home_csv or not away_csv:
        return None

    base_date = original_kickoff_dt.date()
    for offset in range(2, REDISCOVERY_MAX_FORWARD_DAYS + 1):
        date_str = (base_date + timedelta(days=offset)).isoformat()
        fixtures, _reason = fetch_api_football_fixtures_for_league_date(league_code, date_str, shared_state)
        if not fixtures:
            continue
        matched, score, meta = find_best_fixture_match(
            home_csv, away_csv, fixtures, shared_state,
            min_total_score=MATCH_MIN_TOTAL_SCORE, min_side_score=MATCH_MIN_SIDE_SCORE,
        )
        if matched:
            print(
                f"[DBG] {label}: rediscovery hit | '{home_csv} vs {away_csv}' | "
                f"league={league_code} | date={date_str} | score={score}"
            )
            return matched

    print(
        f"[DBG] {label}: rediscovery exhausted, nothing found | "
        f"'{home_csv} vs {away_csv}' | league={league_code} | "
        f"window=+2..+{REDISCOVERY_MAX_FORWARD_DAYS}d from {base_date.isoformat()}"
    )
    return None


def score_fixture_match(
    row_home: str,
    row_away: str,
    api_home: str,
    api_away: str,
    shared_state: dict | None = None,
) -> tuple[int, int, int]:
    hs = similarity_score(row_home, api_home, shared_state)
    aws = similarity_score(row_away, api_away, shared_state)

    row_home_c, row_away_c = canonical_pair(row_home, row_away, shared_state)
    api_home_c, api_away_c = canonical_pair(api_home, api_away, shared_state)

    bonus = 0

    if row_home_c == api_home_c:
        bonus += 10
    if row_away_c == api_away_c:
        bonus += 10

    if row_home_c and api_home_c and (row_home_c in api_home_c or api_home_c in row_home_c):
        bonus += 3
    if row_away_c and api_away_c and (row_away_c in api_away_c or api_away_c in row_away_c):
        bonus += 3

    total = hs + aws + bonus
    return total, hs, aws


def find_best_fixture_match(
    row_home: str,
    row_away: str,
    fixtures: list,
    shared_state: dict | None = None,
    min_total_score: int = MATCH_MIN_TOTAL_SCORE,
    min_side_score: int = MATCH_MIN_SIDE_SCORE,
):
    shared_state = ensure_shared_state_defaults(shared_state)

    if not fixtures:
        return None, 0, None

    row_home_c, row_away_c = canonical_pair(row_home, row_away, shared_state)

    exact_candidates = []
    for fx in fixtures:
        api_home, api_away = extract_fixture_team_names(fx)
        api_home_c, api_away_c = canonical_pair(api_home, api_away, shared_state)

        if row_home_c == api_home_c and row_away_c == api_away_c:
            total, hs, aws = score_fixture_match(
                row_home, row_away, api_home, api_away, shared_state
            )
            exact_candidates.append((total, hs, aws, fx, api_home, api_away))

    if exact_candidates:
        exact_candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        total, hs, aws, fx, api_home, api_away = exact_candidates[0]

        maybe_learn_team_alias(row_home, api_home, hs, shared_state)
        maybe_learn_team_alias(row_away, api_away, aws, shared_state)

        return fx, total, {
            "api_home": api_home,
            "api_away": api_away,
            "home_score": hs,
            "away_score": aws,
            "mode": "canonical_exact",
        }

    best = None
    best_meta = None
    best_score = -1

    for fx in fixtures:
        api_home, api_away = extract_fixture_team_names(fx)
        total, hs, aws = score_fixture_match(
            row_home, row_away, api_home, api_away, shared_state
        )

        if total > best_score:
            best_score = total
            best = fx
            best_meta = {
                "api_home": api_home,
                "api_away": api_away,
                "home_score": hs,
                "away_score": aws,
                "mode": "scored",
            }

    if best is None:
        return None, 0, None

    if best_meta["home_score"] < min_side_score or best_meta["away_score"] < min_side_score:
        if UPDATE_RESULTS_DEBUG:
            diag_log(
                f"match_reject side_score | row='{row_home} vs {row_away}' | "
                f"api='{best_meta['api_home']} vs {best_meta['api_away']}' | "
                f"total={best_score} | hs={best_meta['home_score']} | as={best_meta['away_score']} | "
                f"min_side={min_side_score}"
            )
        return None, best_score, best_meta

    if best_score < min_total_score:
        if UPDATE_RESULTS_DEBUG:
            diag_log(
                f"match_reject total_score | row='{row_home} vs {row_away}' | "
                f"api='{best_meta['api_home']} vs {best_meta['api_away']}' | "
                f"total={best_score} | min_total={min_total_score}"
            )
        return None, best_score, best_meta

    maybe_learn_team_alias(row_home, best_meta["api_home"], best_meta["home_score"], shared_state)
    maybe_learn_team_alias(row_away, best_meta["api_away"], best_meta["away_score"], shared_state)

    return best, best_score, best_meta


def log_no_match_candidates(
    prefix: str,
    row_home: str,
    row_away: str,
    fixtures: list,
    shared_state: dict | None = None,
    top_n: int = 3,
):
    scored = []
    for fx in fixtures or []:
        api_home, api_away = extract_fixture_team_names(fx)
        total, hs, aws = score_fixture_match(row_home, row_away, api_home, api_away, shared_state)
        scored.append((total, hs, aws, api_home, api_away, get_fixture_status(fx)))

    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    if not scored:
        debug_log(
            f"{prefix}: NO CANDIDATES — API returned 0 fixtures for this league+date | "
            f"row='{row_home} vs {row_away}'"
        )
        return

    for total, hs, aws, api_home, api_away, status in scored[:top_n]:
        side_problems = []
        if hs < MATCH_MIN_SIDE_SCORE:
            side_problems.append(f"hs={hs}<{MATCH_MIN_SIDE_SCORE}")
        if aws < MATCH_MIN_SIDE_SCORE:
            side_problems.append(f"aws={aws}<{MATCH_MIN_SIDE_SCORE}")

        if not side_problems and total >= MATCH_MIN_TOTAL_SCORE:
            verdict = "WOULD_MATCH"
        elif side_problems:
            verdict = f"REJECTED(side_score: {', '.join(side_problems)})"
        else:
            verdict = f"REJECTED(total_score: {total}<{MATCH_MIN_TOTAL_SCORE})"

        debug_log(
            f"{prefix}: candidato | "
            f"row='{row_home} vs {row_away}' | api='{api_home} vs {api_away}' | "
            f"total={total} | hs={hs} | aws={aws} | status={status} | {verdict}"
        )


def parse_float(v, default=0.0) -> float:
    try:
        s = str(v).strip().replace(",", ".")
        if s == "":
            return float(default)
        return float(s)
    except Exception:
        return float(default)


def normalize_text(s: str) -> str:
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.replace("&", " and ")
    s = s.replace("-", " ")
    s = re.sub(r"\b(fc|cf|sc|sv|afc|sad|club|deportivo|futebol|football|calcio|fk|ac)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def split_game(game: str):
    game = str(game).strip()
    if " vs " not in game:
        return None, None
    a, b = game.split(" vs ", 1)
    return a.strip(), b.strip()


def team_match_score(a: str, b: str) -> int:
    na = normalize_text(a)
    nb = normalize_text(b)

    if not na or not nb:
        return 0

    if na == nb:
        return 100

    sa = set(na.split())
    sb = set(nb.split())

    if not sa or not sb:
        return 0

    inter = len(sa & sb)
    if inter == 0:
        return 0

    score = inter * 10

    if na in nb or nb in na:
        score += 20

    ta = na.split()
    tb = nb.split()

    if ta and tb and ta[0] == tb[0]:
        score += 5
    if ta and tb and ta[-1] == tb[-1]:
        score += 5

    return score


def choose_best_match(csv_home: str, csv_away: str, matches: list[dict]):
    best = None
    best_score = -1

    for m in matches:
        api_home = str(m.get("homeTeam", {}).get("name", "")).strip()
        api_away = str(m.get("awayTeam", {}).get("name", "")).strip()

        direct_home = team_match_score(csv_home, api_home)
        direct_away = team_match_score(csv_away, api_away)
        direct_total = direct_home + direct_away

        reverse_home = team_match_score(csv_home, api_away)
        reverse_away = team_match_score(csv_away, api_home)
        reverse_total = reverse_home + reverse_away

        total = max(direct_total, reverse_total)

        if direct_home >= 10 and direct_away >= 10 and total > best_score:
            best = m
            best_score = total

    return best, best_score


def choose_best_api_football_match(csv_home: str, csv_away: str, fixtures: list[dict]):
    best = None
    best_score = -1

    for item in fixtures:
        teams = item.get("teams", {}) or {}
        api_home = str((teams.get("home") or {}).get("name", "")).strip()
        api_away = str((teams.get("away") or {}).get("name", "")).strip()

        direct_home = team_match_score(csv_home, api_home)
        direct_away = team_match_score(csv_away, api_away)
        direct_total = direct_home + direct_away

        reverse_home = team_match_score(csv_home, api_away)
        reverse_away = team_match_score(csv_away, api_home)
        reverse_total = reverse_home + reverse_away

        total = max(direct_total, reverse_total)

        if direct_home >= 10 and direct_away >= 10 and total > best_score:
            best = item
            best_score = total

    return best, best_score


def market_result(market: str, home_goals: int, away_goals: int):
    total = int(home_goals) + int(away_goals)
    m = str(market).strip().upper()

    if m == "O1.5":
        return "W" if total >= 2 else "L"

    if m == "O2.5":
        return "W" if total >= 3 else "L"

    if m == "O3.5":
        return "W" if total >= 4 else "L"

    if m == "BTTS":
        return "W" if int(home_goals) >= 1 and int(away_goals) >= 1 else "L"

    return None


def calc_profit(resultado: str, stake: float, odd: float) -> float:
    if resultado == "W":
        return round(stake * (odd - 1.0), 2)
    if resultado == "L":
        return round(-stake, 2)
    if resultado == "P":
        return 0.0
    return 0.0


def calc_real_profit(apostada: str, resultado: str, stake_real: float, odd_real: float):
    ap = str(apostada).strip().lower()
    if ap not in {"sim", "s", "yes", "y", "1", "true"}:
        return ""

    if stake_real <= 0 or odd_real <= 1.01:
        return ""

    if resultado == "W":
        return str(round(stake_real * (odd_real - 1.0), 2))
    if resultado == "L":
        return str(round(-stake_real, 2))
    if resultado == "P":
        return "0.0"
    return ""


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in CSV_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[CSV_COLUMNS].fillna("").copy()



def safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=CSV_COLUMNS)

    try:
        if path.stat().st_size == 0:
            return pd.DataFrame(columns=CSV_COLUMNS)

        df = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8").fillna("")
        return ensure_columns(df)

    except Exception as e:
        print(f"[WARN] Erro a ler {path.name} com ponto-e-vírgula: {e}")
        try:
            df = pd.read_csv(path, sep=",", dtype=str, encoding="utf-8").fillna("")
            return ensure_columns(df)
        except Exception as e2:
            print(f"[CRITICAL] Falha total a ler {path.name}: {e2}")
            # Se for o ficheiro de histórico e existir, lançamos erro para não sobrescrever com vazio
            if "history" in str(path).lower():
                raise RuntimeError(f"Impossível ler histórico em {path}. Abortando para evitar perda de dados.")
            return pd.DataFrame(columns=CSV_COLUMNS)


def get_today_lisbon_iso() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Lisbon")).date().isoformat()
    except Exception:
        return datetime.utcnow().date().isoformat()


def _cached_date_obj(date_str: str, shared_state: dict | None = None):
    shared_state = ensure_shared_state_defaults(shared_state)
    cache = shared_state["date_parse_cache"]
    key = str(date_str or "")

    if key not in cache:
        dt = pd.to_datetime(key, errors="coerce")
        cache[key] = None if pd.isna(dt) else dt.date()

    return cache[key]


def is_future_date(date_str: str, today_iso: str, shared_state: dict | None = None) -> bool:
    d = _cached_date_obj(date_str, shared_state)
    if d is None:
        return False
    return d.isoformat() > today_iso


def make_row_key_from_values(data: str, liga: str, jogo: str, mercado: str) -> str:
    return "||".join([
        str(data or "").strip(),
        str(liga or "").strip(),
        str(jogo or "").strip(),
        str(mercado or "").strip().upper(),
    ])


def make_row_key(row) -> str:
    return make_row_key_from_values(
        row.get("Data", ""),
        row.get("Liga", ""),
        row.get("Jogo", ""),
        row.get("Mercado", ""),
    )


def api_football_season_from_date(
    date_str: str,
    league_id: int | None = None,
    shared_state: dict | None = None,
) -> int:
    """Return the API-Football season integer for a given game date and league.

    Season model is looked up from AF_SEASON_MODELS via league_id:
      "calendar"  — season equals the calendar year of the game date (MLS, Nordic leagues, etc.)
      "european"  — season starts in July; Jan–Jun maps to year-1 (default for all EU leagues)
    """
    d = _cached_date_obj(date_str, shared_state)
    if d is None:
        now = datetime.utcnow()
        year, month = now.year, now.month
    else:
        year, month = int(d.year), int(d.month)

    model = AF_SEASON_MODELS.get(league_id, "european") if league_id is not None else "european"
    if model == "calendar":
        return year
    # european: July–December = current year, January–June = previous year
    return year if month >= 7 else year - 1


# =============================
# API-Football
# =============================
_af_last_api_call_ts = 0.0


def _respect_af_api_spacing():
    global _af_last_api_call_ts
    now = time.monotonic()
    elapsed = now - _af_last_api_call_ts
    if elapsed < AF_CALL_MIN_INTERVAL:
        time.sleep(AF_CALL_MIN_INTERVAL - elapsed)
    _af_last_api_call_ts = time.monotonic()


def http_get_json_api_football(url: str, token: str):
    req = request.Request(
        url,
        headers={
            "x-apisports-key": token,
            "Accept": "application/json",
            "User-Agent": "apostas-over-futebol/1.0",
        },
    )
    with request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_football_get(path: str, params: dict | None = None):
    params = params or {}
    query = parse.urlencode(params)
    url = f"{AF_BASE_URL}{path}"
    if query:
        url += f"?{query}"

    last_error = None

    for attempt in range(1, AF_MAX_RETRIES + 1):
        try:
            _respect_af_api_spacing()
            data = http_get_json_api_football(url, API_FOOTBALL_KEY)

            if attempt > 1:
                print(f"[DBG] API-Football retry sucesso | path={path} | tentativa={attempt}")

            # HTTP 200 does not mean the request succeeded — API-Football puts
            # plan/quota/auth rejections in `errors` while still returning 200
            # with an empty `response`. Without this check that is silently
            # indistinguishable from "no fixtures today".
            meaningful = _extract_meaningful_errors_field(data.get("errors") if isinstance(data, dict) else None)
            if meaningful:
                category, message = classify_provider_error(200, meaningful)
                raise ProviderError(build_provider_error(
                    provider="api-football", endpoint=url, request_params=params,
                    category=category, message=message,
                ))

            return data

        except ProviderError:
            raise

        except error.HTTPError as e:
            last_error = e
            code = getattr(e, "code", None)

            if code == 429 and attempt < AF_MAX_RETRIES:
                wait_s = AF_BASE_SLEEP * (2 ** (attempt - 1))
                print(
                    f"[WARN] API-Football rate limit 429 | path={path} | "
                    f"tentativa={attempt}/{AF_MAX_RETRIES} | espera={wait_s:.1f}s"
                )
                time.sleep(wait_s)
                continue

            raise

        except Exception as e:
            last_error = e

            if attempt < AF_MAX_RETRIES:
                wait_s = AF_BASE_SLEEP * attempt
                print(
                    f"[WARN] API-Football erro temporário | path={path} | "
                    f"tentativa={attempt}/{AF_MAX_RETRIES} | espera={wait_s:.1f}s | erro={e}"
                )
                time.sleep(wait_s)
                continue

            raise

    if last_error:
        raise last_error

    return {}


def get_api_football_league_id(league_code: str, date_str: str, shared_state: dict) -> int | None:
    if not API_FOOTBALL_KEY:
        return None

    conf = API_FOOTBALL_COMPETITIONS.get(league_code)
    if not conf:
        return None

    # Resolve hardcoded id first so the correct season model can be applied.
    hardcoded_id = conf.get("af_id")
    season = api_football_season_from_date(date_str, league_id=hardcoded_id, shared_state=shared_state)
    cache_key = (league_code, season)

    league_id_cache = shared_state["af_league_id_cache"]
    if cache_key in league_id_cache:
        return league_id_cache[cache_key]

    # Short-circuit: use the hardcoded AF league ID from the registry when available,
    # saving an API call to /leagues.
    if hardcoded_id:
        league_id_cache[cache_key] = int(hardcoded_id)
        print(
            f"[DBG] API-Football league id (registry) | code={league_code} | id={hardcoded_id}"
        )
        return int(hardcoded_id)

    country = conf["country"]
    target_name = conf["name"]

    try:
        data = api_football_get(
            "/leagues",
            {
                "country": country,
                "season": season,
            },
        )
        response = data.get("response", []) or []
    except ProviderError as pe:
        record_provider_error(shared_state, pe.record)
        print(f"[ERR] API-Football leagues lookup falhou | league={league_code} | season={season} | erro={pe}")
        league_id_cache[cache_key] = None
        return None
    except error.HTTPError as e:
        code = getattr(e, "code", None)
        message = _extract_message_from_http_error_body(_read_http_error_body(e))
        category, message = classify_provider_error(code, message)
        record_provider_error(shared_state, build_provider_error(
            provider="api-football", endpoint=f"{AF_BASE_URL}/leagues",
            request_params={"country": country, "season": season},
            category=category, message=message,
        ))
        print(f"[ERR] API-Football leagues lookup falhou | league={league_code} | season={season} | erro=HTTP {code}")
        league_id_cache[cache_key] = None
        return None
    except Exception as e:
        category = classify_provider_message(str(e))
        if category == "UNKNOWN":
            category = "NETWORK"
        record_provider_error(shared_state, build_provider_error(
            provider="api-football", endpoint=f"{AF_BASE_URL}/leagues",
            request_params={"country": country, "season": season},
            category=category, message=str(e),
        ))
        print(f"[ERR] API-Football leagues lookup falhou | league={league_code} | season={season} | erro={e}")
        league_id_cache[cache_key] = None
        return None

    best_id = None
    best_score = -1

    for item in response:
        league = item.get("league", {}) or {}
        league_id = league.get("id")
        league_name = str(league.get("name", "")).strip()

        if not league_id or not league_name:
            continue

        score = team_match_score(target_name, league_name)
        if score > best_score:
            best_score = score
            best_id = int(league_id)

    league_id_cache[cache_key] = best_id
    print(
        f"[DBG] API-Football league id lookup | code={league_code} | "
        f"season={season} | target='{target_name}' | id={best_id} | score={best_score}"
    )
    return best_id


def fetch_api_football_fixtures_for_league_date(league_code: str, date_str: str, shared_state: dict):
    if not API_FOOTBALL_KEY:
        return None, "NO_API_KEY"

    league_id = get_api_football_league_id(league_code, date_str, shared_state)
    if not league_id:
        return None, "NO_LEAGUE_ID"

    season = api_football_season_from_date(date_str, league_id=league_id, shared_state=shared_state)
    cache_key = (league_code, date_str, league_id, season)

    fixtures_cache = shared_state["af_fixtures_cache"]
    if cache_key in fixtures_cache:
        return fixtures_cache[cache_key]

    request_params = {"league": league_id, "season": season, "date": date_str}
    endpoint = f"{AF_BASE_URL}/fixtures"

    try:
        data = api_football_get("/fixtures", request_params)
        fixtures = data.get("response", []) or []
        fixtures_cache[cache_key] = (fixtures, "")
        record_provider_success(shared_state, "api-football")
        print(
            f"[DBG] API-Football fixtures | code={league_code} | league_id={league_id} | "
            f"season={season} | date={date_str} | jogos={len(fixtures)}"
        )
        return fixtures, ""

    except ProviderError as pe:
        record_provider_error(shared_state, pe.record)
        fixtures_cache[cache_key] = (None, "PROVIDER_ERROR")
        print(
            f"[ERR] API-Football fixtures falhou | code={league_code} | league_id={league_id} | "
            f"season={season} | date={date_str} | erro=PROVIDER_ERROR ({pe.record['category']})"
        )
        return None, "PROVIDER_ERROR"

    except error.HTTPError as e:
        code = getattr(e, "code", None)
        reason = f"HTTP {code}" if code is not None else "HTTP"
        message = _extract_message_from_http_error_body(_read_http_error_body(e))
        category, message = classify_provider_error(code, message)
        record_provider_error(shared_state, build_provider_error(
            provider="api-football", endpoint=endpoint, request_params=request_params,
            category=category, message=message,
        ))
        fixtures_cache[cache_key] = (None, reason)
        print(
            f"[ERR] API-Football fixtures falhou | code={league_code} | league_id={league_id} | "
            f"season={season} | date={date_str} | erro={reason}"
        )
        return None, reason

    except Exception as e:
        category = classify_provider_message(str(e))
        if category == "UNKNOWN":
            category = "NETWORK"
        record_provider_error(shared_state, build_provider_error(
            provider="api-football", endpoint=endpoint, request_params=request_params,
            category=category, message=str(e),
        ))
        fixtures_cache[cache_key] = (None, "OTHER")
        print(
            f"[ERR] API-Football fixtures falhou | code={league_code} | league_id={league_id} | "
            f"season={season} | date={date_str} | erro={e}"
        )
        return None, "OTHER"


# =============================
# GitHub upload
# =============================
def github_request(url: str, token: str, method: str = "GET", data: dict | None = None):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"token {token}",
        "User-Agent": "render-apostas-bot",
    }
    body = None

    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def github_get_sha(owner: str, repo: str, path: str, branch: str, token: str):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{parse.quote(path)}?ref={parse.quote(branch)}"
    try:
        j = github_request(url, token, method="GET")
        sha = j.get("sha")
        return sha if isinstance(sha, str) else None
    except error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def github_put_file(
    owner: str,
    repo: str,
    path: str,
    content_bytes: bytes,
    branch: str,
    token: str,
    message: str,
) -> None:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{parse.quote(path)}"
    sha = github_get_sha(owner, repo, path, branch, token)

    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    _ = github_request(url, token, method="PUT", data=payload)


def upload_csv_to_github(local_path: Path, remote_name: str) -> None:
    if not GITHUB_TOKEN:
        print("GitHub: GITHUB_TOKEN em falta, não atualizei o CSV no repositório.")
        return

    if not local_path.exists():
        print(f"GitHub: ficheiro não existe: {local_path.name}")
        return

    content = local_path.read_bytes()
    msg = f"Update {remote_name} ({datetime.now(timezone.utc).isoformat()}Z)"
    github_put_file(
        GITHUB_OWNER,
        GITHUB_REPO,
        remote_name,
        content,
        GITHUB_BRANCH,
        GITHUB_TOKEN,
        msg,
    )
    print(f"GitHub: atualizado {remote_name}")


def github_get_file_bytes(owner: str, repo: str, path: str, branch: str, token: str) -> bytes:
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/contents/"
        f"{parse.quote(path)}?ref={parse.quote(branch)}"
    )
    j = github_request(url, token, method="GET")
    content_b64 = j.get("content", "").replace("\n", "")
    return base64.b64decode(content_b64)


# =============================
# Sync history -> daily
# =============================
def sync_daily_from_history(daily_df: pd.DataFrame, history_df: pd.DataFrame):
    daily_df = ensure_columns(daily_df)
    history_df = ensure_columns(history_df)

    history_map = {}
    for _, row in history_df.iterrows():
        key = make_row_key(row)
        if not key.strip("|"):
            continue
        history_map[key] = row

    synced = 0

    for i, row in daily_df.iterrows():
        key = make_row_key(row)
        src = history_map.get(key)
        if src is None:
            continue

        changed = False
        for col in SYNC_RESULT_COLUMNS:
            src_val = str(src.get(col, "")).strip()
            dst_val = str(daily_df.at[i, col]).strip()

            if src_val != "" and src_val != dst_val:
                daily_df.at[i, col] = src_val
                changed = True

        resultado = str(daily_df.at[i, "Resultado"]).strip().upper()
        if resultado in {"W", "L", "P"}:
            lucro_real = calc_real_profit(
                daily_df.at[i, "Apostada"],
                resultado,
                parse_float(daily_df.at[i, "StakeReal€"], 0.0),
                parse_float(daily_df.at[i, "OddReal"], 0.0),
            )
            if lucro_real != "" and str(daily_df.at[i, "LucroReal€"]).strip() != lucro_real:
                daily_df.at[i, "LucroReal€"] = lucro_real
                changed = True

        if changed:
            synced += 1

    print(f"[DBG] sync daily<-history: {synced} linhas sincronizadas")
    return ensure_columns(daily_df), synced


# =============================
# Single row update via API-Football
# =============================
def try_update_row_via_api_football(
    df: pd.DataFrame,
    idx: int,
    row,
    league_code: str,
    label: str,
    shared_state: dict,
):
    data = str(row.get("Data", "")).strip()
    jogo = str(row.get("Jogo", "")).strip()
    mercado = str(row.get("Mercado", "")).strip()
    odd = parse_float(row.get("Odd", ""), 0.0)
    stake = parse_float(row.get("Stake€", ""), 0.0)

    home_csv, away_csv = split_game(jogo)
    if not home_csv or not away_csv:
        print(f"[WARN] {label}: Jogo mal formatado para fallback API-Football: {jogo}")
        return False, "BAD_GAME"

    fixtures, reason = fetch_api_football_fixtures_for_league_date(
        league_code,
        data,
        shared_state,
    )
    if fixtures is None:
        print(f"[WARN] {label}: API-Football sem fixtures para {jogo} | {league_code} | {data} | reason={reason}")
        log_pick_diag(
            label, idx, row, "api_football_fetch", reason or "NO_FIXTURES",
            league_code=league_code,
        )
        return False, reason or "NO_FIXTURES"

    log_pick_diag(
        label, idx, row, "api_football_fetch", "OK",
        league_code=league_code, fixtures=len(fixtures or []),
    )

    matched, best_score, meta = find_best_fixture_match(
        home_csv,
        away_csv,
        fixtures,
        shared_state,
        min_total_score=MATCH_MIN_TOTAL_SCORE,
        min_side_score=MATCH_MIN_SIDE_SCORE,
    )
    if not matched:
        # Late-kickoff fallback: US/Asian leagues with 23:00 UTC kickoffs are
        # sometimes stored in picks with date+1 (next day) rather than the API's UTC date.
        # Try fetching the previous calendar day to recover these games.
        try:
            prev_date = (datetime.strptime(data, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            fixtures_prev, _ = fetch_api_football_fixtures_for_league_date(league_code, prev_date, shared_state)
            if fixtures_prev:
                matched, best_score, meta = find_best_fixture_match(
                    home_csv, away_csv, fixtures_prev, shared_state,
                    min_total_score=MATCH_MIN_TOTAL_SCORE, min_side_score=MATCH_MIN_SIDE_SCORE,
                )
                if matched:
                    print(f"[DBG] {label}: date-1 fallback hit | {jogo} | {data} -> {prev_date}")
                    fixtures = fixtures_prev
        except Exception:
            pass
    if not matched:
        print(f"[WARN] {label}: API-Football sem match para: {jogo} | {league_code} | {data}")
        log_no_match_candidates(f"{label} API-Football", home_csv, away_csv, fixtures, shared_state)
        log_pick_diag(
            label, idx, row, "api_football_match", "NO_MATCH",
            league_code=league_code, fixtures=len(fixtures or []),
            best_score=best_score, meta=meta,
        )
        return False, "NO_MATCH"

    log_pick_diag(
        label, idx, row, "api_football_match", "MATCHED",
        league_code=league_code, best_score=best_score,
        match_mode=(meta or {}).get("mode", ""),
        match=format_fixture_diag(matched),
    )

    can_try_now, kickoff_dt = should_try_result_update_from_fixture(matched)
    if not can_try_now:
        kickoff_txt = kickoff_dt.isoformat() if kickoff_dt else "unknown"
        print(
            f"[DBG] {label}: API-Football ainda cedo para fechar: "
            f"{jogo} | kickoff_utc={kickoff_txt} | delay={RESULT_READY_DELAY}"
        )
        log_pick_diag(
            label, idx, row, "api_football_status", "TOO_EARLY",
            kickoff_utc=kickoff_txt, delay=str(RESULT_READY_DELAY),
            match=format_fixture_diag(matched),
        )
        return False, "TOO_EARLY"

    status = str(get_fixture_status(matched)).upper()
    if status not in AF_FINISHED_STATUS:
        classification = classify_af_status(status)
        if classification == "NON_PLAYED":
            original_kickoff_dt = parse_kickoff_utc(row.get("KickoffUTC", ""))
            if original_kickoff_dt and hours_since(original_kickoff_dt) >= POSTPONED_VOID_AFTER_HOURS:
                reason = AF_VOID_REASON_BY_STATUS.get(status, "postponed_timeout")
                void_result_row(df, idx, row, reason)
                log_pick_diag(
                    label, idx, row, "api_football_status", "VOIDED_NON_PLAYED_TIMEOUT",
                    status=status, void_reason=reason, match=format_fixture_diag(matched),
                )
                print(
                    f"[VOID] {label}: {jogo} auto-voided as P (status={status}, reason={reason}, "
                    f"kickoff+{POSTPONED_VOID_AFTER_HOURS:.0f}h elapsed)"
                )
                return True, "VOIDED_NON_PLAYED"
        print(f"[DBG] {label}: API-Football ainda não terminado: {jogo} | status={status}")
        log_pick_diag(
            label, idx, row, "api_football_status", "NOT_FINISHED",
            status=status, allowed=sorted(AF_FINISHED_STATUS),
            match=format_fixture_diag(matched),
        )
        return False, "NOT_FINISHED"

    kickoff_dt = get_fixture_kickoff_dt(matched)
    if kickoff_dt:
        df.at[idx, "KickoffUTC"] = kickoff_dt.isoformat()
    
    home_goals, away_goals = get_fixture_score(matched)
    if home_goals is None or away_goals is None:
        print(f"[WARN] {label}: API-Football sem goals finais para: {jogo}")
        log_pick_diag(
            label, idx, row, "api_football_score", "NO_SCORE",
            match=format_fixture_diag(matched),
        )
        return False, "NO_SCORE"

    resultado = market_result(mercado, int(home_goals), int(away_goals))
    if resultado is None:
        print(f"[WARN] {label}: Mercado não suportado no fallback API-Football: {mercado}")
        log_pick_diag(label, idx, row, "api_football_market", "UNSUPPORTED_MARKET")
        return False, "UNSUPPORTED_MARKET"

    lucro = calc_profit(resultado, stake, odd)
    df.at[idx, "Resultado"] = resultado
    df.at[idx, "Placar"] = f"{int(home_goals)}-{int(away_goals)}"
    df.at[idx, "Lucro€"] = str(lucro)

    lucro_real = calc_real_profit(
        row.get("Apostada", ""),
        resultado,
        parse_float(row.get("StakeReal€", ""), 0.0),
        parse_float(row.get("OddReal", ""), 0.0),
    )
    if lucro_real != "":
        df.at[idx, "LucroReal€"] = lucro_real

    log_pick_diag(
        label, idx, row, "api_football_write", "UPDATED",
        resultado=resultado, score=f"{home_goals}-{away_goals}",
        lucro=lucro, match=format_fixture_diag(matched),
    )

    print(
        f"[OK] {label}: API-Football fallback | {jogo} | {mercado} | "
        f"{home_goals}-{away_goals} => {resultado} | score_match={best_score} | "
        f"hs={meta['home_score']} | as={meta['away_score']} | mode={meta['mode']} | "
        f"Lucro modelo {lucro} | Lucro real {lucro_real if lucro_real != '' else 'n/a'}"
    )
    return True, "UPDATED"


# =============================
# Shared state
# =============================
def make_shared_runtime_state():
    shared_state = {
        "af_fixtures_cache": {},
        "af_league_id_cache": {},
    }
    return ensure_shared_state_defaults(shared_state)


# =============================
# Core update
# =============================
def _evaluate_missing_fixture_void(df: pd.DataFrame, idx, row, label: str, shared_state: dict):
    """Part 4/5 (ADR-017) — the persistent-missing-fixture safeguard.

    Callers must only invoke this when THIS run's own provider lookup for
    this row concluded with a genuine NO_MATCH (fixtures were fetched
    successfully; none matched) — never on a provider error, which is a
    different reason string entirely and is never routed here. That is what
    satisfies Part 4's safety rule: a failed API request/provider outage is
    never counted as evidence the fixture itself is missing.

    Returns "voided" (wrote P), "settled" (the bounded rediscovery search
    found the fixture already finished and wrote a real W/L), or None (still
    unresolved — either not enough evidence yet, or rediscovery found a
    genuinely rescheduled-but-not-finished fixture and the row should keep
    waiting on it normally).
    """
    original_kickoff_dt = parse_kickoff_utc(row.get("KickoffUTC", ""))
    if not original_kickoff_dt:
        # No reliable original kickoff to measure age from — never auto-void.
        return None

    prev_attempts = _parse_int(row.get("MissingAttempts", ""), 0)
    attempts = prev_attempts + 1
    df.at[idx, "MissingAttempts"] = str(attempts)

    age_hours = hours_since(original_kickoff_dt)
    if age_hours < MISSING_FIXTURE_VOID_AFTER_HOURS:
        return None
    if attempts < MISSING_FIXTURE_MIN_ATTEMPTS:
        return None

    # Mature candidate: time threshold + repeated genuine-NO_MATCH evidence
    # both satisfied. One bounded, final rediscovery attempt before voiding.
    jogo = str(row.get("Jogo", "")).strip()
    home_csv, away_csv = split_game(jogo)
    league_code = LEAGUE_CODE_MAP.get(str(row.get("Liga", "")).strip())

    rediscovered = attempt_rediscovery_af(
        league_code, home_csv, away_csv, original_kickoff_dt, shared_state, label,
    )

    if rediscovered is not None:
        status = str(get_fixture_status(rediscovered)).upper()
        if status in AF_FINISHED_STATUS:
            home_goals, away_goals = get_fixture_score(rediscovered)
            if home_goals is not None and away_goals is not None:
                mercado = str(row.get("Mercado", "")).strip()
                resultado = market_result(mercado, int(home_goals), int(away_goals))
                if resultado is not None:
                    stake = parse_float(row.get("Stake€", ""), 0.0)
                    odd = parse_float(row.get("Odd", ""), 0.0)
                    lucro = calc_profit(resultado, stake, odd)
                    df.at[idx, "Resultado"] = resultado
                    df.at[idx, "Placar"] = f"{int(home_goals)}-{int(away_goals)}"
                    df.at[idx, "Lucro€"] = str(lucro)
                    lucro_real = calc_real_profit(
                        row.get("Apostada", ""), resultado,
                        parse_float(row.get("StakeReal€", ""), 0.0),
                        parse_float(row.get("OddReal", ""), 0.0),
                    )
                    if lucro_real != "":
                        df.at[idx, "LucroReal€"] = lucro_real
                    df.at[idx, "MissingAttempts"] = "0"
                    print(
                        f"[OK] {label}: rediscovered rescheduled fixture (wide search) | "
                        f"{jogo} | {mercado} | {home_goals}-{away_goals} => {resultado}"
                    )
                    return "settled"
        # Found but not (yet) finished — genuinely rescheduled, not missing.
        # Stop counting it as missing; keep waiting for it normally. Its
        # KickoffUTC/Data are deliberately left untouched (see ADR-017) — the
        # next mature-candidate check simply re-runs this same rediscovery
        # rather than relying on the narrow date-based fetch to find a
        # fixture that moved to a different date.
        df.at[idx, "MissingAttempts"] = "0"
        print(
            f"[DBG] {label}: rediscovery found a not-yet-finished rescheduled fixture | "
            f"{jogo} | status={status} — will keep waiting"
        )
        return None

    # No rescheduled fixture found even in the bounded wide window —
    # sufficient evidence (time + repeated attempts + one final rediscovery)
    # to void.
    void_result_row(df, idx, row, MISSING_FIXTURE_VOID_REASON)
    print(
        f"[VOID] {label}: {jogo} auto-voided as P ({MISSING_FIXTURE_VOID_REASON}, "
        f"attempts={attempts}, age={age_hours:.1f}h)"
    )
    return "voided"


def update_dataframe(df: pd.DataFrame, label: str, shared_state: dict):
    df = ensure_columns(df)
    shared_state = ensure_shared_state_defaults(shared_state)

    today_iso = get_today_lisbon_iso()

    updated = 0
    ignored = 0
    already_done = 0
    unsupported_market = 0
    missing_mapping = 0
    no_match_found = 0
    not_finished = 0
    future_skipped = 0

    af_used = 0
    af_updated = 0
    af_failed = 0

    diag_counts = {} if UPDATE_RESULTS_DEBUG else None

    def _diag_count(reason: str):
        if diag_counts is not None:
            diag_counts[reason] = diag_counts.get(reason, 0) + 1

    def _run_af_and_account(idx, row_obj, lg_code, provider_label):
        """Shared body for all three try_update_row_via_api_football() call
        sites below (direct, fallback-after-FD-error, fallback-after-FD-
        no-match) — previously near-identical ~15-line blocks duplicated
        three times. Also the single place that routes a genuine AF
        NO_MATCH into the missing-fixture void safeguard (Part 4/5), so
        that safeguard applies identically regardless of which of the three
        paths produced the NO_MATCH."""
        nonlocal updated, af_used, af_updated, af_failed, ignored
        nonlocal future_skipped, not_finished, no_match_found, unsupported_market

        af_used += 1
        log_pick_diag(label, idx, row_obj, "provider", provider_label, league_code=lg_code)

        ok, reason = try_update_row_via_api_football(df, idx, row_obj, lg_code, label, shared_state)
        if ok:
            updated += 1
            af_updated += 1
            _diag_count("UPDATED_API_FOOTBALL")
            return

        if reason == "NO_MATCH":
            outcome = _evaluate_missing_fixture_void(df, idx, row_obj, label, shared_state)
            if outcome:
                updated += 1
                af_updated += 1
                _diag_count("RESETTLED_VIA_REDISCOVERY" if outcome == "settled" else "VOIDED_MISSING_FIXTURE")
                return

        if reason == "TOO_EARLY":
            future_skipped += 1
        elif reason == "NOT_FINISHED":
            not_finished += 1
        elif reason == "NO_MATCH":
            no_match_found += 1
        elif reason == "UNSUPPORTED_MARKET":
            unsupported_market += 1
        af_failed += 1
        ignored += 1
        _diag_count(f"AF_{reason}")
        log_pick_diag(label, idx, row_obj, "provider_result", reason, provider="api_football")

    for i, row in df.iterrows():
        resultado_atual = str(row.get("Resultado", "")).strip().upper()

        if resultado_atual in {"W", "L", "P"}:
            already_done += 1
            _diag_count("ALREADY_DONE")
            log_pick_diag(label, i, row, "precheck", "ALREADY_DONE", resultado=resultado_atual)

            lucro_real = calc_real_profit(
                row.get("Apostada", ""),
                resultado_atual,
                parse_float(row.get("StakeReal€", ""), 0.0),
                parse_float(row.get("OddReal", ""), 0.0),
            )
            if lucro_real != "":
                df.at[i, "LucroReal€"] = lucro_real

            continue

        data = str(row.get("Data", "")).strip()
        liga = str(row.get("Liga", "")).strip()
        jogo = str(row.get("Jogo", "")).strip()
        mercado = str(row.get("Mercado", "")).strip()
        odd = parse_float(row.get("Odd", ""), 0.0)
        stake = parse_float(row.get("Stake€", ""), 0.0)

        if not data or not liga or not jogo or odd <= 1.01 or stake <= 0:
            ignored += 1
            _diag_count("INVALID_ROW")
            log_pick_diag(
                label, i, row, "precheck", "INVALID_ROW",
                odd=odd, stake=stake,
            )
            continue
        kickoff_str = row.get("KickoffUTC", "")
        if kickoff_str:
            try:
                kickoff_dt = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if kickoff_dt.tzinfo is None:
                    kickoff_dt = kickoff_dt.replace(tzinfo=timezone.utc)

                now_utc = datetime.now(timezone.utc)

                if now_utc < kickoff_dt + RESULT_READY_DELAY:
                    future_skipped += 1
                    ignored += 1
                    _diag_count("KICKOFF_TOO_EARLY")
                    log_pick_diag(
                        label, i, row, "precheck", "KICKOFF_TOO_EARLY",
                        kickoff_utc=kickoff_dt.isoformat(),
                        now_utc=now_utc.isoformat(),
                        delay=str(RESULT_READY_DELAY),
                    )
                    continue
            except Exception as kickoff_err:
                log_pick_diag(
                    label, i, row, "precheck", "KICKOFF_PARSE_ERROR",
                    kickoff_raw=kickoff_str, error=str(kickoff_err),
                )

        if str(mercado).strip().upper() not in SUPPORTED_MARKETS:
            print(f"[WARN] {label}: Mercado não suportado: {mercado}")
            unsupported_market += 1
            ignored += 1
            _diag_count("UNSUPPORTED_MARKET")
            log_pick_diag(label, i, row, "precheck", "UNSUPPORTED_MARKET")
            continue

        if is_future_date(data, today_iso, shared_state):
            future_skipped += 1
            ignored += 1
            _diag_count("FUTURE_DATE")
            log_pick_diag(
                label, i, row, "precheck", "FUTURE_DATE",
                today_lisbon=today_iso, pick_date=data,
            )
            continue

        league_code = LEAGUE_CODE_MAP.get(liga)
        if not league_code:
            print(f"[WARN] {label}: Liga sem mapping: {liga}")
            missing_mapping += 1
            ignored += 1
            _diag_count("MISSING_LEAGUE_MAP")
            log_pick_diag(label, i, row, "precheck", "MISSING_LEAGUE_MAP")
            continue

        home_csv, away_csv = split_game(jogo)
        if not home_csv or not away_csv:
            print(f"[WARN] {label}: Jogo mal formatado: {jogo}")
            ignored += 1
            _diag_count("BAD_GAME_FORMAT")
            log_pick_diag(label, i, row, "precheck", "BAD_GAME_FORMAT")
            continue

        log_pick_diag(
            label, i, row, "precheck", "ELIGIBLE",
            league_code=league_code, home=home_csv, away=away_csv,
        )

        # API-Football is the sole result provider (Phase 27.4 — see
        # docs/09_Architecture_Decisions.md ADR-004 update). Every eligible
        # row resolves through exactly one path: League -> API-Football ->
        # Settlement. _run_af_and_account() already fully accounts for the
        # NO_MATCH -> missing-fixture-void routing, TOO_EARLY/NOT_FINISHED/
        # NO_MATCH/UNSUPPORTED_MARKET bookkeeping, and updated/ignored
        # counters — nothing else is needed here.
        _run_af_and_account(i, row, league_code, "API_FOOTBALL")

    print(
        f"[DBG] {label} resumo -> "
        f"updated={updated} | already_done={already_done} | ignored={ignored} | "
        f"missing_mapping={missing_mapping} | unsupported_market={unsupported_market} | "
        f"no_match_found={no_match_found} | not_finished={not_finished} | "
        f"future_skipped={future_skipped} | "
        f"af_used={af_used} | af_updated={af_updated} | af_failed={af_failed}"
    )
    if diag_counts is not None:
        diag_log(f"{label} decision_counts={dict(sorted(diag_counts.items()))}")

    return ensure_columns(df), updated, already_done, ignored


# =============================
# Manual bets — cloud_state.json bridge
# =============================

def _normalize_market_code(raw: str) -> str:
    """Map any market representation to its canonical SUPPORTED_MARKETS code."""
    s = str(raw or '').strip().upper().replace(' ', '').replace('_', '').replace('.', '')
    if s in {'O15', 'OVER15', 'OVER1,5'}:
        return 'O1.5'
    if s in {'O25', 'OVER25', 'OVER2,5'}:
        return 'O2.5'
    if s in {'O35', 'OVER35', 'OVER3,5'}:
        return 'O3.5'
    if s in {'BTTS', 'BTTSY', 'AMBASMARCAM', 'BOTHTEAMSTOSCORE', 'YES'}:
        return 'BTTS'
    return str(raw or '').strip().upper()


def _resolve_liga_display_name(liga_raw: str) -> str:
    """Convert any liga representation (canonical key, display name, alias)
    to the display name that LEAGUE_CODE_MAP is keyed on.

    Manual bets from the Scout UI use canonical keys ('mls', 'finlandia').
    The free-text form accepts display names ('MLS', 'Premier League').
    LEAGUE_CODE_MAP keys are always display names.
    """
    if liga_raw in LEAGUE_CODE_MAP:
        return liga_raw
    entry = REGISTRY_BY_KEY.get(liga_raw.lower())
    if entry:
        return entry.name
    lower = liga_raw.lower()
    for name in LEAGUE_CODE_MAP:
        if name.lower() == lower:
            return name
    return liga_raw


def manual_bets_to_settlement_df(manual_bets: list) -> pd.DataFrame:
    """Convert cloud_state.json manualBets list to a DataFrame for update_dataframe().

    Row order is preserved 1:1 so that apply_df_results_to_manual_bets() can write
    results back by index without any additional key matching.
    """
    rows = []
    for bet in manual_bets:
        liga_raw = str(bet.get('liga') or '').strip()
        rows.append({
            'Data':       str(bet.get('data')        or '').strip(),
            'Liga':       _resolve_liga_display_name(liga_raw),
            'Jogo':       str(bet.get('jogo')        or '').strip(),
            'Mercado':    _normalize_market_code(bet.get('mercado') or ''),
            'Odd':        str(bet.get('odd')         or '').strip(),
            'Stake€':     str(bet.get('stake')       or '').strip(),
            'Resultado':  str(bet.get('resultado')   or '').strip().upper(),
            'Placar':     str(bet.get('placar')      or '').strip(),
            'Lucro€':     str(bet.get('lucro')       or '').strip(),
            'KickoffUTC': str(bet.get('kickoffUTC')  or '').strip(),
            'Edge%':      '',
            'Apostada':   'sim',
            'OddReal':    '',
            'StakeReal€': '',
            'LucroReal€': '',
            # Round-tripped exactly like Placar/KickoffUTC above (Phase
            # 26.19/26.32 precedent): MissingAttempts is the persisted
            # evidence counter the missing-fixture void safeguard (Part 4,
            # ADR-017) requires to survive across settlement runs — without
            # this bridge it would silently reset to 0 every run and the
            # safeguard would never mature for manual bets.
            'MissingAttempts': str(bet.get('missingAttempts') or '').strip(),
            'SettlementReason': str(bet.get('settlementReason') or '').strip(),
        })
    if not rows:
        return pd.DataFrame(columns=CSV_COLUMNS)

    return ensure_columns(pd.DataFrame(rows))


def apply_df_results_to_manual_bets(manual_bets: list, df: pd.DataFrame) -> tuple[int, int]:
    """Write settled results from the settlement DataFrame back into the bet dicts.

    Returns (newly_settled, evidence_changed):
      - newly_settled: bets that transitioned from unsettled -> W/L/P this run.
      - evidence_changed: bets whose MissingAttempts counter changed this run
        (incremented, or reset to 0 by a rediscovery — see
        _evaluate_missing_fixture_void() in update_dataframe()), REGARDLESS
        of whether they also got a final result. This must be tracked
        separately from newly_settled: the missing-fixture safeguard's
        "repeated attempts" evidence (Part 4/ADR-017) only works if the
        counter survives across runs for a bet that is *still unresolved* —
        callers must save cloud_state.json whenever this is > 0, not only
        when newly_settled > 0.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    newly_settled = 0
    evidence_changed = 0
    for i, bet in enumerate(manual_bets):
        if i >= len(df):
            break

        if 'MissingAttempts' in df.columns:
            new_attempts_str = str(df.at[i, 'MissingAttempts']).strip()
            old_attempts = _parse_int(bet.get('missingAttempts'), 0)
            new_attempts = _parse_int(new_attempts_str, old_attempts)
            if new_attempts != old_attempts:
                bet['missingAttempts'] = new_attempts
                evidence_changed += 1

        old_res = str(bet.get('resultado', '')).strip().upper()
        if old_res in {'W', 'L', 'P'}:
            continue
        new_res = str(df.at[i, 'Resultado']).strip().upper()
        if new_res not in {'W', 'L', 'P'}:
            continue
        lucro_str = str(df.at[i, 'Lucro€']).strip()
        placar_str = str(df.at[i, 'Placar']).strip() if 'Placar' in df.columns else ''
        reason_str = str(df.at[i, 'SettlementReason']).strip() if 'SettlementReason' in df.columns else ''
        bet['resultado'] = new_res
        try:
            bet['lucro'] = round(float(lucro_str), 2) if lucro_str else None
        except ValueError:
            bet['lucro'] = None
        if placar_str:
            bet['placar'] = placar_str
        if reason_str:
            bet['settlementReason'] = reason_str
        # Settlement result (resultado/lucro/placar) is independent from the bet's
        # lifecycle status (see ADR-012). 'rejected' is a terminal lifecycle state —
        # a rejected bet still gets settled analytically, but never becomes 'settled'.
        # Every other lifecycle status ('pending', 'approved') transitions to 'settled'
        # exactly as before.
        if bet.get('status') != 'rejected':
            bet['status'] = 'settled'
        bet['settledAt'] = now_iso
        newly_settled += 1
        print(
            f"[OK] manual settled | {bet.get('jogo', '?')} | {bet.get('mercado', '?')} | "
            f"resultado={new_res} | lucro={bet.get('lucro')}"
        )
    return newly_settled, evidence_changed


def load_cloud_state_from_github() -> dict:
    """Download and parse cloud_state.json from GitHub. Returns {} on 404 or error."""
    try:
        raw = github_get_file_bytes(GITHUB_OWNER, GITHUB_REPO, CLOUD_STATE_NAME, GITHUB_BRANCH, GITHUB_TOKEN)
        text = raw.decode("utf-8") if raw else ""
        return json.loads(text) if text.strip() else {}
    except error.HTTPError as e:
        if getattr(e, "code", None) == 404:
            print(f"[WARN] {CLOUD_STATE_NAME} not found on GitHub — no manual bets to settle")
            return {}
        raise


def save_cloud_state_to_github(content: dict, message: str) -> None:
    """Upload cloud_state.json to GitHub via the existing github_put_file helper."""
    text = json.dumps(content, ensure_ascii=False, indent=2)
    github_put_file(
        GITHUB_OWNER, GITHUB_REPO, CLOUD_STATE_NAME,
        text.encode("utf-8"), GITHUB_BRANCH, GITHUB_TOKEN, message,
    )
    print(f"[settlement] {CLOUD_STATE_NAME} saved to GitHub")


# =============================
# Provider health (persisted in cloud_state.json — see ADR-011)
# =============================
def update_provider_health(cloud_state: dict, shared_state: dict) -> dict:
    """Update cloud_state['providerHealth'] from this run's provider
    successes/errors. Only providers actually contacted this run are
    touched; providers not used this run keep their previous entry as-is.

    A provider's status flips to "warning" after
    PROVIDER_HEALTH_WARNING_THRESHOLD consecutive failing runs, and resets
    to "ok" on the next run where that provider succeeds at least once.
    """
    health = cloud_state.get("providerHealth")
    if not isinstance(health, dict):
        health = {}

    now_iso = datetime.now(timezone.utc).isoformat()

    errors_by_provider = {}
    for rec in shared_state.get("provider_errors", []):
        # last one wins — most recent error for that provider this run
        errors_by_provider[rec["provider"]] = rec

    success_seen = set(shared_state.get("provider_success_seen", set()))
    touched = success_seen | set(errors_by_provider.keys())

    for provider in touched:
        entry = dict(health.get(provider, {}))
        if provider in errors_by_provider:
            entry["consecutiveFailures"] = int(entry.get("consecutiveFailures", 0)) + 1
            entry["lastError"] = errors_by_provider[provider]
            entry["lastCheckedAt"] = now_iso
            entry["status"] = (
                "warning" if entry["consecutiveFailures"] >= PROVIDER_HEALTH_WARNING_THRESHOLD
                else entry.get("status", "ok")
            )
        else:
            entry["consecutiveFailures"] = 0
            entry["status"] = "ok"
            entry["lastSuccessAt"] = now_iso
            entry["lastCheckedAt"] = now_iso
        health[provider] = entry

    cloud_state["providerHealth"] = health
    return health


def pick_primary_provider_error(provider_errors: list) -> dict | None:
    """Choose the error to surface as THE reason settlement found nothing.
    Non-retryable errors (plan/auth/invalid-request — things a retry won't
    fix) are more informative than a transient network/quota blip, so they
    take priority; otherwise the first error recorded wins."""
    if not provider_errors:
        return None
    for rec in provider_errors:
        if not rec.get("retryable"):
            return rec
    return provider_errors[0]


def build_settlement_result(total_updated: int, total_ignored: int, duration: float, shared_state: dict) -> dict:
    """Assembles the /run-settlement response dict. When the provider layer
    failed and nothing got settled, this replaces the ambiguous "0 updated"
    result with an explicit, categorized abort reason instead of letting the
    caller infer "no matches to settle" from an empty count."""
    result = {
        "ok": True,
        "updated": total_updated,
        "ignored": total_ignored,
        "duration": duration,
    }

    provider_errors = shared_state.get("provider_errors", [])
    if provider_errors:
        result["provider_errors"] = provider_errors

        if total_updated == 0:
            worst = pick_primary_provider_error(provider_errors)
            result["settlement_aborted"] = True
            result["abort_provider"] = worst["provider"]
            result["abort_category"] = worst["category"]
            result["abort_reason"] = worst["message"]
            print(
                "\n[settlement] Settlement aborted.\n"
                f"Reason: {worst['provider']} rejected the fixture request.\n"
                f"Category: {worst['category']}\n"
            )

    return result


# =============================
# Remote settlement (called by sync_server.py)
# =============================
def run_settlement_remote() -> dict:
    """Download bot CSVs from GitHub, run settlement, upload results.
    Manual bets are read from cloud_state.json and written back there.

    Returns {"ok": True, "updated": N, "ignored": M, "duration": S.s}
    Raises RuntimeError if env vars are missing.
    """
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not set")
    if not API_FOOTBALL_KEY:
        raise RuntimeError("API_FOOTBALL_KEY not set — settlement cannot proceed")

    t0 = time.time()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        tmp_history = tmp / "picks_history.csv"
        tmp_daily   = tmp / "picks_hoje_simplificado.csv"

        for remote_name, local_path in [
            (REMOTE_HISTORY_NAME, tmp_history),
            (REMOTE_DAILY_NAME,   tmp_daily),
        ]:
            raw = github_get_file_bytes(GITHUB_OWNER, GITHUB_REPO, remote_name, GITHUB_BRANCH, GITHUB_TOKEN)
            local_path.write_bytes(raw)
            print(f"[settlement] downloaded {remote_name} ({len(raw)} bytes)")

        shared_state = make_shared_runtime_state()

        # ── Bot picks ─────────────────────────────────────────────────────────
        history_df = safe_read_csv(tmp_history)
        daily_df   = safe_read_csv(tmp_daily)

        history_df, h_updated, h_done, h_ignored = update_dataframe(history_df, "history", shared_state)
        history_df.to_csv(tmp_history, index=False, sep=";", encoding="utf-8")
        print(f"[settlement] history: updated={h_updated} done={h_done} ignored={h_ignored}")

        daily_df, d_updated, d_done, d_ignored = update_dataframe(daily_df, "daily", shared_state)
        daily_df, _ = sync_daily_from_history(daily_df, history_df)
        daily_df.to_csv(tmp_daily, index=False, sep=";", encoding="utf-8")
        print(f"[settlement] daily: updated={d_updated} done={d_done} ignored={d_ignored}")

        upload_csv_to_github(tmp_history, REMOTE_HISTORY_NAME)
        upload_csv_to_github(tmp_daily,   REMOTE_DAILY_NAME)

        save_team_alias_cache(shared_state)

    # ── Manual bets (cloud_state.json is the single source of truth) ──────────
    m_updated = 0
    m_done    = 0
    m_ignored = 0
    try:
        cloud_state = load_cloud_state_from_github()
        manual_bets = cloud_state.get("manualBets", [])
        newly_settled = 0
        evidence_changed = 0

        if manual_bets:
            manual_df = manual_bets_to_settlement_df(manual_bets)
            manual_df, m_updated, m_done, m_ignored = update_dataframe(manual_df, "manual", shared_state)
            newly_settled, evidence_changed = apply_df_results_to_manual_bets(manual_bets, manual_df)
            print(
                f"[settlement] manual: updated={m_updated} done={m_done} ignored={m_ignored} "
                f"newly_settled={newly_settled} evidence_changed={evidence_changed}"
            )

            if newly_settled > 0 or evidence_changed > 0:
                cloud_state["manualBets"] = manual_bets
        else:
            print("[settlement] manual: no manual bets in cloud_state.json")

        # Provider health must be persisted even when nothing settled — that is
        # exactly the run where a provider outage most needs to be visible.
        health_changed = bool(shared_state.get("provider_errors")) or bool(shared_state.get("provider_success_seen"))
        if health_changed:
            update_provider_health(cloud_state, shared_state)

        # evidence_changed alone (no new result, no health change) still needs
        # a save — it's the MissingAttempts counter accumulating for a manual
        # bet still in flight, and it must survive to the next run for the
        # missing-fixture safeguard (Part 4/ADR-017) to ever mature.
        if newly_settled > 0 or evidence_changed > 0 or health_changed:
            msg = (
                f"Settle {newly_settled} manual bet(s)" if newly_settled > 0
                else ("Update missing-fixture evidence" if evidence_changed > 0 else "Update provider health")
            ) + f" ({datetime.now(timezone.utc).isoformat()}Z)"
            save_cloud_state_to_github(cloud_state, msg)
    except Exception as exc:
        import traceback as _tb
        print(f"[WARN] manual settlement failed: {exc}")
        _tb.print_exc()

    duration = round(time.time() - t0, 1)
    total_updated = h_updated + d_updated + m_updated
    total_ignored = h_ignored + d_ignored + m_ignored

    print(f"[settlement] done in {duration}s — updated={total_updated} ignored={total_ignored}")

    return build_settlement_result(total_updated, total_ignored, duration, shared_state)


def _persist_league_stats(history_file: Path, league_stats_file: Path, remote_name: str) -> None:
    """Regenerates league_stats.csv from history_file and immediately uploads
    it — regeneration without persistence has zero effect, since GitHub
    Actions runners are ephemeral and a local-only write here is discarded
    the moment this job ends (this is the exact gap that left the
    dashboard's "Desempenho por Liga" frozen at a 2026-05-24 snapshot for
    months while picks_history.csv kept advancing — see
    docs/05_Known_Issues.md).

    Deliberately a single try/except around both steps, not two: this
    preserves the derived file's pre-existing failure tolerance exactly (a
    computation or upload problem here is logged and skipped, never allowed
    to abort settlement — history/daily settlement already succeeded above
    and must not be lost over an Analytics-file hiccup) while guaranteeing
    correct ordering by construction — upload can only ever run against
    freshly-regenerated content, never a stale prior copy.
    """
    try:
        update_league_stats(history_file, league_stats_file)
        upload_csv_to_github(league_stats_file, remote_name)
    except Exception as e:
        print(f"[WARN] falha a atualizar/persistir league_stats.csv -> {e}")


# =============================
# Main
# =============================
def main():
    print("[SETTLEMENT] Início — a actualizar resultados pendentes...")
    if not API_FOOTBALL_KEY:
        raise SystemExit("Falta API_FOOTBALL_KEY no Render")

    if UPDATE_RESULTS_DEBUG:
        diag_log(
            "debug mode ON | "
            f"today_lisbon={get_today_lisbon_iso()} | "
            f"result_delay={RESULT_READY_DELAY} | "
            f"match_thresholds total={MATCH_MIN_TOTAL_SCORE} side={MATCH_MIN_SIDE_SCORE} | "
            f"af_finished={sorted(AF_FINISHED_STATUS)}"
        )

    shared_state = make_shared_runtime_state()

    daily_df   = safe_read_csv(DAILY_FILE)
    history_df = safe_read_csv(HISTORY_FILE)

    history_df, h_updated, h_done, h_ignored = update_dataframe(history_df, "history", shared_state)
    history_df.to_csv(HISTORY_FILE, index=False, sep=";", encoding="utf-8")
    _persist_league_stats(HISTORY_FILE, LEAGUE_STATS_FILE, REMOTE_LEAGUE_STATS_NAME)
    print(f"History atualizado: {h_updated} | já resolvidos: {h_done} | ignorados: {h_ignored}")

    daily_df, d_updated, d_done, d_ignored = update_dataframe(daily_df, "daily", shared_state)
    daily_df, d_synced = sync_daily_from_history(daily_df, history_df)
    daily_df.to_csv(DAILY_FILE, index=False, sep=";", encoding="utf-8")
    print(
        f"Daily atualizado: {d_updated} | já resolvidos: {d_done} | ignorados: {d_ignored} | "
        f"sincronizados via history: {d_synced}"
    )

    save_team_alias_cache(shared_state)

    upload_csv_to_github(HISTORY_FILE, REMOTE_HISTORY_NAME)
    upload_csv_to_github(DAILY_FILE,   REMOTE_DAILY_NAME)

    # ── Manual bets — cloud_state.json is the single source of truth ──────────
    m_updated = m_ignored = 0
    if GITHUB_TOKEN:
        try:
            cloud_state = load_cloud_state_from_github()
            manual_bets = cloud_state.get("manualBets", [])
            print(f"Manual bets em cloud_state.json: {len(manual_bets)}")
            newly_settled = 0
            evidence_changed = 0
            if manual_bets:
                manual_df = manual_bets_to_settlement_df(manual_bets)
                manual_df, m_updated, m_done, m_ignored = update_dataframe(manual_df, "manual", shared_state)
                newly_settled, evidence_changed = apply_df_results_to_manual_bets(manual_bets, manual_df)
                print(
                    f"Manual atualizado: {m_updated} | já resolvidos: {m_done} | "
                    f"ignorados: {m_ignored} | liquidados agora: {newly_settled} | "
                    f"evidência atualizada: {evidence_changed}"
                )
                if newly_settled > 0 or evidence_changed > 0:
                    cloud_state["manualBets"] = manual_bets
            else:
                print("Manual: sem apostas pendentes")

            health_changed = bool(shared_state.get("provider_errors")) or bool(shared_state.get("provider_success_seen"))
            if health_changed:
                update_provider_health(cloud_state, shared_state)

            if newly_settled > 0 or evidence_changed > 0 or health_changed:
                msg = (
                    f"Settle {newly_settled} manual bet(s) — local run" if newly_settled > 0
                    else ("Update missing-fixture evidence — local run" if evidence_changed > 0
                          else "Update provider health — local run")
                )
                save_cloud_state_to_github(cloud_state, msg)
        except Exception as e:
            print(f"[WARN] liquidação manual falhou: {e}")
    else:
        print("[WARN] GITHUB_TOKEN não definido — liquidação manual ignorada")

    summary = build_settlement_result(
        h_updated + d_updated + m_updated,
        h_ignored + d_ignored + m_ignored,
        0.0,
        shared_state,
    )
    if summary.get("settlement_aborted"):
        print(
            f"[SETTLEMENT] aborted — provider={summary['abort_provider']} "
            f"category={summary['abort_category']} reason={summary['abort_reason']}"
        )


if __name__ == "__main__":
    main()
