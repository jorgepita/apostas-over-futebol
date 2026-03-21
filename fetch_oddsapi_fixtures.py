import os
import json
import csv
import base64
import urllib.parse
import urllib.request
from urllib import error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List


BASE_DIR = Path(__file__).resolve().parent

API_KEY = os.getenv("ODDS_API_KEY", "").strip()
print(f"[DBG] ODDS_API_KEY len = {len(API_KEY)}")

BASE_ODDS = "https://api.the-odds-api.com/v4/sports/{sport}/odds"
BASE_EVENT_ODDS = "https://api.the-odds-api.com/v4/sports/{sport}/events/{event_id}/odds"

SPORTS = {
    "premier": "soccer_epl",
    "portugal": "soccer_portugal_primeira_liga",
    "alemanha": "soccer_germany_bundesliga",
    # "espanha": "soccer_spain_la_liga",
    # "franca": "soccer_france_ligue_one",
    # "italia": "soccer_italy_serie_a",
    # "paises_baixos": "soccer_netherlands_eredivisie",
}

REGIONS = "eu,uk"
ODDS_FORMAT = "decimal"


def http_get_json(url: str):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "apostas-over-futebol/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def build_totals_url(sport_key: str) -> str:
    if not API_KEY:
        raise SystemExit("Falta ODDS_API_KEY (define no Render -> Environment).")

    params = {
        "apiKey": API_KEY,
        "regions": REGIONS,
        "markets": "totals",
        "oddsFormat": ODDS_FORMAT,
    }
    return BASE_ODDS.format(sport=sport_key) + "?" + urllib.parse.urlencode(params)


def build_btts_url(sport_key: str, event_id: str) -> str:
    if not API_KEY:
        raise SystemExit("Falta ODDS_API_KEY (define no Render -> Environment).")

    params = {
        "apiKey": API_KEY,
        "regions": REGIONS,
        "markets": "btts",
        "oddsFormat": ODDS_FORMAT,
    }
    return BASE_EVENT_ODDS.format(sport=sport_key, event_id=event_id) + "?" + urllib.parse.urlencode(params)


def pick_best_over25_price(bookmakers: List[Dict[str, Any]]) -> Optional[float]:
    best_price = None

    for bm in bookmakers or []:
        for market in bm.get("markets", []) or []:
            if market.get("key") != "totals":
                continue

            for outcome in market.get("outcomes", []) or []:
                try:
                    if outcome.get("name") != "Over":
                        continue

                    point = outcome.get("point")
                    price = outcome.get("price")

                    if point is None or price is None:
                        continue

                    if float(point) == 2.5:
                        price = float(price)
                        if price > 1.01:
                            if best_price is None or price > best_price:
                                best_price = price
                except Exception:
                    continue

    return best_price


def pick_best_btts_yes_price(bookmakers: List[Dict[str, Any]]) -> Optional[float]:
    best_price = None

    for bm in bookmakers or []:
        for market in bm.get("markets", []) or []:
            if market.get("key") != "btts":
                continue

            for outcome in market.get("outcomes", []) or []:
                try:
                    name = str(outcome.get("name", "")).strip().lower()
                    price = outcome.get("price")

                    if price is None:
                        continue

                    if name in {"yes", "sim"}:
                        price = float(price)
                        if price > 1.01:
                            if best_price is None or price > best_price:
                                best_price = price
                except Exception:
                    continue

    return best_price


def iso_to_date_utc(iso_utc: str) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.date().isoformat()


def fetch_btts_for_event(sport_key: str, event_id: str) -> Optional[float]:
    try:
        url = build_btts_url(sport_key, event_id)
        data = http_get_json(url)
        bookmakers = data.get("bookmakers", []) if isinstance(data, dict) else []
        return pick_best_btts_yes_price(bookmakers)
    except Exception as e:
        print(f"[WARN] BTTS fetch falhou sport={sport_key} event={event_id} -> {e}")
        return None


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


def main():
    rows = []
    errors = []
    unauthorized_count = 0

    count_o25_real = 0
    count_btts_real = 0
    count_both_real = 0
    count_events_seen = 0
    count_btts_requests = 0

    for league_key, sport_key in SPORTS.items():
        try:
            url = build_totals_url(sport_key)
            data = http_get_json(url)
            print(f"[DBG] FETCH TOTALS league={league_key} sport={sport_key} events={len(data or [])}")
        except Exception as e:
            msg = str(e)
            if ("HTTP Error 401" in msg) or ("401" in msg and "Unauthorized" in msg):
                unauthorized_count += 1
            errors.append(f"{league_key}: {e}")
            continue

        kept = 0

        for ev in data or []:
            count_events_seen += 1

            event_id = ev.get("id")
            home = ev.get("home_team")
            away = ev.get("away_team")
            commence = ev.get("commence_time")
            bms = ev.get("bookmakers", [])

            if not (event_id and home and away and commence):
                continue

            odd25 = pick_best_over25_price(bms)

            count_btts_requests += 1
            odd_btts = fetch_btts_for_event(sport_key, event_id)

            if odd25 is None and odd_btts is None:
                continue

            if odd25 is not None:
                count_o25_real += 1
            if odd_btts is not None:
                count_btts_real += 1
            if odd25 is not None and odd_btts is not None:
                count_both_real += 1

            rows.append(
                {
                    "Date": iso_to_date_utc(commence),
                    "League": league_key,
                    "HomeTeam": home,
                    "AwayTeam": away,
                    "Odd_Over25": (f"{odd25:.2f}" if odd25 is not None else ""),
                    "Odd_BTTS_Yes": (f"{odd_btts:.2f}" if odd_btts is not None else ""),
                }
            )
            kept += 1

        print(f"[DBG] FETCH league={league_key} kept_rows={kept}")

    fixtures_path = BASE_DIR / "fixtures_today.csv"
    with open(fixtures_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["Date", "League", "HomeTeam", "AwayTeam", "Odd_Over25", "Odd_BTTS_Yes"],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"OK fixtures_today.csv: {len(rows)} jogos (com O2.5 ou BTTS)")
    print(f"[DBG] Eventos vistos: {count_events_seen}")
    print(f"[DBG] Requests BTTS por evento: {count_btts_requests}")
    print(f"[DBG] Jogos com O2.5 real: {count_o25_real}")
    print(f"[DBG] Jogos com BTTS real: {count_btts_real}")
    print(f"[DBG] Jogos com ambos os mercados: {count_both_real}")

    if errors:
        print("\nAvisos por liga:")
        for e in errors:
            print(" -", e)

    if unauthorized_count == len(SPORTS):
        raise SystemExit("ODDS_API_KEY inválida (401 em todas as ligas).")

    owner = "jorgepita"
    repo = "apostas-over-futebol"
    branch = "main"
    upload_file_to_github(fixtures_path, owner, repo, branch)


if __name__ == "__main__":
    main()
