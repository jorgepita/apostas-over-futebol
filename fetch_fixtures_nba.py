# fetch_fixtures_nba.py
import os
import json
import csv
from urllib import request, parse
from datetime import datetime, timezone

API_KEY = os.getenv("ODDS_API_KEY", "").strip()
BASE = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"

REGIONS = os.getenv("ODDS_REGIONS", "us")
MARKETS = "totals"
ODDS_FORMAT = "decimal"


def http_get_json(url: str):
    req = request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "nba-bot/1.0"},
    )
    with request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def build_url():
    if not API_KEY:
        raise SystemExit("Falta ODDS_API_KEY.")
    params = {
        "apiKey": API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
        "oddsFormat": ODDS_FORMAT,
    }
    return BASE + "?" + parse.urlencode(params)


def iso_to_date(iso_utc: str) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.date().isoformat()


def extract_over_lines(event):
    rows = []
    for bm in event.get("bookmakers", []):
        book = bm.get("key")
        for market in bm.get("markets", []):
            if market.get("key") != "totals":
                continue
            for outcome in market.get("outcomes", []):
                if outcome.get("name") == "Over":
                    rows.append({
                        "Book": book,
                        "Line": outcome.get("point"),
                        "Odd": outcome.get("price"),
                    })
    return rows


def main():
    url = build_url()
    data = http_get_json(url)

    rows = []

    for ev in data:
        home = ev.get("home_team")
        away = ev.get("away_team")
        commence = ev.get("commence_time")

        if not (home and away and commence):
            continue

        overs = extract_over_lines(ev)
        if not overs:
            continue

        for o in overs:
            rows.append({
                "Date": iso_to_date(commence),
                "League": "nba",
                "HomeTeam": home,
                "AwayTeam": away,
                "Book": o["Book"],
                "Line": o["Line"],
                "Odd": o["Odd"],
            })

    with open("fixtures_today_nba.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["Date", "League", "HomeTeam", "AwayTeam", "Book", "Line", "Odd"],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"OK fixtures_today_nba.csv: {len(rows)} linhas")


if __name__ == "__main__":
    main()
