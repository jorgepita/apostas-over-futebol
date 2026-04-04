import base64
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib import request, parse, error
from datetime import datetime, timezone

import pandas as pd

BASE = Path(__file__).resolve().parent
DAILY_FILE = BASE / "picks_hoje_simplificado.csv"
HISTORY_FILE = BASE / "picks_history.csv"

API_TOKEN = os.getenv("FOOTBALL_DATA_API_KEY", "").strip()
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

GITHUB_OWNER = "jorgepita"
GITHUB_REPO = "apostas-over-futebol"
GITHUB_BRANCH = "main"

REMOTE_DAILY_NAME = "picks_hoje_simplificado.csv"
REMOTE_HISTORY_NAME = "picks_history.csv"

LEAGUE_CODE_MAP = {
    "Premier League": "PL",
    "Primeira Liga": "PPL",
    "Bundesliga": "BL1",
    "La Liga": "PD",
    "LaLiga": "PD",
    "Ligue 1": "FL1",
    "Serie A": "SA",
    "Eredivisie": "DED",
    "Championship": "ELC",
    "2. Bundesliga": "BL2",
    "Serie B": "SB",
    "Ligue 2": "FL2",
    "Belgian Pro League": "BSA",
    "Jupiler Pro League": "BSA",
    "Super Lig": "TSL",
    "Süper Lig": "TSL",
}

SUPPORTED_MARKETS = {"O1.5", "O2.5", "O3.5", "BTTS"}

CSV_COLUMNS = [
    "Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€", "Edge%",
    "Apostada", "OddReal", "StakeReal€",
    "Resultado", "Lucro€", "LucroReal€"
]

SYNC_RESULT_COLUMNS = [
    "Apostada", "OddReal", "StakeReal€",
    "Resultado", "Lucro€", "LucroReal€"
]

HTTP_TIMEOUT = 30

# football-data.org
FD_MAX_RETRIES = 4
FD_BASE_SLEEP = 1.5
FD_CALL_MIN_INTERVAL = 0.65

# API-Football
AF_MAX_RETRIES = 4
AF_BASE_SLEEP = 1.2
AF_CALL_MIN_INTERVAL = 0.50
AF_BASE_URL = "https://v3.football.api-sports.io"

# Confirmado pelos teus testes
BLOCKED_FOOTBALL_DATA_CODES = {"BL2", "TSL"}

API_FOOTBALL_FALLBACK_COMPETITIONS = {
    "BL2": {
        "country": "Germany",
        "name": "2. Bundesliga",
    },
    "TSL": {
        "country": "Turkey",
        "name": "Süper Lig",
    },
}

FD_FINISHED_STATUS = {"FINISHED"}
AF_FINISHED_STATUS = {"FT", "AET", "PEN"}


# =============================
# Helpers
# =============================
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

        df = pd.read_csv(path, sep=";", dtype=str).fillna("")
        return ensure_columns(df)

    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=CSV_COLUMNS)

    except Exception as e:
        print(f"[WARN] Erro a ler {path.name}: {e}")
        return pd.DataFrame(columns=CSV_COLUMNS)


def get_today_lisbon_iso() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Lisbon")).date().isoformat()
    except Exception:
        return datetime.utcnow().date().isoformat()


def is_future_date(date_str: str, today_iso: str) -> bool:
    try:
        return pd.to_datetime(date_str, errors="coerce").date().isoformat() > today_iso
    except Exception:
        return False


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


def api_football_season_from_date(date_str: str) -> int:
    dt = pd.to_datetime(date_str, errors="coerce")
    if pd.isna(dt):
        now = datetime.utcnow()
        return now.year if now.month >= 7 else now.year - 1

    if dt.month >= 7:
        return int(dt.year)
    return int(dt.year) - 1


# =============================
# football-data.org
# =============================
_fd_last_api_call_ts = 0.0


def _respect_fd_api_spacing():
    global _fd_last_api_call_ts
    now = time.monotonic()
    elapsed = now - _fd_last_api_call_ts
    if elapsed < FD_CALL_MIN_INTERVAL:
        time.sleep(FD_CALL_MIN_INTERVAL - elapsed)
    _fd_last_api_call_ts = time.monotonic()


