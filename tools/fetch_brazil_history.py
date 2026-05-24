"""
Fetch Brazil Serie A historical match results from API-Football.

Downloads seasons 2022, 2023, 2024 and writes to data_raw/brasil.csv.
Team names come from the same API used for live fixtures, so they will
match without any normalization step.

Usage:
    API_FOOTBALL_KEY=<key> python fetch_brazil_history.py

    Or with .env loaded automatically (same as other scripts in this repo).
"""

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "data_raw" / "brasil.csv"

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
API_FOOTBALL_BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io").strip()

BRAZIL_LEAGUE_ID = 71
# 3 full seasons + ongoing current season
SEASONS = [2022, 2023, 2024, 2025]
# Minimum inter-request gap (API-Football free plan: 10 req/min)
MIN_INTERVAL = 6.5

_last_call = 0.0


def _http_get(path: str, params: dict) -> dict:
    global _last_call
    elapsed = time.monotonic() - _last_call
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_call = time.monotonic()

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
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_season(season: int) -> list[dict]:
    data = _http_get("/fixtures", {
        "league": BRAZIL_LEAGUE_ID,
        "season": season,
        "status": "FT",
    })
    resp = data.get("response", []) if isinstance(data, dict) else []
    errors = data.get("errors") if isinstance(data, dict) else None
    if errors:
        print(f"  [WARN] API errors: {errors}")
    return resp


def parse_fixture(item: dict) -> tuple | None:
    fixture = item.get("fixture") or {}
    teams = item.get("teams") or {}
    score = item.get("score") or {}
    goals = item.get("goals") or {}

    date_str = fixture.get("date", "")
    home = ((teams.get("home") or {}).get("name") or "").strip()
    away = ((teams.get("away") or {}).get("name") or "").strip()

    ft = score.get("fulltime") or {}
    hg = ft.get("home") if ft.get("home") is not None else goals.get("home")
    ag = ft.get("away") if ft.get("away") is not None else goals.get("away")

    if not home or not away or hg is None or ag is None:
        return None

    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        date_fmt = dt.strftime("%d/%m/%Y")
    except Exception:
        return None

    return (date_fmt, home, away, int(hg), int(ag))


def main():
    if not API_FOOTBALL_KEY:
        raise SystemExit("API_FOOTBALL_KEY not set. Export it or add to .env")

    all_rows: list[tuple] = []
    per_season: dict[int, int] = {}

    for season in SEASONS:
        print(f"[FETCH] season={season} league=Brasil Serie A (id={BRAZIL_LEAGUE_ID}) ...")
        fixtures = fetch_season(season)
        n = len(fixtures)
        print(f"  API returned {n} finished fixtures")

        parsed = 0
        skipped = 0
        for item in fixtures:
            row = parse_fixture(item)
            if row:
                all_rows.append(row)
                parsed += 1
            else:
                skipped += 1

        per_season[season] = parsed
        print(f"  Parsed {parsed}  Skipped {skipped}")

    # Sort chronologically
    all_rows.sort(key=lambda x: datetime.strptime(x[0], "%d/%m/%Y"))

    # Deduplicate (date+home+away key)
    seen: set[tuple] = set()
    unique_rows: list[tuple] = []
    for row in all_rows:
        key = (row[0], row[1], row[2])
        if key not in seen:
            seen.add(key)
            unique_rows.append(row)

    with open(OUTPUT_PATH, "w", encoding="utf-8", newline="") as f:
        f.write("Date,HomeTeam,AwayTeam,FTHG,FTAG\n")
        for row in unique_rows:
            f.write(f"{row[0]},{row[1]},{row[2]},{row[3]},{row[4]}\n")

    print(f"\n{'='*55}")
    print(f"Output: {OUTPUT_PATH}")
    print(f"Total rows written: {len(unique_rows)}")
    print(f"\nPer-season breakdown:")
    for s, n in per_season.items():
        print(f"  {s}: {n} matches")

    if unique_rows:
        dates = [datetime.strptime(r[0], "%d/%m/%Y") for r in unique_rows]
        print(f"\nDate range: {min(dates).strftime('%Y-%m-%d')} .. {max(dates).strftime('%Y-%m-%d')}")
        teams = sorted(set(r[1] for r in unique_rows) | set(r[2] for r in unique_rows))
        print(f"Unique teams: {len(teams)}")
        for t in teams:
            print(f"  {t}")
    print('='*55)
    print("\nNext step: python validate_brasil.py")


if __name__ == "__main__":
    main()
