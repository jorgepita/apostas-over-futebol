import os
import json
import csv
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List


API_KEY = os.getenv("ODDS_API_KEY", "").strip()
print(f"[DBG] ODDS_API_KEY len = {len(API_KEY)}")

BASE = "https://api.the-odds-api.com/v4/sports/{sport}/odds"

SPORTS = {
    "premier": "soccer_epl",
    "portugal": "soccer_portugal_primeira_liga",
    "alemanha": "soccer_germany_bundesliga",
}

REGIONS = "eu,uk"

# AGORA PEDE TOTALS E BTTS
MARKETS = "totals,btts"

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


def build_url(sport_key: str) -> str:
    params = {
        "apiKey": API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
        "oddsFormat": ODDS_FORMAT,
    }
    return BASE.format(sport=sport_key) + "?" + urllib.parse.urlencode(params)


def pick_best_over_price(bookmakers, goal_line):

    best_price = None

    for bm in bookmakers or []:
        for m in bm.get("markets", []) or []:

            if m.get("key") != "totals":
                continue

            for o in m.get("outcomes", []) or []:

                if o.get("name") != "Over":
                    continue

                if float(o.get("point", 0)) == goal_line:

                    price = float(o.get("price", 0))

                    if price > 1.01:
                        if best_price is None or price > best_price:
                            best_price = price

    return best_price


def pick_best_btts(bookmakers):

    best_price = None

    for bm in bookmakers or []:
        for m in bm.get("markets", []) or []:

            if m.get("key") != "btts":
                continue

            for o in m.get("outcomes", []) or []:

                if o.get("name") != "Yes":
                    continue

                price = float(o.get("price", 0))

                if price > 1.01:
                    if best_price is None or price > best_price:
                        best_price = price

    return best_price


def iso_to_date_utc(iso_utc: str) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.date().isoformat()


def main():

    rows = []

    for league_key, sport_key in SPORTS.items():

        try:

            url = build_url(sport_key)

            data = http_get_json(url)

            print(f"[DBG] {league_key} events = {len(data)}")

        except Exception as e:

            print(f"Erro {league_key} -> {e}")

            continue

        for ev in data:

            home = ev.get("home_team")
            away = ev.get("away_team")
            commence = ev.get("commence_time")

            if not home or not away or not commence:
                continue

            bms = ev.get("bookmakers", [])

            odd15 = pick_best_over_price(bms, 1.5)
            odd25 = pick_best_over_price(bms, 2.5)

            odd_btts = pick_best_btts(bms)

            if not odd15 and not odd25 and not odd_btts:
                continue

            rows.append(
                {
                    "Date": iso_to_date_utc(commence),
                    "League": league_key,
                    "HomeTeam": home,
                    "AwayTeam": away,
                    "Odd_Over15": f"{odd15:.2f}" if odd15 else "",
                    "Odd_Over25": f"{odd25:.2f}" if odd25 else "",
                    "Odd_BTTS_Yes": f"{odd_btts:.2f}" if odd_btts else "",
                }
            )

    with open("fixtures_today.csv", "w", newline="", encoding="utf-8") as f:

        w = csv.DictWriter(
            f,
            fieldnames=[
                "Date",
                "League",
                "HomeTeam",
                "AwayTeam",
                "Odd_Over15",
                "Odd_Over25",
                "Odd_BTTS_Yes",
            ],
        )

        w.writeheader()

        w.writerows(rows)

    print(f"OK fixtures_today.csv: {len(rows)} jogos")


if __name__ == "__main__":
    main()
