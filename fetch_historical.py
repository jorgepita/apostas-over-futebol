import os
import json
import time
import urllib.parse
import urllib.request
from urllib import error
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

import pandas as pd

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
DATA_RAW_DIR = BASE_DIR / "data_raw"
DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
API_FOOTBALL_BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io").strip()

print(f"[DBG] API_FOOTBALL_KEY len = {len(API_FOOTBALL_KEY)}")
print(f"[DBG] API_FOOTBALL_BASE = {API_FOOTBALL_BASE}")

LEAGUE_INFO = {
    "noruega": {"name": "Eliteserien", "country": "Norway", "id": 103},
    "suecia": {"name": "Allsvenskan", "country": "Sweden", "id": 113},
    "mls": {"name": "MLS", "country": "USA", "id": 253},
    "japao": {"name": "J1 League", "country": "Japan", "id": 98},
    "coreia": {"name": "K League 1", "country": "Korea Republic", "id": 292},
    "finlandia": {"name": "Veikkausliiga", "country": "Finland", "id": 244},
    "islandia": {"name": "Besta deild", "country": "Iceland", "id": 188},
}

API_CALL_MIN_INTERVAL = 0.28
_api_last_call_ts = 0.0


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

    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw)
    except error.HTTPError as e:
        print(f"[ERRO] HTTP {e.code} -> {e.reason}")
        return {"response": []}
    except Exception as e:
        print(f"[ERRO] HTTP request falhou -> {e}")
        return {"response": []}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit("Falta config.json na pasta do projeto.")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def get_config_league_id(cfg: dict, league_key: str) -> Optional[int]:
    api_cfg = cfg.get("api_football", {}) or {}
    league_ids = api_cfg.get("league_ids", {}) or {}
    if league_key in league_ids:
        try:
            return int(league_ids[league_key])
        except Exception:
            pass

    league_info = LEAGUE_INFO.get(league_key, {})
    return league_info.get("id")


def normalize_date(date_str: str) -> str:
    """
    Convert ISO date (YYYY-MM-DD) to DD/MM/YYYY format.
    """
    try:
        dt = datetime.fromisoformat(date_str.split("T")[0])
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return ""


def extract_match_record(fixture: dict) -> Optional[dict]:
    """
    Extract a single match record from API-Football fixture response.
    Returns dict with {Date, HomeTeam, AwayTeam, FTHG, FTAG} or None.
    """
    try:
        fixture_meta = fixture.get("fixture", {}) or {}
        teams = fixture.get("teams", {}) or {}
        goals = fixture.get("goals", {}) or {}

        fixture_date = fixture_meta.get("date", "")
        home_name = ((teams.get("home") or {}).get("name") or "").strip()
        away_name = ((teams.get("away") or {}).get("name") or "").strip()
        home_goals = goals.get("home")
        away_goals = goals.get("away")

        if not fixture_date or not home_name or not away_name:
            return None

        if home_goals is None or away_goals is None:
            return None

        return {
            "Date": normalize_date(fixture_date),
            "HomeTeam": home_name,
            "AwayTeam": away_name,
            "FTHG": int(home_goals),
            "FTAG": int(away_goals),
        }
    except Exception as e:
        print(f"[WARN] falhou extração do match -> {e}")
        return None


def search_league_id_by_api(league_key: str, season: int) -> Optional[int]:
    league_info = LEAGUE_INFO.get(league_key, {})
    country = league_info.get("country")
    expected_name = league_info.get("name", "")

    if not country:
        return None

    params = {
        "country": country,
        "season": season,
    }
    data = http_get_json_api_football("/leagues", params)
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


