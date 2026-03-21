import os
import json
import csv
import base64
import urllib.parse
import urllib.request
from urllib import error
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Optional

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
DATA_RAW_DIR = BASE_DIR / "data_raw"

API_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
API_BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io").strip()

print(f"[DBG] API_FOOTBALL_KEY len = {len(API_KEY)}")
print(f"[DBG] API_FOOTBALL_BASE = {API_BASE}")

DEFAULT_LEAGUE_IDS = {
    "premier": 39,
    "portugal": 94,
    "alemanha": 78,
    "espanha": 140,
    "franca": 61,
    "italia": 135,
    "paises_baixos": 88,
}

DEFAULT_INTERNATIONAL_LEAGUE_IDS = {
    "uefa_nations_league": 5,
    "world_cup_qualification_europe": 32,
    "euro_championship_qualification": 4,
    "international_friendlies": 10,
}


# =============================
# HTTP helpers
# =============================
def http_get_json(path: str, params: dict) -> dict:
    if not API_KEY:
        raise SystemExit("Falta API_FOOTBALL_KEY (define no Render -> Environment).")

    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}{path}?{query}"

    req = urllib.request.Request(
        url,
        headers={
            "x-apisports-key": API_KEY,
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
# Model helpers
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


def build_international_map(cfg: dict) -> dict:
    api_cfg = cfg.get("api_football", {})
    raw = api_cfg.get("international_league_ids", {}) or {}
    result = {}

    for key, value in DEFAULT_INTERNATIONAL_LEAGUE_IDS.items():
        result[key] = int(raw.get(key, value))

    return result


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
# API-Football helpers
# =============================
def fetch_fixtures_for_league_date(league_id: int, season: int, date_iso: str) -> list[dict]:
    data = http_get_json(
        "/fixtures",
        {
            "league": league_id,
            "season": season,
            "date": date_iso,
            "timezone": "Europe/Lisbon",
        },
    )
    return data.get("response", []) if isinstance(data, dict) else []


def fetch_odds_for_fixture(fixture_id: int) -> list[dict]:
    data = http_get_json(
        "/odds",
        {
            "fixture": fixture_id,
        },
    )
    return data.get("response", []) if isinstance(data, dict) else []


def extract_best_market_prices(odds_response: list[dict]) -> tuple[Optional[float], Optional[float]]:
    best_o25 = None
    best_btts = None

    for item in odds_response or []:
        bookmakers = item.get("bookmakers", []) or []

        for bm in bookmakers:
            bets = bm.get("bets", []) or []

            for bet in bets:
                bet_name = str(bet.get("name", "")).strip().lower()
                values = bet.get("values", []) or []

                if "over" in bet_name and "under" in bet_name and "2.5" in bet_name:
                    for v in values:
                        label = str(v.get("value", "")).strip().lower()
                        odd = v.get("odd")
                        try:
                            odd = float(odd)
                        except Exception:
                            odd = None

                        if label in {"over 2.5", "over"} and odd and odd > 1.01:
                            if best_o25 is None or odd > best_o25:
                                best_o25 = odd

                if "both teams" in bet_name and "score" in bet_name:
                    for v in values:
                        label = str(v.get("value", "")).strip().lower()
                        odd = v.get("odd")
                        try:
                            odd = float(odd)
                        except Exception:
                            odd = None

                        if label in {"yes", "sim"} and odd and odd > 1.01:
                            if best_btts is None or odd > best_btts:
                                best_btts = odd

    return best_o25, best_btts


# =============================
# Candidate builders
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
        "home": home,
        "away": away,
        "lam_h": lam_h,
        "lam_a": lam_a,
        "lam_t": lam_t,
        "score": score,
        "api_fixture_date": fixture_date,
        "source_type": "history_model",
    }


def build_candidate_international(
    item: dict,
    league_key: str,
    league_name: str,
    date_iso: str,
    season: int,
) -> Optional[dict]:
    fixture = item.get("fixture", {}) or {}
    teams = item.get("teams", {}) or {}

    fixture_id = fixture.get("id")
    fixture_date = str(fixture.get("date", ""))
    home = ((teams.get("home") or {}).get("name") or "").strip()
    away = ((teams.get("away") or {}).get("name") or "").strip()

    if not fixture_id or not home or not away:
        return None

    # Sem histórico local de seleções/competições internacionais,
    # usamos score neutro só para não perder os jogos disponíveis.
    lam_h = 1.35
    lam_a = 1.10
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
        "source_type": "international_fallback",
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
    lambda_boost = float(history_cfg.get("lambda_boost", 1.0))

    run_cfg = cfg.get("run", {})
    days_ahead = int(run_cfg.get("days_ahead", 7))

    api_cfg = cfg.get("api_football", {})
    shortlist_total = int(api_cfg.get("shortlist_total", 12))
    shortlist_per_league_per_day = int(api_cfg.get("shortlist_per_league_per_day", 2))
    shortlist_per_international_day = int(api_cfg.get("shortlist_per_international_day", 4))
    fallback_to_internationals = bool(api_cfg.get("fallback_to_internationals", True))

    leagues_cfg = cfg.get("leagues", {})
    league_map = build_league_map(cfg)
    international_map = build_international_map(cfg)

    manual_season = api_cfg.get("season")

    try:
        from zoneinfo import ZoneInfo
        now_pt = datetime.now(ZoneInfo("Europe/Lisbon"))
    except Exception:
        now_pt = datetime.utcnow()

    dates_to_fetch = [(now_pt.date() + timedelta(days=i)) for i in range(days_ahead + 1)]

    print(f"[DBG] dates_to_fetch={[d.isoformat() for d in dates_to_fetch]}")
    print(f"[DBG] shortlist_total={shortlist_total} | shortlist_per_league_per_day={shortlist_per_league_per_day}")
    print(f"[DBG] fallback_to_internationals={fallback_to_internationals}")

    fixture_candidates = []
    fixture_requests = 0
    odds_requests = 0

    # 1) Ligas domésticas
    for league_key, league_id in league_map.items():
        league_name = leagues_cfg.get(league_key, {}).get("name", league_key)
        df_hist = try_load_history_csv(league_key)

        if df_hist is None:
            print(f"[WARN] histórico em falta para {league_key}")
            continue

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

    # 2) Fallback internacional
    if not fixture_candidates and fallback_to_internationals:
        print("[DBG] sem jogos nas ligas domésticas -> a tentar fallback internacional")

        for intl_key, intl_league_id in international_map.items():
            intl_name = intl_key

            for target_date in dates_to_fetch:
                date_iso = target_date.isoformat()
                season = int(manual_season) if manual_season is not None else season_for_date(target_date)

                try:
                    resp = fetch_fixtures_for_league_date(intl_league_id, season, date_iso)
                    fixture_requests += 1
                except Exception as e:
                    print(f"[WARN] intl fixtures falhou league={intl_key} season={season} date={date_iso} -> {e}")
                    continue

                day_rows = []
                for item in resp:
                    row = build_candidate_international(
                        item=item,
                        league_key=intl_key,
                        league_name=intl_name,
                        date_iso=date_iso,
                        season=season,
                    )
                    if row:
                        day_rows.append(row)

                day_rows.sort(key=lambda x: x["score"], reverse=True)
                kept_day = day_rows[:shortlist_per_international_day]
                fixture_candidates.extend(kept_day)

                print(
                    f"[DBG] intl fixtures league={intl_key} season={season} date={date_iso} "
                    f"raw={len(day_rows)} shortlist_day={len(kept_day)}"
                )

    # 3) Global shortlist
    unique_candidates = {}
    for row in fixture_candidates:
        unique_candidates[row["fixture_id"]] = row

    fixture_candidates = list(unique_candidates.values())
    fixture_candidates.sort(key=lambda x: x["score"], reverse=True)
    fixture_candidates = fixture_candidates[:shortlist_total]

    print(f"[DBG] fixture_requests={fixture_requests}")
    print(f"[DBG] shortlist_global={len(fixture_candidates)}")

    rows = []

    # 4) Odds só para shortlist
    for fx in fixture_candidates:
        fixture_id = fx["fixture_id"]

        try:
            odds_resp = fetch_odds_for_fixture(fixture_id)
            odds_requests += 1
        except Exception as e:
            print(f"[WARN] odds falhou fixture={fixture_id} -> {e}")
            continue

        odd_o25, odd_btts = extract_best_market_prices(odds_resp)

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

        print(
            f"[DBG] odds fixture={fixture_id} | source={fx['source_type']} | season={fx['season']} | "
            f"{fx['league_key']} | {fx['home']} vs {fx['away']} | O2.5={odd_o25} | BTTS={odd_btts}"
        )

    rows.sort(key=lambda x: (x["Date"], x["League"], x["HomeTeam"], x["AwayTeam"]))

    fixtures_path = BASE_DIR / "fixtures_today.csv"
    with open(fixtures_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["Date", "League", "HomeTeam", "AwayTeam", "Odd_Over25", "Odd_BTTS_Yes"],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"OK fixtures_today.csv: {len(rows)} jogos shortlistados com odds")
    print(f"[DBG] requests fixtures={fixture_requests}")
    print(f"[DBG] requests odds={odds_requests}")
    print(f"[DBG] requests total={fixture_requests + odds_requests}")

    owner = "jorgepita"
    repo = "apostas-over-futebol"
    branch = "main"
    upload_file_to_github(fixtures_path, owner, repo, branch)


if __name__ == "__main__":
    main()
