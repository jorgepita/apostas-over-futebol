import os
import json
import csv
import base64
import urllib.parse
import urllib.request
import unicodedata
import re
import time
from urllib import error
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Optional

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
DATA_RAW_DIR = BASE_DIR / "data_raw"

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
API_FOOTBALL_BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()

print(f"[DBG] API_FOOTBALL_KEY len = {len(API_FOOTBALL_KEY)}")
print(f"[DBG] API_FOOTBALL_BASE = {API_FOOTBALL_BASE}")
print(f"[DBG] ODDS_API_KEY len = {len(ODDS_API_KEY)}")

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
}


# =============================
# HTTP helpers
# =============================
def http_get_json_api_football(path: str, params: dict) -> dict:
    if not API_FOOTBALL_KEY:
        raise SystemExit("Falta API_FOOTBALL_KEY (define no Render -> Environment).")

    query = urllib.parse.urlencode(params)
    url = f"{API_FOOTBALL_BASE}{path}?{query}"

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


def http_get_json_odds(url: str) -> dict | list:
    if not ODDS_API_KEY:
        raise SystemExit("Falta ODDS_API_KEY (define no Render -> Environment).")

    req = urllib.request.Request(
        url,
        headers={
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


def normalize_team_name(name: str) -> str:
    s = str(name or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    repl = {
        "stª": "santa",
        "st.": "saint",
        " st ": " saint ",
        " fc ": " ",
        " afc ": " ",
        " sc ": " ",
        " ac ": " ",
        " cf ": " ",
        " ssc ": " ",
        " 1. ": " ",
        "1. ": " ",
        "&": " and ",
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def same_match(api_home: str, api_away: str, odds_home: str, odds_away: str) -> bool:
    ah = normalize_team_name(api_home)
    aa = normalize_team_name(api_away)
    oh = normalize_team_name(odds_home)
    oa = normalize_team_name(odds_away)
    return ah == oh and aa == oa


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

    result = {}
    for key in leagues_cfg.keys():
        league_id = league_ids.get(key, DEFAULT_LEAGUE_IDS.get(key))
        if league_id:
            result[key] = int(league_id)
    return result


def build_odds_sport_map(cfg: dict) -> dict:
    odds_cfg = cfg.get("the_odds_api", {})
    return dict(odds_cfg.get("sport_keys", {}) or {})


def season_for_date(d: date) -> int:
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
def fetch_fixtures_for_league_date(league_id: int, season: int, date_iso: str) -> list[dict]:
    params = {
        "league": league_id,
        "season": season,
        "date": date_iso,
        "timezone": "Europe/Lisbon",
    }

    data = http_get_json_api_football("/fixtures", params)

    try:
        results = data.get("results", None)
        errors = data.get("errors", None)
        response_len = len(data.get("response", []) or []) if isinstance(data, dict) else -1
        print(
            f"[API-DBG] /fixtures league={league_id} season={season} date={date_iso} "
            f"results={results} response_len={response_len} errors={errors}"
        )
    except Exception:
        pass

    return data.get("response", []) if isinstance(data, dict) else []


# =============================
# API-Football BTTS odds per fixture
# =============================
def fetch_btts_odds_for_fixture_api_football(fixture_id: int) -> Optional[float]:
    try:
        data = http_get_json_api_football("/odds", {"fixture": fixture_id})
    except Exception as e:
        print(f"[WARN] BTTS odds API-Football falhou fixture={fixture_id} -> {e}")
        return None

    response = data.get("response", []) if isinstance(data, dict) else []
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

    def debug_odds_payload_for_fixture_api_football(fixture_id: int) -> None:
        try:
            data = http_get_json_api_football("/odds", {"fixture": fixture_id})
        except Exception as e:
            print(f"[WARN] DEBUG odds API-Football falhou fixture={fixture_id} -> {e}")
            return

        print(f"[DBG] DEBUG odds payload fixture={fixture_id}")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:20000])

# =============================
# The Odds API O2.5 odds grouped
# =============================
def fetch_odds_for_sport_date(sport_key: str, date_iso: str, cfg: dict) -> list[dict]:
    odds_cfg = cfg.get("the_odds_api", {})
    regions = odds_cfg.get("regions", "eu")
    markets = odds_cfg.get("markets", "totals")
    odds_format = odds_cfg.get("odds_format", "decimal")
    date_format = odds_cfg.get("date_format", "iso")

    commence_from = f"{date_iso}T00:00:00Z"
    commence_to = f"{date_iso}T23:59:59Z"

    base_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    query = urllib.parse.urlencode(
        {
            "apiKey": ODDS_API_KEY,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": date_format,
            "commenceTimeFrom": commence_from,
            "commenceTimeTo": commence_to,
        }
    )
    url = f"{base_url}?{query}"

    try:
        data = http_get_json_odds(url)
        if isinstance(data, list):
            print(f"[ODDS-DBG] sport={sport_key} date={date_iso} events={len(data)}")
            return data
        print(f"[ODDS-DBG] sport={sport_key} date={date_iso} resposta não-lista")
        return []
    except Exception as e:
        print(f"[WARN] O2.5 odds fetch falhou sport={sport_key} date={date_iso} -> {e}")
        return []


def extract_best_over25_from_event(event: dict) -> Optional[float]:
    best_o25 = None

    bookmakers = event.get("bookmakers", []) or []
    for bm in bookmakers:
        markets = bm.get("markets", []) or []
        for market in markets:
            key = str(market.get("key", "")).strip().lower()
            outcomes = market.get("outcomes", []) or []

            if key == "totals":
                for o in outcomes:
                    name = str(o.get("name", "")).strip().lower()
                    point = o.get("point")
                    price = o.get("price")

                    try:
                        price = float(price)
                    except Exception:
                        price = None

                    try:
                        point = float(point)
                    except Exception:
                        point = None

                    if name == "over" and point == 2.5 and price and price > 1.01:
                        if best_o25 is None or price > best_o25:
                            best_o25 = price

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
    sport_key: str,
) -> Optional[dict]:
    fixture = item.get("fixture", {}) or {}
    teams = item.get("teams", {}) or {}

    fixture_id = fixture.get("id")
    fixture_date = str(fixture.get("date", ""))
    home = ((teams.get("home") or {}).get("name") or "").strip()
    away = ((teams.get("away") or {}).get("name") or "").strip()

    if not fixture_id or not home or not away:
        return None

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
    except Exception:
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
        "sport_key": sport_key,
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
    shortlist_total = int(api_cfg.get("shortlist_total", 18))
    shortlist_per_league_per_day = int(api_cfg.get("shortlist_per_league_per_day", 3))
    sleep_between_requests = float(api_cfg.get("sleep_seconds_between_fixture_requests", 0.35))
    use_api_football_for_btts_odds = bool(api_cfg.get("use_api_football_for_btts_odds", True))

    leagues_cfg = cfg.get("leagues", {})
    league_map = build_league_map(cfg)
    odds_sport_map = build_odds_sport_map(cfg)

    manual_season = api_cfg.get("season")

    try:
        from zoneinfo import ZoneInfo
        now_pt = datetime.now(ZoneInfo("Europe/Lisbon"))
    except Exception:
        now_pt = datetime.utcnow()

    dates_to_fetch = [(now_pt.date() + timedelta(days=i)) for i in range(days_ahead + 1)]

    print(f"[DBG] dates_to_fetch={[d.isoformat() for d in dates_to_fetch]}")
    print(f"[DBG] shortlist_total={shortlist_total} | shortlist_per_league_per_day={shortlist_per_league_per_day}")

    fixture_candidates = []
    fixture_requests = 0
    odds_requests_the_odds = 0
    odds_requests_api_football = 0

    # 1) Fixtures via API-Football
    for league_key, league_id in league_map.items():
        league_name = leagues_cfg.get(league_key, {}).get("name", league_key)
        sport_key = odds_sport_map.get(league_key, "")

        if not sport_key:
            print(f"[WARN] sport_key em falta para {league_key}")
            continue

        df_hist = try_load_history_csv(league_key)
        if df_hist is None:
            print(f"[WARN] histórico em falta para {league_key}")
            continue

        league_boosts = history_cfg.get("league_lambda_boost", {}) or {}
        lambda_boost = float(league_boosts.get(league_key, lambda_boost_default))

        for target_date in dates_to_fetch:
            date_iso = target_date.isoformat()
            season = int(manual_season) if manual_season is not None else season_for_date(target_date)

            try:
                resp = fetch_fixtures_for_league_date(league_id, season, date_iso)
                fixture_requests += 1
            except Exception as e:
                print(f"[WARN] fixtures falhou league={league_key} season={season} date={date_iso} -> {e}")
                continue

            day_rows = []
            for item in resp:
                row = build_candidate_from_history(
                    item=item,
                    league_key=league_key,
                    league_name=league_name,
                    date_iso=date_iso,
                    season=season,
                    df_hist=df_hist,
                    window=window,
                    decay=decay,
                    min_games_home=min_games_home,
                    min_games_away=min_games_away,
                    lambda_boost=lambda_boost,
                    sport_key=sport_key,
                )
                if row:
                    day_rows.append(row)

            day_rows.sort(key=lambda x: x["score"], reverse=True)
            kept_day = day_rows[:shortlist_per_league_per_day]
            fixture_candidates.extend(kept_day)

            print(
                f"[DBG] fixtures league={league_key} season={season} date={date_iso} "
                f"raw={len(day_rows)} shortlist_day={len(kept_day)}"
            )

            if sleep_between_requests > 0:
                time.sleep(sleep_between_requests)

    # 2) Global shortlist
    unique_candidates = {}
    for row in fixture_candidates:
        unique_candidates[row["fixture_id"]] = row

    fixture_candidates = list(unique_candidates.values())
    fixture_candidates.sort(key=lambda x: x["score"], reverse=True)
    fixture_candidates = fixture_candidates[:shortlist_total]

    print(f"[DBG] fixture_requests={fixture_requests}")
    print(f"[DBG] shortlist_global={len(fixture_candidates)}")

    if not fixture_candidates:
        fixtures_path = BASE_DIR / "fixtures_today.csv"
        with open(fixtures_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["Date", "League", "HomeTeam", "AwayTeam", "Odd_Over25", "Odd_BTTS_Yes"],
                delimiter=";",
            )
            w.writeheader()

        print("OK fixtures_today.csv: 0 jogos shortlistados com odds")
        owner = "jorgepita"
        repo = "apostas-over-futebol"
        branch = "main"
        upload_file_to_github(fixtures_path, owner, repo, branch)
        return

    # 3) Fetch O2.5 odds from The Odds API grouped by sport/date
    grouped = {}
    for fx in fixture_candidates:
        key = (fx["sport_key"], fx["date"])
        grouped.setdefault(key, []).append(fx)

    over25_map = {}

    for (sport_key, date_iso), candidates in grouped.items():
        odds_events = fetch_odds_for_sport_date(sport_key, date_iso, cfg)
        odds_requests_the_odds += 1

        print(f"[DBG] odds_events recebidos | sport={sport_key} | date={date_iso} | total={len(odds_events)}")

        for fx in candidates:
            matched_event = None

            for ev in odds_events:
                home_team = str(ev.get("home_team", "")).strip()
                away_team = str(ev.get("away_team", "")).strip()

                if not away_team:
                    teams = ev.get("teams", []) or []
                    if len(teams) == 2:
                        away_team = teams[0] if teams[1] == home_team else teams[1]

                if same_match(fx["home"], fx["away"], home_team, away_team):
                    print(f"[DBG] MATCH TheOdds | sport={sport_key} | {fx['league_key']} | {fx['home']} vs {fx['away']}")
                    print(json.dumps(ev, ensure_ascii=False, indent=2)[:12000])
                    matched_event = ev
                    break

            if not matched_event:
                print(f"[DBG] O2.5 sem match: {fx['league_key']} | {fx['home']} vs {fx['away']}")
                continue

            odd_o25 = extract_best_over25_from_event(matched_event)
            over25_map[fx["fixture_id"]] = odd_o25

            print(
                f"[DBG] O2.5 match | sport={sport_key} | {fx['league_key']} | "
                f"{fx['home']} vs {fx['away']} | O2.5={odd_o25}"
            )
            if not matched_event:
                print(f"[DBG] O2.5 sem match: {fx['league_key']} | {fx['home']} vs {fx['away']}")
                continue

            odd_o25 = extract_best_over25_from_event(matched_event)
            over25_map[fx["fixture_id"]] = odd_o25

            print(
                f"[DBG] O2.5 match | sport={sport_key} | {fx['league_key']} | "
                f"{fx['home']} vs {fx['away']} | O2.5={odd_o25}"
            )

    debug_fixture_id = 1387037
    debug_odds_payload_for_fixture_api_football(debug_fixture_id)
    return
    
    # 4) Fetch BTTS odds from API-Football only for shortlisted fixtures
    btts_map = {}
    if use_api_football_for_btts_odds:
        for fx in fixture_candidates:
            odd_btts = fetch_btts_odds_for_fixture_api_football(fx["fixture_id"])
            odds_requests_api_football += 1
            btts_map[fx["fixture_id"]] = odd_btts

            print(
                f"[DBG] BTTS fixture={fx['fixture_id']} | {fx['league_key']} | "
                f"{fx['home']} vs {fx['away']} | BTTS={odd_btts}"
            )

            if sleep_between_requests > 0:
                time.sleep(min(sleep_between_requests, 0.25))

    # 5) Final rows
    rows = []
    for fx in fixture_candidates:
        odd_o25 = over25_map.get(fx["fixture_id"])
        odd_btts = btts_map.get(fx["fixture_id"])

        if odd_o25 is None and odd_btts is None:
            continue

        rows.append(
            {
                "Date": fx["date"],
                "League": fx["league_key"],
                "HomeTeam": fx["home"],
                "AwayTeam": fx["away"],
                "Odd_Over25": (f"{odd_o25:.2f}" if odd_o25 is not None else ""),
                "Odd_BTTS_Yes": (f"{odd_btts:.2f}" if odd_btts is not None else ""),
            }
        )

    rows.sort(key=lambda x: (x["Date"], x["League"], x["HomeTeam"], x["AwayTeam"]))

    fixtures_path = BASE_DIR / "fixtures_today.csv"
    with open(fixtures_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["Date", "League", "HomeTeam", "AwayTeam", "Odd_Over25", "Odd_BTTS_Yes"],
            delimiter=";",
        )
        w.writeheader()
        w.writerows(rows)

    print(f"OK fixtures_today.csv: {len(rows)} jogos shortlistados com odds")
    print(f"[DBG] requests fixtures API-Football={fixture_requests}")
    print(f"[DBG] requests odds TheOdds groups={odds_requests_the_odds}")
    print(f"[DBG] requests odds API-Football BTTS={odds_requests_api_football}")
    print(f"[DBG] requests total aproximado={fixture_requests + odds_requests_the_odds + odds_requests_api_football}")

    owner = "jorgepita"
    repo = "apostas-over-futebol"
    branch = "main"
    upload_file_to_github(fixtures_path, owner, repo, branch)


if __name__ == "__main__":
    main()
