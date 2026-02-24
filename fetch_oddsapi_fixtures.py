import os, json, csv
import urllib.parse, urllib.request
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List


API_KEY = os.getenv("ODDS_API_KEY", "").strip()
BASE = "https://api.the-odds-api.com/v4/sports/{sport}/odds"

# Ligas (sport keys do The Odds API)
SPORTS = {
    "premier": "soccer_epl",
    "portugal": "soccer_portugal_primeira_liga",
    "espanha": "soccer_spain_la_liga",
    "franca": "soccer_france_ligue_one",
    "italia": "soccer_italy_serie_a",
    "alemanha": "soccer_germany_bundesliga",
    "paises_baixos": "soccer_netherlands_eredivisie",
}

REGIONS = "eu"
MARKETS = "totals"
ODDS_FORMAT = "decimal"


def http_get_json(url: str):
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "apostas-over-futebol/1.0"},
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


def pick_over_price(bookmakers: List[Dict[str, Any]], goal_line: float) -> Optional[float]:
    for bm in bookmakers or []:
        for m in bm.get("markets", []) or []:
            if m.get("key") != "totals":
                continue
            for o in m.get("outcomes", []) or []:
                try:
                    if o.get("name") == "Over" and float(o.get("point")) == float(goal_line):
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
    rows = []
    errors = []
    unauthorized_count = 0

    for league_key, sport_key in SPORTS.items():
        try:
            url = build_url(sport_key)
            data = http_get_json(url)
        except Exception as e:
            msg = str(e)
            if "HTTP Error 401" in msg or "401" in msg and "Unauthorized" in msg:
                unauthorized_count += 1
            errors.append(f"{league_key}: {e}")
            continue

        for ev in data or []:
            home = ev.get("home_team")
            away = ev.get("away_team")
            commence = ev.get("commence_time")
            bms = ev.get("bookmakers", [])

            if not (home and away and commence):
                continue

            odd15 = pick_over_price(bms, 1.5)
            odd25 = pick_over_price(bms, 2.5)

            if odd15 is None or odd25 is None:
                continue

            rows.append(
                {
                    "Date": iso_to_date_utc(commence),
                    "League": league_key,
                    "HomeTeam": home,
                    "AwayTeam": away,
                    "Odd_Over15": f"{odd15:.2f}",
                    "Odd_Over25": f"{odd25:.2f}",
                }
            )

    # Escrever sempre o CSV (para não partir o passo seguinte)
    with open("fixtures_today.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["Date", "League", "HomeTeam", "AwayTeam", "Odd_Over15", "Odd_Over25"],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"OK fixtures_today.csv: {len(rows)} jogos com O1.5 e O2.5")

    if errors:
        print("\nAvisos por liga:")
        for e in errors:
            print(" -", e)

    # Se TODAS as ligas deram 401, é key errada -> falhar job (alerta no run_job.py)
    if unauthorized_count == len(SPORTS):
        raise SystemExit("ODDS_API_KEY inválida (401 em todas as ligas).")


if __name__ == "__main__":
    main()