import os
import json
import csv
import base64
import urllib.parse
import urllib.request
import time
import re
from urllib import error
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

import pandas as pd

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
DATA_RAW_DIR = BASE_DIR / "data_raw"

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
API_FOOTBALL_BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io").strip()

print(f"[DBG] API_FOOTBALL_KEY len = {len(API_FOOTBALL_KEY)}")
print(f"[DBG] API_FOOTBALL_BASE = {API_FOOTBALL_BASE}")

DEFAULT_LEAGUE_IDS = {
    "premier": 39,
    "portugal": 94,
    "alemanha": 78,
    "espanha": 140,
    "franca": 61,
    "italia": 135,
    "paises_baixos": 88,
    "championship": 40,
    "alemanha2": 79,
    "italia2": 136,
    "franca2": 62,
    "belgica": 144,
    "turquia": 203,
    "noruega": 103,
    "suecia": 113,
    "mls": 253,
    "japao": 98,
    "coreia": 292,
    "finlandia": 244,
    "islandia": 188,
    # Brazilian Serie A: calendar-year season, BTTS-favored profile, O2.5 medium confidence only
    "brasil": 71,
}

LEAGUE_INFO_EXT = {
    "noruega": {"name": "Eliteserien", "country": "Norway"},
    "suecia": {"name": "Allsvenskan", "country": "Sweden"},
    "mls": {"name": "MLS", "country": "USA"},
    "japao": {"name": "J1 League", "country": "Japan"},
    "coreia": {"name": "K League 1", "country": "Korea Republic"},
    "finlandia": {"name": "Veikkausliiga", "country": "Finland"},
    "islandia": {"name": "Besta deild", "country": "Iceland"},
    # Campeonato Brasileiro runs April-December (calendar year).
    # Brazilian football has relatively balanced home/away attack rates, supporting BTTS.
    # O2.5 is medium-confidence only: ~2.3 avg goals/game vs ~2.8 in EU top leagues,
    # and lambda calibration is unverified until sufficient history accumulates.
    # lambda_boost=1.00 (no inflation) — avoids the over-estimation seen in Asian leagues.
    "brasil": {"name": "Campeonato Brasileiro Serie A", "country": "Brazil"},
}

API_CALL_MIN_INTERVAL = 0.28
_api_last_call_ts = 0.0


# =============================
# HTTP helpers
# =============================
def _respect_api_spacing():
    global _api_last_call_ts

    now = time.monotonic()
    elapsed = now - _api_last_call_ts
    if elapsed < API_CALL_MIN_INTERVAL:
        time.sleep(API_CALL_MIN_INTERVAL - elapsed)

    _api_last_call_ts = time.monotonic()


def http_get_json_api_football(path: str, params: dict) -> dict:
    if not API_FOOTBALL_KEY:
        raise SystemExit("Falta API_FOOTBALL_KEY (define no Render -> Environment).")

    query = urllib.parse.urlencode(params)
    url = f"{API_FOOTBALL_BASE}{path}?{query}"

    _respect_api_spacing()

    req = urllib.request.Request(
        url,
        headers={
            "x-apisports-key": API_FOOTBALL_KEY,
            "Accept": "application/json",
            "User-Agent": "apostas-over-futebol/1.0",
        },
    )

    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw)


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

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def github_get_sha(owner: str, repo: str, path: str, branch: str, token: str) -> str | None:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
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
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}"
    sha = github_get_sha(owner, repo, path, branch, token)

    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    _ = github_request(url, token, method="PUT", data=payload)


def upload_file_to_github(file_path: Path, owner: str, repo: str, branch: str) -> None:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        print("GitHub: GITHUB_TOKEN em falta (não fiz upload).")
        return

    prefix = os.getenv("GITHUB_PATH_PREFIX", "").strip().strip("/")
    rel_path = file_path.name if not prefix else f"{prefix}/{file_path.name}"

    try:
        content = file_path.read_bytes()
        msg = f"Update {file_path.name} ({datetime.now(timezone.utc).isoformat()}Z)"
        github_put_file(owner, repo, rel_path, content, branch, token, msg)
        print(f"GitHub: upload concluído ({file_path.name})")
    except Exception as e:
        print(f"GitHub: falhou upload de {file_path.name} -> {e}")


# =============================
# Helpers
# =============================
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    return df


def safe_mean(series) -> float:
    if series is None:
        return 0.0
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return 0.0
    return float(s.mean())


def weighted_mean(values, decay: float = 0.90) -> float:
    v = pd.to_numeric(pd.Series(values), errors="coerce").dropna().tolist()
    if not v:
        return 0.0
    n = len(v)
    weights = [decay ** (n - 1 - i) for i in range(n)]
    num = sum(v[i] * weights[i] for i in range(n))
    den = sum(weights)
    return float(num / den) if den > 0 else 0.0


