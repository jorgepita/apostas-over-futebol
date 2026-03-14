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

# Ligas (sport keys do The Odds API)
SPORTS = {
    "premier": "soccer_epl",
    "portugal": "soccer_portugal_primeira_liga",
    "alemanha": "soccer_germany_bundesliga",
    # "espanha": "soccer_spain_la_liga",
    # "franca": "soccer_france_ligue_one",
    # "italia": "soccer_italy_serie_a",
    # "paises_baixos": "soccer_netherlands_eredivisie",
}

# Mais regiões = mais bookmakers / mais linhas
REGIONS = "eu,uk"
MARKETS = "totals"
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
    if not API_KEY:
        raise SystemExit("Falta ODDS_API_KEY (define no Render -> Environment).")
    params = {
        "apiKey": API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
        "oddsFormat": ODDS_FORMAT,
    }
    return BASE.format(sport=sport_key) + "?" + urllib.parse.urlencode(params)


def pick_best_over_price(bookmakers: List[Dict[str, Any]], goal_line: float) -> Optional[float]:
    """
    Procura a melhor odd disponível para Over X.5 em todos os bookmakers.
    Devolve a maior odd válida encontrada.
    """
    best_price = None

    for bm in bookmakers or []:
        for m in bm.get("markets", []) or []:
            if m.get("key") != "totals":
                continue

            for o in m.get("outcomes", []) or []:
                try:
                    if o.get("name") != "Over":
                        continue

                    point = o.get("point")
                    price = o.get("price")

                    if point is None or price is None:
                        continue

                    if float(point) == float(goal_line):
                        price = float(price)
                        if price > 1.01:
                            if best_price is None or price > best_price:
                                best_price = price
                except Exception:
                    continue

    return best_price


def estimate_over15_from_over25(odd25: Optional[float]) -> Optional[float]:
    """
    Fallback conservador para estimar O1.5 a partir de O2.5.
    Não é perfeito, mas é muito melhor do que odd=0.

    Exemplo:
    O2.5 @ 1.80 -> O1.5 ~ 1.44
    O2.5 @ 2.00 -> O1.5 ~ 1.55
    """
    if odd25 is None or odd25 <= 1.01:
        return None

    est = 1.0 + (odd25 - 1.0) * 0.55

    # intervalo realista
    est = max(1.12, min(1.80, est))
    return round(est, 2)


def iso_to_date_utc(iso_utc: str) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.date().isoformat()


def main():
    rows = []
    errors = []
    unauthorized_count = 0

    count_both_real = 0
    count_only_15_real = 0
    count_only_25_real = 0
    count_15_estimated = 0

    for league_key, sport_key in SPORTS.items():
        try:
            url = build_url(sport_key)
            data = http_get_json(url)
            print(f"[DBG] FETCH league={league_key} sport={sport_key} events={len(data or [])}")
        except Exception as e:
            msg = str(e)
            if ("HTTP Error 401" in msg) or ("401" in msg and "Unauthorized" in msg):
                unauthorized_count += 1
            errors.append(f"{league_key}: {e}")
            continue

        kept = 0

        for ev in data or []:
            home = ev.get("home_team")
            away = ev.get("away_team")
            commence = ev.get("commence_time")
            bms = ev.get("bookmakers", [])

            if not (home and away and commence):
                continue

            odd15_real = pick_best_over_price(bms, 1.5)
            odd25_real = pick_best_over_price(bms, 2.5)

            odd15_final = odd15_real
            odd25_final = odd25_real

            # fallback: se não houver O1.5 real mas houver O2.5, estimar O1.5
            if odd15_final is None and odd25_final is not None:
                odd15_final = estimate_over15_from_over25(odd25_final)
                if odd15_final is not None:
                    count_15_estimated += 1
                    print(
                        f"[INFO] O1.5 estimado -> {league_key} | {home} vs {away} | "
                        f"O2.5={odd25_final:.2f} => O1.5~{odd15_final:.2f}"
                    )

            # descartar se não houver nenhuma odd útil
            if odd15_final is None and odd25_final is None:
                continue

            if odd15_real is not None and odd25_real is not None:
                count_both_real += 1
            elif odd15_real is not None and odd25_real is None:
                count_only_15_real += 1
                print(
                    f"[WARN] Com O1.5 real mas sem O2.5 -> "
                    f"{league_key} | {home} vs {away} | O1.5={odd15_real:.2f}"
                )
            elif odd15_real is None and odd25_real is not None:
                count_only_25_real += 1
                print(
                    f"[WARN] Sem O1.5 real mas com O2.5 -> "
                    f"{league_key} | {home} vs {away} | O2.5={odd25_real:.2f}"
                )

            rows.append(
                {
                    "Date": iso_to_date_utc(commence),
                    "League": league_key,
                    "HomeTeam": home,
                    "AwayTeam": away,
                    "Odd_Over15": (f"{odd15_final:.2f}" if odd15_final is not None else ""),
                    "Odd_Over25": (f"{odd25_final:.2f}" if odd25_final is not None else ""),
                }
            )
            kept += 1

        print(f"[DBG] FETCH league={league_key} kept_rows={kept}")

    with open("fixtures_today.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["Date", "League", "HomeTeam", "AwayTeam", "Odd_Over15", "Odd_Over25"],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"OK fixtures_today.csv: {len(rows)} jogos (com O1.5 ou O2.5)")
    print(f"[DBG] Jogos com ambas odds reais: {count_both_real}")
    print(f"[DBG] Jogos só com O1.5 real: {count_only_15_real}")
    print(f"[DBG] Jogos só com O2.5 real: {count_only_25_real}")
    print(f"[DBG] O1.5 estimado a partir de O2.5: {count_15_estimated}")

    if errors:
        print("\nAvisos por liga:")
        for e in errors:
            print(" -", e)

    if unauthorized_count == len(SPORTS):
        raise SystemExit("ODDS_API_KEY inválida (401 em todas as ligas).")


if __name__ == "__main__":
    main()