def http_get_json_football_data(url: str, token: str):
    req = request.Request(
        url,
        headers={
            "X-Auth-Token": token,
            "Accept": "application/json",
            "User-Agent": "apostas-over-futebol/1.0",
        },
    )
    with request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_matches_for_league_date(league_code: str, date_str: str) -> list[dict]:
    url = (
        f"https://api.football-data.org/v4/competitions/{league_code}/matches"
        f"?dateFrom={parse.quote(date_str)}&dateTo={parse.quote(date_str)}"
    )

    last_error = None

    for attempt in range(1, FD_MAX_RETRIES + 1):
        try:
            _respect_fd_api_spacing()
            data = http_get_json_football_data(url, API_TOKEN)
            matches = data.get("matches", []) or []

            if attempt > 1:
                print(f"[DBG] football-data retry sucesso | league={league_code} | date={date_str} | tentativa={attempt}")

            return matches

        except error.HTTPError as e:
            last_error = e
            code = getattr(e, "code", None)

            if code == 429 and attempt < FD_MAX_RETRIES:
                wait_s = FD_BASE_SLEEP * (2 ** (attempt - 1))
                print(
                    f"[WARN] football-data rate limit 429 | league={league_code} | date={date_str} | "
                    f"tentativa={attempt}/{FD_MAX_RETRIES} | espera={wait_s:.1f}s"
                )
                time.sleep(wait_s)
                continue

            raise

        except Exception as e:
            last_error = e

            if attempt < FD_MAX_RETRIES:
                wait_s = FD_BASE_SLEEP * attempt
                print(
                    f"[WARN] football-data erro temporário | league={league_code} | date={date_str} | "
                    f"tentativa={attempt}/{FD_MAX_RETRIES} | espera={wait_s:.1f}s | erro={e}"
                )
                time.sleep(wait_s)
                continue

            raise

    if last_error:
        raise last_error

    return []


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

            return data

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


def get_api_football_league_id(fd_league_code: str, date_str: str, shared_state: dict) -> int | None:
    if not API_FOOTBALL_KEY:
        return None

    conf = API_FOOTBALL_FALLBACK_COMPETITIONS.get(fd_league_code)
    if not conf:
        return None

    season = api_football_season_from_date(date_str)
    cache_key = (fd_league_code, season)

    league_id_cache = shared_state["af_league_id_cache"]
    if cache_key in league_id_cache:
        return league_id_cache[cache_key]

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
    except Exception as e:
        print(f"[ERR] API-Football leagues lookup falhou | league={fd_league_code} | season={season} | erro={e}")
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
        f"[DBG] API-Football league id lookup | fd_code={fd_league_code} | "
        f"season={season} | target='{target_name}' | id={best_id} | score={best_score}"
    )
    return best_id


