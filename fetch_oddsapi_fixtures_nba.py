# fetch_oddsapi_fixtures_nba.py
import os, json, csv
import urllib.parse, urllib.request
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List


API_KEY = os.getenv("ODDS_API_KEY", "").strip()
print(f"[DBG] ODDS_API_KEY len = {len(API_KEY)}")

BASE = "https://api.the-odds-api.com/v4/sports/{sport}/odds"

# NBA
SPORT_KEY = "basketball_nba"

REGIONS = "us"          # NBA tipicamente melhor em "us"
MARKETS = "totals"      # over/under
ODDS_FORMAT = "decimal"


def http_get_json(url: str):
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "apostas-bot/1.0"},
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def build_url(sport_key: str) -> str:
    if not API_KEY:
        raise SystemExit("Falta ODDS_API_KEY (define no Render -> Environment).")
    params = {
        "apiKey": API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
        "oddsFormat": ODDS_FORMAT,
    }
    return BASE.format(sport=sport_key) + "?" + urllib.parse.urlencode(params)


def pick_total_price(bookmakers: List[Dict[str, Any]], side: str, total_points: float) -> Optional[float]:
    # side: "Over" ou "Under"
    for bm in bookmakers or []:
        for m in bm.get("markets", []) or []:
            if m.get("key") != "totals":
                continue
            for o in m.get("outcomes", []) or []:
                try:
                    if o.get("name") == side and float(o.get("point")) == float(total_points):
                        price = o.get("price")
                        if price is not None:
                            return float(price)
                except Exception:
                    continue
    return None


def iso_to_date_utc(iso_utc: str) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.date().isoformat()


def main():
    url = build_url(SPORT_KEY)
    data = http_get_json(url)

    rows = []
    for ev in data or []:
        home = ev.get("home_team")
        away = ev.get("away_team")
        commence = ev.get("commence_time")
        bms = ev.get("bookmakers", [])

        if not (home and away and commence):
            continue

        # totals vêm com "point". Em NBA é tipo 224.5 etc.
        # Vamos tentar apanhar a linha mais comum (a primeira que aparecer).
        total_line = None
        for bm in bms or []:
            for m in bm.get("markets", []) or []:
                if m.get("key") != "totals":
                    continue
                outs = m.get("outcomes", []) or []
                # qualquer outcome tem "point"
                for o in outs:
                    try:
                        total_line = float(o.get("point"))
                        break
                    except Exception:
                        pass
                if total_line is not None:
                    break
            if total_line is not None:
                break

        if total_line is None:
            continue

        odd_over = pick_total_price(bms, "Over", total_line)
        odd_under = pick_total_price(bms, "Under", total_line)

        # para já só precisamos do Over, mas guardo Under também (pode dar jeito depois)
        if odd_over is None:
            continue

        rows.append(
            {
                "Date": iso_to_date_utc(commence),
                "League": "nba",
                "HomeTeam": home,
                "AwayTeam": away,
                "TotalLine": f"{total_line:.1f}",
                "Odd_Over": f"{odd_over:.2f}",
                "Odd_Under": f"{odd_under:.2f}" if odd_under is not None else "",
            }
        )

    with open("fixtures_today_nba.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["Date", "League", "HomeTeam", "AwayTeam", "TotalLine", "Odd_Over", "Odd_Under"],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"OK fixtures_today_nba.csv: {len(rows)} jogos NBA com totals")

if __name__ == "__main__":
    main()
