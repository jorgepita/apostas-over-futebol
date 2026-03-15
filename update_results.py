import base64
import json
import os
from pathlib import Path
from urllib import request, parse, error
from datetime import datetime, timedelta, timezone

import pandas as pd

BASE = Path(__file__).resolve().parent
FILE = BASE / "picks_hoje_simplificado.csv"

# football-data.org competition codes
LEAGUE_CODE_MAP = {
    "Premier League": "PL",
    "Primeira Liga": "PPL",
    "Bundesliga": "BL1",
}

API_TOKEN = os.getenv("FOOTBALL_DATA_API_KEY", "").strip()

# GitHub upload
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_OWNER = "jorgepita"
GITHUB_REPO = "apostas-over-futebol"
GITHUB_BRANCH = "main"


def http_get_json(url: str, token: str):
    req = request.Request(
        url,
        headers={
            "X-Auth-Token": token,
            "Accept": "application/json",
            "User-Agent": "apostas-over-futebol/1.0",
        },
    )
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
    with request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def github_get_sha(owner: str, repo: str, path: str, branch: str, token: str) -> str | None:
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


def upload_file_to_github(local_path: Path, remote_name: str) -> None:
    if not GITHUB_TOKEN:
        print("GitHub: GITHUB_TOKEN em falta, não atualizei o CSV no repositório.")
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


def normalize_name(s: str) -> str:
    return " ".join(str(s).strip().lower().split())


def parse_float(v, default=0.0) -> float:
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return float(default)


def market_won(market: str, home_goals: int, away_goals: int) -> bool | None:
    total = home_goals + away_goals
    m = str(market).strip().upper()
    if m == "O2.5":
        return total >= 3
    if m == "O1.5":
        return total >= 2
    return None


def fetch_finished_matches_for_date(league_code: str, date_str: str) -> list[dict]:
    url = (
        f"https://api.football-data.org/v4/competitions/{league_code}/matches"
        f"?status=FINISHED&dateFrom={date_str}&dateTo={date_str}"
    )
    data = http_get_json(url, API_TOKEN)
    return data.get("matches", []) or []


def build_match_index(matches: list[dict]) -> dict:
    idx = {}
    for m in matches:
        home = normalize_name(m.get("homeTeam", {}).get("name", ""))
        away = normalize_name(m.get("awayTeam", {}).get("name", ""))
        score = m.get("score", {}) or {}
        ft = score.get("fullTime", {}) or {}

        key = (home, away)
        idx[key] = {
            "status": m.get("status"),
            "winner": score.get("winner"),
            "home_goals": ft.get("home"),
            "away_goals": ft.get("away"),
        }
    return idx


def main():
    if not FILE.exists():
        raise SystemExit("Falta picks_hoje_simplificado.csv")

    if not API_TOKEN:
        raise SystemExit("Falta FOOTBALL_DATA_API_KEY no Render")

    df = pd.read_csv(FILE, sep=";", dtype=str).fillna("")

    for col in ["Resultado", "Lucro€", "Odd", "Stake€", "Liga", "Jogo", "Mercado", "Data"]:
        if col not in df.columns:
            df[col] = ""

    # cache por liga+data para não gastar pedidos
    cache: dict[tuple[str, str], dict] = {}

    updated = 0
    skipped = 0

    for i, row in df.iterrows():
        resultado_atual = str(row.get("Resultado", "")).strip().lower()
        if resultado_atual not in ["", "nan", "none"]:
            skipped += 1
            continue

        liga = str(row.get("Liga", "")).strip()
        data = str(row.get("Data", "")).strip()
        jogo = str(row.get("Jogo", "")).strip()
        mercado = str(row.get("Mercado", "")).strip()
        odd = parse_float(row.get("Odd", ""), 0.0)
        stake = parse_float(row.get("Stake€", ""), 0.0)

        if not liga or not data or not jogo or odd <= 1.01 or stake <= 0:
            skipped += 1
            continue

        league_code = LEAGUE_CODE_MAP.get(liga)
        if not league_code:
            skipped += 1
            continue

        try:
            home_name, away_name = [x.strip() for x in jogo.split(" vs ", 1)]
        except ValueError:
            skipped += 1
            continue

        cache_key = (league_code, data)
        if cache_key not in cache:
            matches = fetch_finished_matches_for_date(league_code, data)
            cache[cache_key] = build_match_index(matches)

        match_idx = cache[cache_key]
        result = match_idx.get((normalize_name(home_name), normalize_name(away_name)))

        if not result:
            skipped += 1
            continue

        if result.get("status") != "FINISHED":
            skipped += 1
            continue

        home_goals = result.get("home_goals")
        away_goals = result.get("away_goals")
        if home_goals is None or away_goals is None:
            skipped += 1
            continue

        won = market_won(mercado, int(home_goals), int(away_goals))
        if won is None:
            skipped += 1
            continue

        resultado = "W" if won else "L"
        lucro = round(stake * (odd - 1), 2) if won else round(-stake, 2)

        df.at[i, "Resultado"] = resultado
        df.at[i, "Lucro€"] = str(lucro)
        updated += 1

    df.to_csv(FILE, index=False, sep=";")
    print(f"Resultados atualizados: {updated} | ignorados: {skipped}")

    upload_file_to_github(FILE, "picks_hoje_simplificado.csv")


if __name__ == "__main__":
    main()
