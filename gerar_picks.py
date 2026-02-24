# gerar_picks.py
import json
import math
import os
from pathlib import Path
from urllib import request, parse
from datetime import date, timedelta

import pandas as pd

BASE = Path(__file__).resolve().parent


# -----------------------------
# Helpers estatísticos / modelo
# -----------------------------
def safe_mean(series) -> float:
    if series is None:
        return 0.0
    try:
        if len(series) == 0:
            return 0.0
    except Exception:
        return 0.0
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return 0.0
    return float(s.mean())


def poisson_cdf(k: int, lam: float) -> float:
    """P(X <= k) para X ~ Poisson(lam)."""
    if lam <= 0:
        return 1.0 if k >= 0 else 0.0
    term = math.exp(-lam)
    s = term
    for i in range(1, k + 1):
        term *= lam / i
        s += term
    return float(min(1.0, max(0.0, s)))


def prob_over_line(lam_total: float, line: float) -> float:
    """
    Para total goals ~ Poisson(lam_total).
    Over 1.5 => >=2 => 1 - P(X<=1)
    Over 2.5 => >=3 => 1 - P(X<=2)
    """
    k = int(math.floor(line))
    return 1.0 - poisson_cdf(k, lam_total)


def kelly_fraction(p: float, odd: float) -> float:
    """Kelly "true": f = (p*odd - 1)/(odd-1), com piso 0."""
    if odd is None or odd <= 1.0:
        return 0.0
    f = (p * odd - 1.0) / (odd - 1.0)
    return max(0.0, float(f))


def league_avgs(df_hist: pd.DataFrame) -> tuple[float, float]:
    return (
        safe_mean(df_hist.get("FTHG", pd.Series(dtype=float))),
        safe_mean(df_hist.get("FTAG", pd.Series(dtype=float))),
    )


def last_n_home(df_hist: pd.DataFrame, team: str, n: int) -> pd.DataFrame:
    d = df_hist[df_hist["HomeTeam"] == team].sort_values("Date")
    return d.tail(n)


def last_n_away(df_hist: pd.DataFrame, team: str, n: int) -> pd.DataFrame:
    d = df_hist[df_hist["AwayTeam"] == team].sort_values("Date")
    return d.tail(n)


def compute_lambdas(df_hist: pd.DataFrame, home: str, away: str, window: int) -> tuple[float, float, float]:
    """
    Modelo simples:
    lambdaHome = avg_home * home_attack * away_defense
    lambdaAway = avg_away * away_attack * home_defense
    """
    avg_home, avg_away = league_avgs(df_hist)
    if avg_home <= 0:
        avg_home = 1.2
    if avg_away <= 0:
        avg_away = 1.0

    h_last = last_n_home(df_hist, home, window)
    a_last = last_n_away(df_hist, away, window)

    home_scored = safe_mean(h_last.get("FTHG", pd.Series(dtype=float)))
    home_attack = (home_scored / avg_home) if avg_home > 0 else 1.0

    home_conceded = safe_mean(h_last.get("FTAG", pd.Series(dtype=float)))
    home_defense = (home_conceded / avg_away) if avg_away > 0 else 1.0

    away_scored = safe_mean(a_last.get("FTAG", pd.Series(dtype=float)))
    away_attack = (away_scored / avg_away) if avg_away > 0 else 1.0

    away_conceded = safe_mean(a_last.get("FTHG", pd.Series(dtype=float)))
    away_defense = (away_conceded / avg_home) if avg_home > 0 else 1.0

    lam_home = avg_home * home_attack * away_defense
    lam_away = avg_away * away_attack * home_defense

    lam_home = float(max(0.05, min(6.0, lam_home)))
    lam_away = float(max(0.05, min(6.0, lam_away)))
    lam_total = lam_home + lam_away
    return lam_home, lam_away, lam_total


# -----------------------------
# Telegram
# -----------------------------
def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    with request.urlopen(req, timeout=20) as resp:
        _ = resp.read()


