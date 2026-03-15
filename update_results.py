import base64
import json
import os
import re
import unicodedata
from pathlib import Path
from urllib import request, parse, error
from datetime import datetime, timezone

import pandas as pd

BASE = Path(__file__).resolve().parent
FILE = BASE / "picks_hoje_simplificado.csv"

API_TOKEN = os.getenv("FOOTBALL_DATA_API_KEY", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

GITHUB_OWNER = "jorgepita"
GITHUB_REPO = "apostas-over-futebol"
GITHUB_BRANCH = "main"
REMOTE_CSV_NAME = "picks_hoje_simplificado.csv"

# football-data.org competition codes
LEAGUE_CODE_MAP = {
    "Premier League": "PL",
    "Primeira Liga": "PPL",
    "Bundesliga": "BL1",
}


# =============================
# Helpers
# =============================
def parse_float(v, default=0.0) -> float:
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return float(default)


def normalize_text(s: str) -> str:
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.replace("&", " and ")
    s = re.sub(r"\b(fc|cf|sc|sv|afc|sad|club|deportivo|futebol)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def split_game(game: str) -> tuple[str, str] | tuple[None, None]:
    game = str(game).strip()
    if " vs " not in game:
        return None, None
    a, b = game.split(" vs ", 1)
    return a.strip(), b.strip()


def team_match_score(a: str, b: str) -> int:
    """
    score simples de correspondência entre nomes de equipa.
    quanto maior, melhor.
    """
    na = normalize_text(a)
    nb = normalize_text(b)

    if na == nb:
        return 100

    sa = set(na.split())
    sb = set(nb.split())

    if not sa or not sb:
        return 0

    inter = len(sa & sb)
    if inter == 0:
        return 0

    # favorece nomes muito parecidos
    score = inter * 10
    if na in nb or nb in na:
        score += 20

    return score


def games_match(csv_home: str, csv_away: str, api_home: str, api_away: str) -> bool:
    home_score = team_match_score(csv_home, api_home)
    away_score = team_match_score(csv_away, api_away)
    return home_score >= 10 and away_score >= 10


def market_result(market: str, home_goals: int, away_goals: int) -> str | None:
    total = home_goals + away_goals
    m = str(market).strip().upper()

    if m == "O2.5":
        return "W" if total >= 3 else "L"

    if m == "O1.5":
        return "W" if total >= 2 else "L"

    return None


def calc_profit(resultado: str, stake: float, odd: float) -> float:
    if resultado == "W":
        return round(stake * (odd - 1.0), 2)
    if resultado == "L":
        return round(-stake, 2)
    return 0.0


# =============================
# football-data.org
# =============================
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


def fetch_matches_for_league_date(league_code: str, date_str: str) -> list[dict]:
    url = (
        f"https://api.football-data.org/v4/competitions/{league_code}/matches"
        f"?dateFrom={parse.quote(date_str)}&dateTo={parse.quote(date_str)}"
    )
    data = http_get_json(url, API_TOKEN)
    return data.get("matches", []) or []


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


def upload_csv_to_github(local_path: Path, remote_name: str) -> None:
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


# =============================
# Main
# =============================
def main():
    if not FILE.exists():
        raise SystemExit("Falta picks_hoje_simplificado.csv")

    if not API_TOKEN:
        raise SystemExit("Falta FOOTBALL_DATA_API_KEY no Render")

    df = pd.read_csv(FILE, sep=";", dtype=str).fillna("")

    # garantir colunas
    for col in ["Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€", "Resultado", "Lucro€"]:
        if col not in df.columns:
            df[col] = ""

    # cache para evitar pedidos repetidos
    matches_cache: dict[tuple[str, str], list[dict]] = {}

    updated = 0
    ignored = 0
    already_done = 0

    for i, row in df.iterrows():
        resultado_atual = str(row.get("Resultado", "")).strip().upper()

        if resultado_atual in {"W", "L", "P"}:
            already_done += 1
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

        league_code = LEAGUE_CODE_MAP.get(liga)
        if not league_code:
            print(f"[WARN] Liga sem mapping: {liga}")
            ignored += 1
            continue

        home_csv, away_csv = split_game(jogo)
        if not home_csv or not away_csv:
            print(f"[WARN] Jogo mal formatado: {jogo}")
            ignored += 1
            continue

        cache_key = (league_code, data)
        if cache_key not in matches_cache:
            try:
                matches_cache[cache_key] = fetch_matches_for_league_date(league_code, data)
                print(f"[DBG] {liga} {data}: {len(matches_cache[cache_key])} jogos encontrados")
            except Exception as e:
                print(f"[ERR] API {liga} {data}: {e}")
                ignored += 1
                continue

        matches = matches_cache[cache_key]

        matched = None
        for m in matches:
            api_home = m.get("homeTeam", {}).get("name", "")
            api_away = m.get("awayTeam", {}).get("name", "")

            if games_match(home_csv, away_csv, api_home, api_away):
                matched = m
                break

        if not matched:
            print(f"[WARN] Sem match API para: {jogo} | {liga} | {data}")
            ignored += 1
            continue

        status = str(matched.get("status", "")).upper()
        if status != "FINISHED":
            print(f"[DBG] Ainda não terminado: {jogo} | status={status}")
            ignored += 1
            continue

        score = matched.get("score", {}) or {}
        ft = score.get("fullTime", {}) or {}
        home_goals = ft.get("home")
        away_goals = ft.get("away")

        if home_goals is None or away_goals is None:
            print(f"[WARN] Sem fullTime score para: {jogo}")
            ignored += 1
            continue

        resultado = market_result(mercado, int(home_goals), int(away_goals))
        if resultado is None:
            print(f"[WARN] Mercado não suportado: {mercado}")
            ignored += 1
            continue

        lucro = calc_profit(resultado, stake, odd)

        df.at[i, "Resultado"] = resultado
        df.at[i, "Lucro€"] = str(lucro)
        updated += 1

        print(
            f"[OK] {jogo} | {mercado} | {home_goals}-{away_goals} "
            f"=> {resultado} | Lucro {lucro}"
        )

    df.to_csv(FILE, index=False, sep=";")

    print(
        f"Resultados atualizados: {updated} | "
        f"já resolvidos: {already_done} | ignorados: {ignored}"
    )

    upload_csv_to_github(FILE, REMOTE_CSV_NAME)


if __name__ == "__main__":
    main()