def league_avgs(df_hist: pd.DataFrame) -> tuple[float, float]:
    return (
        safe_mean(df_hist.get("FTHG", pd.Series(dtype=float))),
        safe_mean(df_hist.get("FTAG", pd.Series(dtype=float))),
    )


def last_n_home(df_hist: pd.DataFrame, team: str, n: int) -> pd.DataFrame:
    d = df_hist[df_hist["HomeTeam"] == team].sort_values("Date")
    return d.tail(n)


def last_n_away(df_hist: pd.DataFrame, team: str, n: int) -> pd.DataFrame:
    d = df_hist[df_hist["AwayTeam"] == team].sort_values("Date")
    return d.tail(n)


def clamp_strength(x: float, lo: float = 0.80, hi: float = 1.30) -> float:
    return float(max(lo, min(hi, x)))


def compute_lambdas(
    df_hist: pd.DataFrame,
    home: str,
    away: str,
    window: int,
    decay: float,
    min_games_home: int,
    min_games_away: int,
) -> tuple[float, float, float]:
    avg_home, avg_away = league_avgs(df_hist)

    if avg_home <= 0:
        avg_home = 1.20
    if avg_away <= 0:
        avg_away = 1.00

    h_last = last_n_home(df_hist, home, window)
    a_last = last_n_away(df_hist, away, window)

    if len(h_last) < min_games_home or len(a_last) < min_games_away:
        lam_home = float(max(0.25, min(2.20, avg_home)))
        lam_away = float(max(0.20, min(1.90, avg_away)))
        return lam_home, lam_away, lam_home + lam_away

    home_scored = weighted_mean(h_last["FTHG"], decay=decay)
    home_conceded = weighted_mean(h_last["FTAG"], decay=decay)
    away_scored = weighted_mean(a_last["FTAG"], decay=decay)
    away_conceded = weighted_mean(a_last["FTHG"], decay=decay)

    home_attack = clamp_strength(home_scored / avg_home if avg_home > 0 else 1.0)
    home_defense = clamp_strength(home_conceded / avg_away if avg_away > 0 else 1.0)
    away_attack = clamp_strength(away_scored / avg_away if avg_away > 0 else 1.0)
    away_defense = clamp_strength(away_conceded / avg_home if avg_home > 0 else 1.0)

    lam_home = avg_home * home_attack * away_defense
    lam_away = avg_away * away_attack * home_defense

    lam_home = float(max(0.25, min(2.20, lam_home)))
    lam_away = float(max(0.20, min(1.90, lam_away)))

    return lam_home, lam_away, lam_home + lam_away


def fixture_shortlist_score(lam_home: float, lam_away: float, lam_total: float) -> float:
    min_side = min(lam_home, lam_away)
    return (lam_total * 1.0) + (min_side * 0.75)