# -----------------------------
# Regras de mercado / stakes
# -----------------------------
def apply_market_rules(rows: list[dict], bankroll: float, rules: dict) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    edge_min = float(rules.get("edge_min", 0.0))
    df = df[df["Edge"] >= edge_min].copy()
    if df.empty:
        return df

    kfrac = float(rules.get("kelly_fraction", 0.25))
    cap_frac = float(rules.get("cap_frac", 0.05))
    daily_cap_frac = float(rules.get("daily_cap_frac", 0.15))
    min_picks = int(rules.get("min_picks", 1))

    df["StakeFracRaw"] = df["KellyTrue"] * kfrac
    df["StakeFrac"] = df["StakeFracRaw"].clip(lower=0.0, upper=cap_frac)

    if len(df) < min_picks:
        return df.iloc[0:0].copy()

    total_frac = float(df["StakeFrac"].sum())
    scale = 1.0
    if total_frac > daily_cap_frac and total_frac > 0:
        scale = daily_cap_frac / total_frac
        df["StakeFrac"] = df["StakeFrac"] * scale

    df["Stake€"] = df["StakeFrac"] * float(bankroll)
    df["DailyScale"] = float(scale)
    df["Bankroll€"] = float(bankroll)

    df = df.sort_values(["Edge", "KellyTrue"], ascending=[False, False]).reset_index(drop=True)

    round_cols = {
        "LambdaHome": 3,
        "LambdaAway": 3,
        "LambdaTotal": 3,
        "ProbModel": 3,
        "ProbMarket": 3,
        "Edge": 4,
        "KellyTrue": 4,
        "StakeFracRaw": 4,
        "StakeFrac": 4,
        "Stake€": 2,
    }
    for col, dec in round_cols.items():
        if col in df.columns:
            df[col] = df[col].round(dec)

    return df