def fetch_api_football_fixtures_for_league_date(fd_league_code: str, date_str: str, shared_state: dict):
    if not API_FOOTBALL_KEY:
        return None, "NO_API_KEY"

    league_id = get_api_football_league_id(fd_league_code, date_str, shared_state)
    if not league_id:
        return None, "NO_LEAGUE_ID"

    season = api_football_season_from_date(date_str)
    cache_key = (fd_league_code, date_str, league_id, season)

    fixtures_cache = shared_state["af_fixtures_cache"]
    if cache_key in fixtures_cache:
        return fixtures_cache[cache_key]

    try:
        data = api_football_get(
            "/fixtures",
            {
                "league": league_id,
                "season": season,
                "date": date_str,
            },
        )
        fixtures = data.get("response", []) or []
        fixtures_cache[cache_key] = (fixtures, "")
        print(
            f"[DBG] API-Football fixtures | fd_code={fd_league_code} | league_id={league_id} | "
            f"season={season} | date={date_str} | jogos={len(fixtures)}"
        )
        return fixtures, ""

    except error.HTTPError as e:
        code = getattr(e, "code", None)
        reason = f"HTTP {code}" if code is not None else "HTTP"
        fixtures_cache[cache_key] = (None, reason)
        print(
            f"[ERR] API-Football fixtures falhou | fd_code={fd_league_code} | league_id={league_id} | "
            f"season={season} | date={date_str} | erro={reason}"
        )
        return None, reason

    except Exception as e:
        fixtures_cache[cache_key] = (None, "OTHER")
        print(
            f"[ERR] API-Football fixtures falhou | fd_code={fd_league_code} | league_id={league_id} | "
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
        return False, reason or "NO_FIXTURES"

    matched, best_score = choose_best_api_football_match(home_csv, away_csv, fixtures)
    if not matched:
        print(f"[WARN] {label}: API-Football sem match para: {jogo} | {league_code} | {data}")
        return False, "NO_MATCH"

    fixture = matched.get("fixture", {}) or {}
    status = (fixture.get("status", {}) or {}).get("short", "")
    status = str(status).upper()

    if status not in AF_FINISHED_STATUS:
        print(f"[DBG] {label}: API-Football ainda não terminado: {jogo} | status={status}")
        return False, "NOT_FINISHED"

    goals = matched.get("goals", {}) or {}
    home_goals = goals.get("home")
    away_goals = goals.get("away")

    if home_goals is None or away_goals is None:
        print(f"[WARN] {label}: API-Football sem goals finais para: {jogo}")
        return False, "NO_SCORE"

    resultado = market_result(mercado, int(home_goals), int(away_goals))
    if resultado is None:
        print(f"[WARN] {label}: Mercado não suportado no fallback API-Football: {mercado}")
        return False, "UNSUPPORTED_MARKET"

    lucro = calc_profit(resultado, stake, odd)
    df.at[idx, "Resultado"] = resultado
    df.at[idx, "Lucro€"] = str(lucro)

    lucro_real = calc_real_profit(
        row.get("Apostada", ""),
        resultado,
        parse_float(row.get("StakeReal€", ""), 0.0),
        parse_float(row.get("OddReal", ""), 0.0),
    )
    if lucro_real != "":
        df.at[idx, "LucroReal€"] = lucro_real

    print(
        f"[OK] {label}: API-Football fallback | {jogo} | {mercado} | "
        f"{home_goals}-{away_goals} => {resultado} | score_match={best_score} | "
        f"Lucro modelo {lucro} | Lucro real {lucro_real if lucro_real != '' else 'n/a'}"
    )
    return True, "UPDATED"


# =============================
# Shared state
# =============================
def make_shared_runtime_state():
    return {
        "fd_matches_cache": {},
        "af_fixtures_cache": {},
        "af_league_id_cache": {},
        "blocked_fd_leagues_seen": set(),
    }


# =============================
# Core update
# =============================
def update_dataframe(df: pd.DataFrame, label: str, shared_state: dict):
    df = ensure_columns(df)

    fd_matches_cache = shared_state["fd_matches_cache"]
    blocked_fd_leagues_seen = shared_state["blocked_fd_leagues_seen"]

    today_iso = get_today_lisbon_iso()

    updated = 0
    ignored = 0
    already_done = 0
    unsupported_market = 0
    missing_mapping = 0
    no_match_found = 0
    not_finished = 0
    future_skipped = 0

    api_403 = 0
    api_429 = 0
    api_other = 0

    af_used = 0
    af_updated = 0
    af_failed = 0

    for i, row in df.iterrows():
        resultado_atual = str(row.get("Resultado", "")).strip().upper()

        if resultado_atual in {"W", "L", "P"}:
            already_done += 1

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
            continue

        if str(mercado).strip().upper() not in SUPPORTED_MARKETS:
            print(f"[WARN] {label}: Mercado não suportado: {mercado}")
            unsupported_market += 1
            ignored += 1
            continue

        if is_future_date(data, today_iso):
            future_skipped += 1
            ignored += 1
            continue

        league_code = LEAGUE_CODE_MAP.get(liga)
        if not league_code:
            print(f"[WARN] {label}: Liga sem mapping: {liga}")
            missing_mapping += 1
            ignored += 1
            continue

        home_csv, away_csv = split_game(jogo)
        if not home_csv or not away_csv:
            print(f"[WARN] {label}: Jogo mal formatado: {jogo}")
            ignored += 1
            continue

        use_api_football_direct = league_code in BLOCKED_FOOTBALL_DATA_CODES

        if use_api_football_direct:
            blocked_fd_leagues_seen.add(league_code)
            af_used += 1
            ok, _ = try_update_row_via_api_football(
                df, i, row, league_code, label, shared_state
            )
            if ok:
                updated += 1
                af_updated += 1
            else:
                af_failed += 1
                ignored += 1
            continue

        cache_key = (league_code, data)

        if cache_key not in fd_matches_cache:
            try:
                matches = fetch_matches_for_league_date(league_code, data)
                fd_matches_cache[cache_key] = {
                    "ok": True,
                    "matches": matches,
                    "reason": "",
                }
                print(f"[DBG] {label}: {liga} {data}: {len(matches)} jogos encontrados")

            except error.HTTPError as e:
                code = getattr(e, "code", None)
                reason = f"HTTP {code}" if code is not None else "HTTP"
                fd_matches_cache[cache_key] = {
                    "ok": False,
                    "matches": [],
                    "reason": reason,
                }

                if code == 403:
                    api_403 += 1
                    print(f"[ERR] {label}: football-data {liga} {data}: HTTP Error 403")
                elif code == 429:
                    api_429 += 1
                    print(f"[ERR] {label}: football-data {liga} {data}: HTTP Error 429")
                else:
                    api_other += 1
                    print(f"[ERR] {label}: football-data {liga} {data}: HTTP Error {code}")

            except Exception as e:
                fd_matches_cache[cache_key] = {
                    "ok": False,
                    "matches": [],
                    "reason": "OTHER",
                }
                api_other += 1
                print(f"[ERR] {label}: football-data {liga} {data}: {e}")

        cache_entry = fd_matches_cache[cache_key]

        if not cache_entry["ok"] and cache_entry["reason"] == "HTTP 403" and league_code in API_FOOTBALL_FALLBACK_COMPETITIONS:
            blocked_fd_leagues_seen.add(league_code)
            af_used += 1
            ok, _ = try_update_row_via_api_football(
                df, i, row, league_code, label, shared_state
            )
            if ok:
                updated += 1
                af_updated += 1
            else:
                af_failed += 1
                ignored += 1
            continue

        if not cache_entry["ok"]:
            ignored += 1
            continue

        matches = cache_entry["matches"]
        matched, best_score = choose_best_match(home_csv, away_csv, matches)

        if not matched:
            print(f"[WARN] {label}: Sem match API para: {jogo} | {liga} | {data}")
            no_match_found += 1
            ignored += 1
            continue

        status = str(matched.get("status", "")).upper()
        if status not in FD_FINISHED_STATUS:
            print(f"[DBG] {label}: Ainda não terminado: {jogo} | status={status}")
            not_finished += 1
            ignored += 1
            continue

        score = matched.get("score", {}) or {}
        ft = score.get("fullTime", {}) or {}
        home_goals = ft.get("home")
        away_goals = ft.get("away")

        if home_goals is None or away_goals is None:
            print(f"[WARN] {label}: Sem fullTime score para: {jogo}")
            ignored += 1
            continue

        resultado = market_result(mercado, int(home_goals), int(away_goals))
        if resultado is None:
            print(f"[WARN] {label}: Mercado não suportado: {mercado}")
            unsupported_market += 1
            ignored += 1
            continue

        lucro = calc_profit(resultado, stake, odd)

        df.at[i, "Resultado"] = resultado
        df.at[i, "Lucro€"] = str(lucro)

        lucro_real = calc_real_profit(
            row.get("Apostada", ""),
            resultado,
            parse_float(row.get("StakeReal€", ""), 0.0),
            parse_float(row.get("OddReal", ""), 0.0),
        )
        if lucro_real != "":
            df.at[i, "LucroReal€"] = lucro_real

        updated += 1

        print(
            f"[OK] {label}: football-data | {jogo} | {mercado} | {home_goals}-{away_goals} "
            f"=> {resultado} | score_match={best_score} | "
            f"Lucro modelo {lucro} | Lucro real {lucro_real if lucro_real != '' else 'n/a'}"
        )

    print(
        f"[DBG] {label} resumo -> "
        f"updated={updated} | already_done={already_done} | ignored={ignored} | "
        f"missing_mapping={missing_mapping} | unsupported_market={unsupported_market} | "
        f"no_match_found={no_match_found} | not_finished={not_finished} | "
        f"future_skipped={future_skipped} | api_403={api_403} | api_429={api_429} | api_other={api_other} | "
        f"af_used={af_used} | af_updated={af_updated} | af_failed={af_failed} | "
        f"blocked_fd_leagues={sorted(blocked_fd_leagues_seen) if blocked_fd_leagues_seen else []}"
    )

    return ensure_columns(df), updated, already_done, ignored


# =============================
# Main
# =============================
def main():
    if not API_TOKEN:
        raise SystemExit("Falta FOOTBALL_DATA_API_KEY no Render")

    if not API_FOOTBALL_KEY:
        print("[WARN] API_FOOTBALL_KEY não definida. O fallback para BL2/TSL não vai funcionar.")

    shared_state = make_shared_runtime_state()

    daily_df = safe_read_csv(DAILY_FILE)
    history_df = safe_read_csv(HISTORY_FILE)

    history_df, h_updated, h_done, h_ignored = update_dataframe(history_df, "history", shared_state)
    history_df.to_csv(HISTORY_FILE, index=False, sep=";", encoding="utf-8")
    print(f"History atualizado: {h_updated} | já resolvidos: {h_done} | ignorados: {h_ignored}")

    daily_df, d_updated, d_done, d_ignored = update_dataframe(daily_df, "daily", shared_state)

    daily_df, d_synced = sync_daily_from_history(daily_df, history_df)
    daily_df.to_csv(DAILY_FILE, index=False, sep=";", encoding="utf-8")
    print(
        f"Daily atualizado: {d_updated} | já resolvidos: {d_done} | ignorados: {d_ignored} | "
        f"sincronizados via history: {d_synced}"
    )

    upload_csv_to_github(HISTORY_FILE, REMOTE_HISTORY_NAME)
    upload_csv_to_github(DAILY_FILE, REMOTE_DAILY_NAME)


if __name__ == "__main__":
    main()