def fetch_finished_matches(
    league_key: str,
    league_id: int,
    season: int,
) -> list[dict]:
    """
    Fetch finished matches for a league and season from API-Football.
    Returns list of fixture dicts.
    """
    params = {
        "league": league_id,
        "season": season,
        "status": "FT",
    }

    data = http_get_json_api_football("/fixtures", params)
    response = data.get("response", []) if isinstance(data, dict) else []

    try:
        results = data.get("results", None)
        errors = data.get("errors", None)
        response_len = len(response) if isinstance(response, list) else -1
        print(
            f"[API-DBG] /fixtures league={league_id} season={season} status=FT "
            f"results={results} response_len={response_len} errors={errors}"
        )
    except Exception:
        pass

    if not response:
        resolved_league_id = search_league_id_by_api(league_key, season)
        if resolved_league_id and resolved_league_id != league_id:
            print(f"[DBG] Re-resolvendo league_id para {league_key}: {league_id} -> {resolved_league_id}")
            params["league"] = resolved_league_id
            data = http_get_json_api_football("/fixtures", params)
            response = data.get("response", []) if isinstance(data, dict) else []

            try:
                results = data.get("results", None)
                errors = data.get("errors", None)
                response_len = len(response) if isinstance(response, list) else -1
                print(
                    f"[API-DBG] /fixtures fallback league={resolved_league_id} season={season} "
                    f"results={results} response_len={response_len} errors={errors}"
                )
            except Exception:
                pass

    return response


def get_historical_seasons(cfg: dict, league_key: str, current_year: int, current_month: int) -> list[int]:
    hist_cfg = cfg.get("historical", {}) or {}
    seasons_by_league = hist_cfg.get("seasons_by_league", {}) or {}
    if league_key in seasons_by_league:
        seasons = []
        for season in seasons_by_league[league_key] or []:
            try:
                seasons.append(int(season))
            except Exception:
                pass
        return sorted(set(seasons))

    seasons = []
    for season in hist_cfg.get("seasons", []) or []:
        try:
            seasons.append(int(season))
        except Exception:
            pass
    if seasons:
        return sorted(set(seasons))

    # Fallback default logic
    summer_leagues = {"mls", "noruega", "suecia", "japao", "coreia", "finlandia", "islandia"}
    if league_key in summer_leagues:
        # For summer leagues, we want current year if it has already started (Mar-May)
        if current_month >= 4:
            return [current_year - 1, current_year]
        return [current_year - 1]

    if current_month >= 7:
        return [current_year]
    return [current_year - 1]


def generate_historical_csv(
    cfg: dict,
    league_key: str,
    seasons: list[int],
) -> None:
    """
    Fetch finished matches for a league across multiple seasons and write one merged CSV.
    """
    if not seasons:
        print(f"[AVISO] Nenhuma season configurada para {league_key}")
        return

    league_id = get_config_league_id(cfg, league_key)
    if league_id is None:
        print(f"[AVISO] league_id em falta para {league_key}")

    print(f"[HIST] fetching league={league_key.upper()}")

    records = []
    seen = set()
    for season in seasons:
        if league_id is None:
            league_id = search_league_id_by_api(league_key, season)
            if league_id is None:
                print(f"[AVISO] não consegui resolver league_id para {league_key} season={season}")
                continue

        fixtures = fetch_finished_matches(league_key, league_id, season)
        if not fixtures:
            print(f"[AVISO] Nenhum match encontrado para {league_key} season={season}")
            continue

        for fixture in fixtures:
            record = extract_match_record(fixture)
            if not record:
                continue

            key = (record["Date"], record["HomeTeam"], record["AwayTeam"])
            if key in seen:
                continue

            seen.add(key)
            records.append(record)

    if not records:
        print(f"[AVISO] Nenhum record extraído para {league_key}")
        return

    df = pd.DataFrame(records)
    df = df[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].copy()
    df["_parsed_date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
    df = df.sort_values(["_parsed_date", "HomeTeam", "AwayTeam"], ascending=[True, True, True])
    df = df.drop(columns=["_parsed_date"])

    output_path = DATA_RAW_DIR / f"{league_key}.csv"
    df.to_csv(output_path, index=False, encoding="utf-8")

    print(f"[HIST] saved data_raw/{league_key}.csv rows={len(df)}")


def main():
    cfg = load_config()

    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Lisbon"))
    except Exception:
        now = datetime.utcnow()

    current_year = now.year
    current_month = now.month

    print(f"[DBG] Current year={current_year} month={current_month}")
    print(f"[DBG] Leagues to fetch: {sorted(LEAGUE_INFO.keys())}")

    for league_key in sorted(LEAGUE_INFO.keys()):
        seasons = get_historical_seasons(cfg, league_key, current_year, current_month)
        generate_historical_csv(cfg, league_key, seasons)

    print("\n[FIM] Histórico atualizado com sucesso!")


if __name__ == "__main__":
    main()