# -----------------------------
# Main
# -----------------------------
def main():
    cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))

    fixtures_path = BASE / "fixtures_today.csv"
    if not fixtures_path.exists():
        raise SystemExit("Falta fixtures_today.csv na pasta do projeto.")

    fixtures = pd.read_csv(fixtures_path)

    required = {"Date", "League", "HomeTeam", "AwayTeam", "Odd_Over15", "Odd_Over25"}
    if not required.issubset(set(fixtures.columns)):
        raise SystemExit(f"fixtures_today.csv precisa das colunas: {sorted(required)}")

    fixtures["Date"] = pd.to_datetime(fixtures["Date"], dayfirst=True, errors="coerce").dt.date.astype(str)
    fixtures = fixtures.dropna(subset=["Date"]).copy()

    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    fixtures = fixtures[fixtures["Date"].isin([today, tomorrow])].copy()

    rows15, rows25 = [], []

    history_cfg = cfg.get("history", {})
    window = int(history_cfg.get("window", 10))

    for league_key, league_meta in cfg["leagues"].items():
        league_fixt = fixtures[fixtures["League"] == league_key].copy()
        if league_fixt.empty:
            continue

        hist_path = BASE / "data_raw" / f"{league_key}.csv"
        if not hist_path.exists():
            continue

        df_hist = pd.read_csv(hist_path)

        need_hist = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
        if not need_hist.issubset(set(df_hist.columns)):
            continue

        df_hist["Date"] = pd.to_datetime(df_hist["Date"], dayfirst=True, errors="coerce")
        df_hist = df_hist.dropna(subset=["Date"]).copy()

        league_name = league_meta.get("name", league_key)

        for _, fx in league_fixt.iterrows():
            home = str(fx["HomeTeam"])
            away = str(fx["AwayTeam"])

            lam_h, lam_a, lam_t = compute_lambdas(df_hist, home, away, window)

            p15 = prob_over_line(lam_t, 1.5)
            p25 = prob_over_line(lam_t, 2.5)

            odd15 = float(fx["Odd_Over15"]) if not pd.isna(fx["Odd_Over15"]) else 0.0
            odd25 = float(fx["Odd_Over25"]) if not pd.isna(fx["Odd_Over25"]) else 0.0

            pm15 = (1.0 / odd15) if odd15 > 1.0 else 0.0
            pm25 = (1.0 / odd25) if odd25 > 1.0 else 0.0

            edge15 = p15 - pm15
            edge25 = p25 - pm25

            k15 = kelly_fraction(p15, odd15)
            k25 = kelly_fraction(p25, odd25)

            base_row = {
                "Date": fx["Date"],
                "League": league_key,
                "LeagueName": league_name,
                "HomeTeam": home,
                "AwayTeam": away,
                "LambdaHome": lam_h,
                "LambdaAway": lam_a,
                "LambdaTotal": lam_t,
            }

            rows15.append(
                {
                    **base_row,
                    "Market": "O1.5",
                    "ProbModel": p15,
                    "Odd": odd15,
                    "ProbMarket": pm15,
                    "Edge": edge15,
                    "KellyTrue": k15,
                }
            )

            rows25.append(
                {
                    **base_row,
                    "Market": "O2.5",
                    "ProbModel": p25,
                    "Odd": odd25,
                    "ProbMarket": pm25,
                    "Edge": edge25,
                    "KellyTrue": k25,
                }
            )

    bankroll15 = float(cfg["bankroll"]["over15"])
    bankroll25 = float(cfg["bankroll"]["over25"])

    out15 = apply_market_rules(rows15, bankroll15, cfg["rules"]["over15"])
    out25 = apply_market_rules(rows25, bankroll25, cfg["rules"]["over25"])

    out15_path = BASE / "picks_over15.csv"
    out25_path = BASE / "picks_over25.csv"
    combo_path = BASE / "picks_hoje.csv"

    out15.to_csv(out15_path, index=False)
    out25.to_csv(out25_path, index=False)

    combo = pd.concat([out15, out25], ignore_index=True)
    combo.to_csv(combo_path, index=False)

    print("OK. Gerados:")
    print(f"- {out15_path.name} ({len(out15)} picks)")
    print(f"- {out25_path.name} ({len(out25)} picks)")
    print(f"- {combo_path.name} ({len(combo)} picks)")

    # ==========================
    # Telegram (mensagens separadas por mercado)
    # ==========================
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
    CHAT_ID = os.getenv("CHAT_ID", "").strip()

    def _send_in_chunks(text: str, title: str):
        MAX = 3900
        if not text:
            return
        if len(text) <= MAX:
            send_telegram_message(TELEGRAM_TOKEN, CHAT_ID, text)
            return

        parts = []
        cur = ""
        for line in text.splitlines(True):
            if len(cur) + len(line) > MAX:
                parts.append(cur)
                cur = ""
            cur += line
        if cur:
            parts.append(cur)

        for i, p in enumerate(parts, 1):
            prefix = f"{title} ({i}/{len(parts)})\n"
            send_telegram_message(TELEGRAM_TOKEN, CHAT_ID, prefix + p)

    def build_message(df: pd.DataFrame, titulo: str) -> str:
        if df is None or len(df) == 0:
            return f"❌ {titulo}\nSem picks hoje (filtros não passaram)."

        # Texto simples (sem Markdown) para não partir por caracteres especiais
        msg = f"📊 {titulo}\n\n"
        for _, r in df.iterrows():
            msg += (
                f"{r['LeagueName']} | {r['HomeTeam']} vs {r['AwayTeam']}\n"
                f"Market: {r['Market']} @ {r['Odd']}\n"
                f"Edge: {r['Edge']:.2%} | Stake: {r['Stake€']:.2f}€\n\n"
            )
        return msg

    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            _send_in_chunks(build_message(out15, "PICKS OVER 1.5"), "PICKS OVER 1.5")
            _send_in_chunks(build_message(out25, "PICKS OVER 2.5"), "PICKS OVER 2.5")
            print("Telegram: mensagens O1.5 e O2.5 enviadas.")
        except Exception as e:
            print(f"Telegram: erro ao enviar -> {e}")
    else:
        print("Telegram: TOKEN ou CHAT_ID em falta (não enviei mensagem).")


if __name__ == "__main__":
    main()