def normalize_text(s: str) -> str:
    s = str(s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_value_label(s: str) -> str:
    s = normalize_text(s)
    s = s.replace("goals", "").replace("goal", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


# =============================
# Config helpers
# =============================
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit("Falta config.json na pasta do projeto.")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def build_league_map(cfg: dict) -> dict:
    leagues_cfg = cfg.get("leagues", {})
    api_cfg = cfg.get("api_football", {})
    league_ids = api_cfg.get("league_ids", {}) or {}
    # Include keys declared in config plus any present in DEFAULT_LEAGUE_IDS
    keys = set(leagues_cfg.keys()) | set(DEFAULT_LEAGUE_IDS.keys())

    result = {}
    for key in sorted(keys):
        league_id = league_ids.get(key, DEFAULT_LEAGUE_IDS.get(key))
        if league_id:
            result[key] = int(league_id)
    return result


def season_for_date(d: date, league_key: str = None) -> int:
    # Summer leagues (Calendar year)
    summer_leagues = {"mls", "noruega", "suecia", "japao", "coreia", "finlandia", "islandia", "brasil"}
    if league_key in summer_leagues:
        return d.year
    # Winter leagues (Starting year)
    return d.year if d.month >= 7 else (d.year - 1)


def try_load_history_csv(league_key: str) -> Optional[pd.DataFrame]:
    hist_path = DATA_RAW_DIR / f"{league_key}.csv"
    if not hist_path.exists():
        return None

    try:
        df_hist = pd.read_csv(hist_path, sep=None, engine="python")
        df_hist = normalize_columns(df_hist)

        need_hist = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
        if not need_hist.issubset(set(df_hist.columns)):
            print(f"[WARN] {league_key}: histórico sem colunas necessárias -> {sorted(df_hist.columns)}")
            return None

        df_hist["Date"] = pd.to_datetime(df_hist["Date"], dayfirst=True, errors="coerce")
        df_hist = df_hist.dropna(subset=["Date"]).copy()
        return df_hist
    except Exception as e:
        print(f"[WARN] falhou leitura histórico {league_key} -> {e}")
        return None


# =============================
# API-Football fixtures
# =============================
def search_league_id_by_api(league_key: str, season: int) -> Optional[int]:
    info = LEAGUE_INFO_EXT.get(league_key)
    if not info:
        return None
    
    country = info.get("country")
    expected_name = info.get("name", "")

    if not country:
        return None

    params = {
        "country": country,
        "season": season,
    }
    try:
        data = http_get_json_api_football("/leagues", params)
    except Exception:
        return None

    response = data.get("response", []) if isinstance(data, dict) else []

    best_id = None
    for item in response:
        league = item.get("league", {}) or {}
        league_id = league.get("id")
        league_name = str(league.get("name", "")).strip()

        if not league_id or not league_name:
            continue

        if league_name.lower() == expected_name.lower():
            return int(league_id)

        if expected_name.lower() in league_name.lower():
            best_id = int(league_id)

    return best_id


def fetch_fixtures_for_league_date(
    league_id: int,
    season: int,
    date_iso: str,
    league_key: str = None,
    fixtures_cache: dict | None = None,
) -> tuple[list[dict], bool]:
    cache_key = (int(league_id), int(season), str(date_iso))

    if fixtures_cache is not None and cache_key in fixtures_cache:
        return fixtures_cache[cache_key], True

    params = {
        "league": league_id,
        "season": season,
        "date": date_iso,
        "timezone": "Europe/Lisbon",
    }

    data = http_get_json_api_football("/fixtures", params)
    response = data.get("response", []) if isinstance(data, dict) else []

    if not response and league_key:
        resolved_id = search_league_id_by_api(league_key, season)
        if resolved_id and resolved_id != league_id:
            print(f"[DBG] Re-resolvendo league_id para {league_key}: {league_id} -> {resolved_id}")
            params["league"] = resolved_id
            data = http_get_json_api_football("/fixtures", params)
            response = data.get("response", []) if isinstance(data, dict) else []

    try:
        results = data.get("results", None)
        errors = data.get("errors", None)
        response_len = len(response)
        print(
            f"[API-DBG] /fixtures league={params.get('league')} season={season} date={date_iso} "
            f"results={results} response_len={response_len} errors={errors}"
        )
    except Exception:
        pass

    if fixtures_cache is not None:
        fixtures_cache[cache_key] = response

    return response, False


# =============================
# API-Football odds per fixture
# =============================
def fetch_fixture_odds_response_api_football(
    fixture_id: int,
    odds_cache: dict | None = None,
) -> tuple[list[dict], bool]:
    fixture_id = int(fixture_id)

    if odds_cache is not None and fixture_id in odds_cache:
        return odds_cache[fixture_id], True

    try:
        data = http_get_json_api_football("/odds", {"fixture": fixture_id})
    except Exception as e:
        print(f"[WARN] odds API-Football falhou fixture={fixture_id} -> {e}")
        if odds_cache is not None:
            odds_cache[fixture_id] = []
        return [], False

    response = data.get("response", []) if isinstance(data, dict) else []

    if odds_cache is not None:
        odds_cache[fixture_id] = response

    return response, False


def extract_best_btts_from_api_football_response(response: list[dict], fixture_id: int) -> Optional[float]:
    best_btts = None

    allowed_main_names = {
        "both teams score",
        "both teams to score",
    }

    blocked_terms = {
        "first half",
        "second half",
        "1st half",
        "2nd half",
        "results/",
        "result/",
        "total goals/",
        "total goals",
    }

    yes_labels = {"yes", "sim"}

    for item in response:
        bookmakers = item.get("bookmakers", []) or []

        for bm in bookmakers:
            bm_name = str(bm.get("name", "")).strip()
            bets = bm.get("bets", []) or []

            for bet in bets:
                raw_bet_name = str(bet.get("name", "")).strip()
                bet_name = raw_bet_name.lower()
                values = bet.get("values", []) or []

                if bet_name not in allowed_main_names:
                    continue

                if any(term in bet_name for term in blocked_terms):
                    continue

                for v in values:
                    raw_label = str(v.get("value", "")).strip()
                    label = raw_label.lower()
                    odd = v.get("odd")

                    try:
                        odd = float(odd)
                    except Exception:
                        odd = None

                    if label not in yes_labels:
                        continue

                    if odd is None or odd <= 1.01:
                        continue

                    if odd < 1.20 or odd > 3.50:
                        print(
                            f"[DBG] BTTS ignorado por faixa suspeita | "
                            f"fixture={fixture_id} | bookmaker={bm_name} | "
                            f"market={raw_bet_name} | label={raw_label} | odd={odd}"
                        )
                        continue

                    print(
                        f"[DBG] BTTS candidato | fixture={fixture_id} | "
                        f"bookmaker={bm_name} | market={raw_bet_name} | "
                        f"label={raw_label} | odd={odd}"
                    )

                    if best_btts is None or odd > best_btts:
                        best_btts = odd

    return best_btts


def extract_best_over25_from_api_football_response(response: list[dict], fixture_id: int) -> Optional[float]:
    best_o25 = None

    blocked_market_terms = {
        "home",
        "away",
        "team",
        "1st half",
        "2nd half",
        "first half",
        "second half",
        "corners",
        "cards",
        "booking",
        "double chance",
        "exact score",
        "both teams",
        "winner",
        "handicap",
        "yellow",
        "red",
        "bookings",
        "fouls",
        "offsides",
        "shots",
        "throw-ins",
    }

    allowed_market_markers = {
        "over/under",
        "over under",
        "goals over/under",
        "goals over under",
        "total goals",
        "match goals",
        "goal line",
        "totals",
    }

    for item in response:
        bookmakers = item.get("bookmakers", []) or []

        for bm in bookmakers:
            bm_name = str(bm.get("name", "")).strip()
            bets = bm.get("bets", []) or []

            for bet in bets:
                raw_bet_name = str(bet.get("name", "")).strip()
                bet_name = normalize_text(raw_bet_name)
                values = bet.get("values", []) or []

                if any(term in bet_name for term in blocked_market_terms):
                    continue

                if not any(marker in bet_name for marker in allowed_market_markers):
                    continue

                for v in values:
                    raw_label = str(v.get("value", "")).strip()
                    label = normalize_value_label(raw_label)
                    odd = v.get("odd")

                    try:
                        odd = float(odd)
                    except Exception:
                        odd = None

                    is_over25 = (
                        label == "over 2.5"
                        or label == "over2.5"
                        or label == "+2.5"
                        or label.startswith("over 2.5 ")
                    )

                    if not is_over25:
                        continue

                    if odd is None or odd <= 1.01:
                        continue

                    if odd < 1.10 or odd > 8.00:
                        print(
                            f"[DBG] O2.5 ignorado por faixa suspeita | "
                            f"fixture={fixture_id} | bookmaker={bm_name} | "
                            f"market={raw_bet_name} | label={raw_label} | odd={odd}"
                        )
                        continue

                    print(
                        f"[DBG] O2.5 candidato | fixture={fixture_id} | "
                        f"bookmaker={bm_name} | market={raw_bet_name} | "
                        f"label={raw_label} | odd={odd}"
                    )

                    if best_o25 is None or odd > best_o25:
                        best_o25 = odd

    return best_o25


# =============================
# Candidate builder
# =============================
def build_candidate_from_history(
    item: dict,
    league_key: str,
    league_name: str,
    date_iso: str,
    season: int,
    df_hist: pd.DataFrame,
    window: int,
    decay: float,
    min_games_home: int,
    min_games_away: int,
    lambda_boost: float,
) -> Optional[dict]:
    fixture = item.get("fixture", {}) or {}
    teams = item.get("teams", {}) or {}

    fixture_id = fixture.get("id")
    fixture_date = str(fixture.get("date", ""))
    home = ((teams.get("home") or {}).get("name") or "").strip()
    away = ((teams.get("away") or {}).get("name") or "").strip()

    if not fixture_id or not home or not away:
        print(f"[FIXTURE FILTERED] league={league_key.upper()} reason=missing_data fixture_id={fixture_id} home={home} away={away}")
        return None

    print(f"[DBG] build_candidate league={league_key} home={home} away={away}")
    try:
        lam_h, lam_a, lam_t = compute_lambdas(
            df_hist,
            home,
            away,
            window=window,
            decay=decay,
            min_games_home=min_games_home,
            min_games_away=min_games_away,
        )
    except Exception as e:
        print(f"[FIXTURE FILTERED] league={league_key.upper()} reason=lambda_error error={e}")
        return None

    if lambda_boost and lambda_boost != 1.0:
        lam_h = max(0.25, min(2.20, lam_h * lambda_boost))
        lam_a = max(0.20, min(1.90, lam_a * lambda_boost))
        lam_t = lam_h + lam_a

    score = fixture_shortlist_score(lam_h, lam_a, lam_t)

    return {
        "fixture_id": int(fixture_id),
        "date": date_iso,
        "season": season,
        "league_key": league_key,
        "league_name": league_name,
        "home": home,
        "away": away,
        "lam_h": lam_h,
        "lam_a": lam_a,
        "lam_t": lam_t,
        "score": score,
        "api_fixture_date": fixture_date,
    }


# =============================
# Main
# =============================
def main():
    cfg = load_config()

    history_cfg = cfg.get("history", {})
    window = int(history_cfg.get("window", 12))
    decay = float(history_cfg.get("decay", 0.88))
    min_games_home = int(history_cfg.get("min_games_home", 8))
    min_games_away = int(history_cfg.get("min_games_away", 8))
    lambda_boost_default = float(history_cfg.get("lambda_boost", 1.0))

    run_cfg = cfg.get("run", {})
    days_ahead = int(run_cfg.get("days_ahead", 3))

    api_cfg = cfg.get("api_football", {})
    shortlist_total_cfg = int(api_cfg.get("shortlist_total", 18))
    shortlist_per_league_per_day_cfg = int(api_cfg.get("shortlist_per_league_per_day", 3))
    print(f"[DBG] config_shortlist_total={shortlist_total_cfg} shortlist_per_league_per_day={shortlist_per_league_per_day_cfg}")

    # TEMPORARY OVERRIDE to allow newly added leagues to surface for debugging
    shortlist_total = shortlist_total_cfg
    shortlist_per_league_per_day = shortlist_per_league_per_day_cfg
    print(f"[DBG] OVERRIDE shortlist_total={shortlist_total} shortlist_per_league_per_day={shortlist_per_league_per_day}")
    sleep_between_requests = float(api_cfg.get("sleep_seconds_between_fixture_requests", 0.35))
    use_api_football_for_btts_odds = bool(api_cfg.get("use_api_football_for_btts_odds", True))

    leagues_cfg = cfg.get("leagues", {})
    league_map = build_league_map(cfg)

    manual_season = api_cfg.get("season")

    try:
        from zoneinfo import ZoneInfo
        now_pt = datetime.now(ZoneInfo("Europe/Lisbon"))
    except Exception:
        # datetime.utcnow() is deprecated, use now(timezone.utc)
        now_pt = datetime.now(timezone.utc)

    start_dt = now_pt
    end_dt = now_pt + timedelta(days=days_ahead)
    print(f"[DATE WINDOW] start={start_dt} end={end_dt}")

    dates_to_fetch = [(now_pt.date() + timedelta(days=i)) for i in range(days_ahead + 1)]

    print(f"[DBG] dates_to_fetch={[d.isoformat() for d in dates_to_fetch]}")
    print(f"[DBG] shortlist_total={shortlist_total} | shortlist_per_league_per_day={shortlist_per_league_per_day}")

    fixture_candidates = []
    fixture_requests = 0
    odds_requests_api_football = 0
    fixture_cache_hits = 0
    odds_cache_hits = 0

    fixtures_cache = {}
    odds_cache = {}
    history_cache = {}

    # Counters for debug: per-league raw fixtures and per-league kept (after per-league truncation)
    counts_per_league_raw: dict = {}
    counts_per_league_kept: dict = {}

    # Per-league rejection audit (accumulated across all dates for the league)
    league_audit: dict = {}

    def _audit(lk: str, key: str, n: int = 1):
        if lk not in league_audit:
            league_audit[lk] = {}
        league_audit[lk][key] = league_audit[lk].get(key, 0) + n

    # 1) Fixtures via API-Football
    for league_key, league_id in league_map.items():
        league_name = leagues_cfg.get(league_key, {}).get("name", league_key)

        if league_key not in leagues_cfg:
            print(f"[FIXTURE SKIP] league={league_key.upper()} reason=not_in_config")
            _audit(league_key, "skip_not_in_config")
            continue

        if league_key in history_cache:
            df_hist = history_cache[league_key]
        else:
            df_hist = try_load_history_csv(league_key)
            history_cache[league_key] = df_hist

        if df_hist is None:
            print(f"[FIXTURE SKIP] league={league_key.upper()} reason=no_history_file")
            _audit(league_key, "skip_no_history_file")
            continue

        hist_rows = len(df_hist)
        hist_date_min = str(df_hist["Date"].min().date()) if len(df_hist) else "n/a"
        hist_date_max = str(df_hist["Date"].max().date()) if len(df_hist) else "n/a"
        print(
            f"[HISTORY] league={league_key.upper()} rows={hist_rows} "
            f"date_range={hist_date_min}..{hist_date_max}"
        )

        league_boosts = history_cfg.get("league_lambda_boost", {}) or {}
        lambda_boost = float(league_boosts.get(league_key, lambda_boost_default))

        league_fixtures_total = 0
        league_raw_total = 0
        for target_date in dates_to_fetch:
            date_iso = target_date.isoformat()
            season = int(manual_season) if manual_season is not None else season_for_date(target_date, league_key)

            try:
                resp, from_cache = fetch_fixtures_for_league_date(
                    league_id=league_id,
                    season=season,
                    date_iso=date_iso,
                    league_key=league_key,
                    fixtures_cache=fixtures_cache,
                )
                if from_cache:
                    fixture_cache_hits += 1
                else:
                    fixture_requests += 1
            except Exception as e:
                print(
                    f"[FIXTURE SKIP] league={league_key.upper()} reason=api_error "
                    f"date={date_iso} season={season} error={e}"
                )
                _audit(league_key, "skip_api_error")
                continue

            resp_count = len(resp or [])
            _audit(league_key, "api_returned", resp_count)

            print(
                f"[AUDIT] league={league_key.upper()} date={date_iso} season={season} "
                f"api_fixtures={resp_count} from_cache={from_cache}"
            )

            if resp_count == 0:
                _audit(league_key, "skip_api_empty_date")
                print(
                    f"[AUDIT] league={league_key.upper()} date={date_iso} "
                    f"→ 0 fixtures from API (wrong season? off-season?)"
                )
                if (not from_cache) and sleep_between_requests > 0:
                    time.sleep(sleep_between_requests)
                continue

            day_rows = []
            n_past = 0
            n_missing_data = 0
            n_lambda_error = 0
            n_built = 0

            for item in resp:
                # --- Gate 1: past-fixture filter ---
                f_date_str = (item.get("fixture") or {}).get("date", "")
                if f_date_str:
                    try:
                        f_dt = datetime.fromisoformat(f_date_str.replace("Z", "+00:00"))
                        if f_dt < now_pt:
                            n_past += 1
                            continue
                    except Exception:
                        pass

                fixture = item.get("fixture") or {}
                teams  = item.get("teams") or {}
                fixture_id = fixture.get("id")
                home = ((teams.get("home") or {}).get("name") or "").strip()
                away = ((teams.get("away") or {}).get("name") or "").strip()

                # --- Gate 2: missing team/fixture data ---
                if not fixture_id or not home or not away:
                    n_missing_data += 1
                    _audit(league_key, "reject_missing_data")
                    continue

                league_raw_total += 1

                # --- Gate 3: lambda calculation ---
                try:
                    lam_h, lam_a, lam_t = compute_lambdas(
                        df_hist, home, away,
                        window=window, decay=decay,
                        min_games_home=min_games_home,
                        min_games_away=min_games_away,
                    )
                    # Determine whether we used team-specific history or league fallback
                    h_rows = last_n_home(df_hist, home, window)
                    a_rows = last_n_away(df_hist, away, window)
                    used_fallback = (len(h_rows) < min_games_home or len(a_rows) < min_games_away)
                    if used_fallback:
                        _audit(league_key, "lambda_fallback_league_avg")
                    else:
                        _audit(league_key, "lambda_team_specific")
                except Exception as e:
                    n_lambda_error += 1
                    _audit(league_key, "reject_lambda_error")
                    print(
                        f"[AUDIT] league={league_key.upper()} date={date_iso} "
                        f"lambda_error home={home} away={away} err={e}"
                    )
                    continue

                if lambda_boost and lambda_boost != 1.0:
                    lam_h = max(0.25, min(2.20, lam_h * lambda_boost))
                    lam_a = max(0.20, min(1.90, lam_a * lambda_boost))
                    lam_t = lam_h + lam_a

                score = fixture_shortlist_score(lam_h, lam_a, lam_t)
                row = {
                    "fixture_id": int(fixture_id),
                    "date": date_iso,
                    "season": season,
                    "league_key": league_key,
                    "league_name": league_name,
                    "home": home,
                    "away": away,
                    "lam_h": lam_h,
                    "lam_a": lam_a,
                    "lam_t": lam_t,
                    "score": score,
                    "api_fixture_date": f_date_str,
                }
                n_built += 1
                day_rows.append(row)

            _audit(league_key, "past_filtered", n_past)
            _audit(league_key, "built_candidates", n_built)

            print(
                f"[AUDIT] league={league_key.upper()} date={date_iso} season={season} "
                f"api={resp_count} past_filtered={n_past} missing_data={n_missing_data} "
                f"lambda_errors={n_lambda_error} built={n_built}"
            )

            if n_past == resp_count and resp_count > 0:
                print(
                    f"[AUDIT] league={league_key.upper()} date={date_iso} "
                    f"→ ALL {resp_count} fixtures are in the past — "
                    f"script ran too late or fixtures already played"
                )

            day_rows.sort(key=lambda x: x["score"], reverse=True)
            kept_day = day_rows[:shortlist_per_league_per_day]
            counts_per_league_raw[league_key] = counts_per_league_raw.get(league_key, 0) + len(day_rows)
            counts_per_league_kept[league_key] = counts_per_league_kept.get(league_key, 0) + len(kept_day)
            fixture_candidates.extend(kept_day)
            league_fixtures_total += len(day_rows)

            if day_rows:
                scores = [r["score"] for r in day_rows]
                print(
                    f"[AUDIT] league={league_key.upper()} date={date_iso} "
                    f"candidates={len(day_rows)} kept_day={len(kept_day)} "
                    f"score_range={min(scores):.2f}..{max(scores):.2f}"
                )

            if (not from_cache) and sleep_between_requests > 0:
                time.sleep(sleep_between_requests)

        # --- Per-league summary ---
        audit_entry = league_audit.get(league_key, {})
        total_api    = audit_entry.get("api_returned", 0)
        total_past   = audit_entry.get("past_filtered", 0)
        total_built  = audit_entry.get("built_candidates", 0)
        total_kept   = counts_per_league_kept.get(league_key, 0)
        total_fallbk = audit_entry.get("lambda_fallback_league_avg", 0)
        total_team   = audit_entry.get("lambda_team_specific", 0)
        print(
            f"[LEAGUE SUMMARY] league={league_key.upper()} "
            f"api_total={total_api} past_filtered={total_past} "
            f"built={total_built} kept_after_per_league_cap={total_kept} "
            f"lambda_team={total_team} lambda_fallback={total_fallbk}"
        )
        if total_built == 0 and total_api > 0:
            print(
                f"[LEAGUE SUMMARY] league={league_key.upper()} "
                f"→ ZERO valid candidates despite {total_api} API fixtures. "
                f"Likely cause: all past ({total_past}) or missing data."
            )

    # 2) Global shortlist with per-league minimum guarantee
    print("\n========== GLOBAL SHORTLIST AUDIT ==========")
    print(f"[AUDIT] candidates_entering_global_pool={sum(counts_per_league_raw.values())}")
    for lk in sorted(counts_per_league_raw):
        raw  = counts_per_league_raw.get(lk, 0)
        kept = counts_per_league_kept.get(lk, 0)
        print(f"[AUDIT]   {lk.upper():20s} raw={raw:3d}  after_per_league_cap={kept:3d}")

    unique_candidates = {}
    for row in fixture_candidates:
        unique_candidates[row["fixture_id"]] = row

    all_cands = sorted(unique_candidates.values(), key=lambda x: x["score"], reverse=True)
    counts_before = len(all_cands)

    # Pass 1: guarantee each league that produced candidates gets at least this many slots,
    # taken in descending score order so the best fixtures per league are kept first.
    MIN_PER_LEAGUE_GLOBAL = 2
    guaranteed: list = []
    guaranteed_counts: dict = {}
    remaining: list = []
    for row in all_cands:
        lk = row["league_key"]
        if guaranteed_counts.get(lk, 0) < MIN_PER_LEAGUE_GLOBAL:
            guaranteed.append(row)
            guaranteed_counts[lk] = guaranteed_counts.get(lk, 0) + 1
        else:
            remaining.append(row)

    # Pass 2: fill remaining capacity from the top-scored non-guaranteed candidates
    extra = remaining[: max(0, shortlist_total - len(guaranteed))]
    fixture_candidates = guaranteed + extra
    fixture_candidates.sort(key=lambda x: x["score"], reverse=True)

    per_league_final: dict = {}
    for c in fixture_candidates:
        per_league_final[c["league_key"]] = per_league_final.get(c["league_key"], 0) + 1

    print(f"[AUDIT] global_pool_before={counts_before}  after_shortlist={len(fixture_candidates)}  shortlist_total={shortlist_total}")
    print("[AUDIT] per-league slots in final shortlist:")
    for lk in sorted(set(list(counts_per_league_raw.keys()) + list(per_league_final.keys()))):
        raw_cands = counts_per_league_kept.get(lk, 0)
        final     = per_league_final.get(lk, 0)
        flag      = "" if final > 0 else "  ← ZERO SLOTS (no candidates reached global pool)"
        print(f"[AUDIT]   {lk.upper():20s} entered_pool={raw_cands:3d}  final_slots={final:3d}{flag}")

    if all_cands:
        score_cutoff = all_cands[min(shortlist_total, len(all_cands)) - 1]["score"] if len(all_cands) >= shortlist_total else 0.0
        print(f"[AUDIT] score_cutoff_without_guarantee={score_cutoff:.3f}")
        print(f"[AUDIT] score of lowest-kept fixture (with guarantee): {fixture_candidates[-1]['score']:.3f}")
    print("=============================================\n")

    print(f"[DBG] fixture_requests={fixture_requests}")
    print(f"[DBG] fixture_cache_hits={fixture_cache_hits}")
    print(f"[DBG] shortlist_global={len(fixture_candidates)}")

    if not fixture_candidates:
        fixtures_path = BASE_DIR / "fixtures_today.csv"
        with open(fixtures_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["Date", "League", "HomeTeam", "AwayTeam", "Odd_Over25", "Odd_BTTS_Yes", "KickoffUTC"],
                delimiter=";",
            )
            w.writeheader()

        print("OK fixtures_today.csv: 0 jogos shortlistados com odds")
        owner = "jorgepita"
        repo = "apostas-over-futebol"
        branch = "main"
        upload_file_to_github(fixtures_path, owner, repo, branch)
        return

    # 3) Fetch O2.5 e BTTS via API-Football por fixture
    over25_map = {}
    btts_map = {}

    for fx in fixture_candidates:
        response, from_cache = fetch_fixture_odds_response_api_football(
            fx["fixture_id"],
            odds_cache=odds_cache,
        )
        if from_cache:
            odds_cache_hits += 1
        else:
            odds_requests_api_football += 1

        odd_o25 = extract_best_over25_from_api_football_response(response, fx["fixture_id"])
        over25_map[fx["fixture_id"]] = odd_o25

        odd_btts = None
        if use_api_football_for_btts_odds:
            odd_btts = extract_best_btts_from_api_football_response(response, fx["fixture_id"])
            btts_map[fx["fixture_id"]] = odd_btts

        print(
            f"[DBG] fixture odds | fixture={fx['fixture_id']} | {fx['league_key']} | "
            f"{fx['home']} vs {fx['away']} | O2.5={odd_o25} | BTTS={odd_btts}"
        )

        if (not from_cache) and sleep_between_requests > 0:
            time.sleep(min(sleep_between_requests, 0.25))

    # 4) Final rows — with per-league odds audit
    print("\n========== ODDS AUDIT ==========")
    no_odds_by_league: dict = {}
    rows = []
    for fx in fixture_candidates:
        odd_o25 = over25_map.get(fx["fixture_id"])
        odd_btts = btts_map.get(fx["fixture_id"])
        lk = fx["league_key"]

        if odd_o25 is None and odd_btts is None:
            no_odds_by_league[lk] = no_odds_by_league.get(lk, 0) + 1
            print(
                f"[AUDIT] no_odds league={lk.upper()} fixture_id={fx['fixture_id']} "
                f"{fx['home']} vs {fx['away']} date={fx['date']}"
            )
            continue

        rows.append(
            {
                "Date": fx["date"],
                "League": lk,
                "HomeTeam": fx["home"],
                "AwayTeam": fx["away"],
                "Odd_Over25": (f"{odd_o25:.2f}" if odd_o25 is not None else ""),
                "Odd_BTTS_Yes": (f"{odd_btts:.2f}" if odd_btts is not None else ""),
                "KickoffUTC": fx.get("api_fixture_date", ""),
            }
        )

    rows_by_league: dict = {}
    for r in rows:
        rows_by_league[r["League"]] = rows_by_league.get(r["League"], 0) + 1

    print(f"[AUDIT] shortlisted={len(fixture_candidates)}  with_odds={len(rows)}  no_odds={len(fixture_candidates)-len(rows)}")
    all_lks = sorted(set(list(per_league_final.keys()) + list(no_odds_by_league.keys())))
    for lk in all_lks:
        shortlisted = per_league_final.get(lk, 0)
        no_odds     = no_odds_by_league.get(lk, 0)
        with_odds   = rows_by_league.get(lk, 0)
        flag        = "  ← ZERO rows written" if with_odds == 0 else ""
        print(
            f"[AUDIT]   {lk.upper():20s} shortlisted={shortlisted}  no_odds={no_odds}  written={with_odds}{flag}"
        )
    print("=================================\n")

    rows.sort(key=lambda x: (x["Date"], x["League"], x["HomeTeam"], x["AwayTeam"]))

    fixtures_path = BASE_DIR / "fixtures_today.csv"
    with open(fixtures_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["Date", "League", "HomeTeam", "AwayTeam", "Odd_Over25", "Odd_BTTS_Yes", "KickoffUTC"],
            delimiter=";",
        )
        w.writeheader()
        w.writerows(rows)

    print(f"OK fixtures_today.csv: {len(rows)} jogos shortlistados com odds")
    print(f"[DBG] requests fixtures API-Football={fixture_requests}")
    print(f"[DBG] cache hits fixtures API-Football={fixture_cache_hits}")
    print(f"[DBG] requests odds API-Football={odds_requests_api_football}")
    print(f"[DBG] cache hits odds API-Football={odds_cache_hits}")
    print(f"[DBG] requests total aproximado={fixture_requests + odds_requests_api_football}")

    owner = "jorgepita"
    repo = "apostas-over-futebol"
    branch = "main"
    upload_file_to_github(fixtures_path, owner, repo, branch)


if __name__ == "__main__":
    main()
