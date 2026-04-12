import base64
import json
import math
import os
from collections import Counter
from pathlib import Path
from urllib import request, parse, error
from datetime import datetime, timedelta, timezone

import pandas as pd

BASE = Path(__file__).resolve().parent
SENT_STATE_PATH = BASE / "sent_state.json"
HISTORY_PATH = BASE / "picks_history.csv"

DEFAULT_MAX_PICKS_PER_DAY = 12
DEFAULT_MAX_PICKS_GLOBAL = 36


# =============================
# Anti-duplicados (por dia)
# =============================
def load_sent_state(today_iso: str) -> set[str]:
    try:
        if not SENT_STATE_PATH.exists():
            return set()
        data = json.loads(SENT_STATE_PATH.read_text(encoding="utf-8"))
        if data.get("date") != today_iso:
            return set()
        sent_list = data.get("sent", [])
        return set(sent_list) if isinstance(sent_list, list) else set()
    except Exception:
        return set()


def save_sent_state(today_iso: str, sent: set[str]) -> None:
    payload = {"date": today_iso, "sent": sorted(sent)}
    SENT_STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def pick_id(row: dict) -> str:
    return f"{row['Date']}|{row['League']}|{row['HomeTeam']}|{row['AwayTeam']}|{row['Market']}"


def history_pick_id_from_simple(row: pd.Series) -> str:
    return (
        f"{str(row.get('Data', '')).strip()}|"
        f"{str(row.get('Liga', '')).strip()}|"
        f"{str(row.get('Jogo', '')).strip()}|"
        f"{str(row.get('Mercado', '')).strip()}"
    )


# =============================
# Helpers
# =============================
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    return df


def safe_mean(series) -> float:
    if series is None:
        return 0.0
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return 0.0
    return float(s.mean())


def weighted_mean(values, decay: float = 0.90) -> float:
    v = pd.to_numeric(pd.Series(values), errors="coerce").dropna().tolist()
    if not v:
        return 0.0
    n = len(v)
    weights = [decay ** (n - 1 - i) for i in range(n)]
    num = sum(v[i] * weights[i] for i in range(n))
    den = sum(weights)
    return float(num / den) if den > 0 else 0.0


def poisson_cdf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k >= 0 else 0.0
    term = math.exp(-lam)
    s = term
    for i in range(1, k + 1):
        term *= lam / i
        s += term
    return float(min(1.0, max(0.0, s)))


def prob_over25(lam_total: float) -> float:
    return 1.0 - poisson_cdf(2, lam_total)


def prob_btts_yes_adjusted(lam_home: float, lam_away: float) -> float:
    """
    BTTS ajustado para reduzir inflação do Poisson puro.
    Versão intermédia: menos agressiva, sem matar demasiado volume.
    """
    lam_home = max(0.0, float(lam_home))
    lam_away = max(0.0, float(lam_away))

    p_home0 = math.exp(-lam_home)
    p_away0 = math.exp(-lam_away)
    raw = 1.0 - p_home0 - p_away0 + (p_home0 * p_away0)

    # ligeiramente mais conservador que a versão atual
    adj = raw * 0.885

    bigger = max(lam_home, lam_away)
    smaller = min(lam_home, lam_away)
    ratio = (bigger / smaller) if smaller > 0 else 99.0
    gap = abs(lam_home - lam_away)
    product = lam_home * lam_away

    if ratio >= 2.50:
        adj *= 0.88
    elif ratio >= 2.10:
        adj *= 0.93

    if gap >= 1.10:
        adj *= 0.90
    elif gap >= 0.90:
        adj *= 0.95

    # travão leve quando uma equipa tem pouco peso ofensivo
    if smaller < 0.55:
        adj *= 0.91
    elif smaller < 0.70:
        adj *= 0.96

    # travão leve para combinações pouco equilibradas
    if product < 0.55:
        adj *= 0.92
    elif product < 0.70:
        adj *= 0.97

    return float(max(0.0, min(1.0, adj)))


def kelly_fraction(p: float, odd: float) -> float:
    if odd is None or odd <= 1.01:
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


def clamp_strength(x: float, lo: float = 0.80, hi: float = 1.30) -> float:
    return float(max(lo, min(hi, x)))


def compute_lambdas(
    df_hist: pd.DataFrame,
    home: str,
    away: str,
    window: int,
    decay: float,
    min_games_home: int,
    min_games_away: int,
) -> tuple[float, float, float]:
    avg_home, avg_away = league_avgs(df_hist)

    if avg_home <= 0:
        avg_home = 1.20
    if avg_away <= 0:
        avg_away = 1.00

    h_last = last_n_home(df_hist, home, window)
    a_last = last_n_away(df_hist, away, window)

    if len(h_last) < min_games_home or len(a_last) < min_games_away:
        lam_home = float(max(0.25, min(2.20, avg_home)))
        lam_away = float(max(0.20, min(1.90, avg_away)))
        return lam_home, lam_away, lam_home + lam_away

    home_scored = weighted_mean(h_last["FTHG"], decay=decay)
    home_conceded = weighted_mean(h_last["FTAG"], decay=decay)
    away_scored = weighted_mean(a_last["FTAG"], decay=decay)
    away_conceded = weighted_mean(a_last["FTHG"], decay=decay)

    home_attack = clamp_strength(home_scored / avg_home if avg_home > 0 else 1.0)
    home_defense = clamp_strength(home_conceded / avg_away if avg_away > 0 else 1.0)
    away_attack = clamp_strength(away_scored / avg_away if avg_away > 0 else 1.0)
    away_defense = clamp_strength(away_conceded / avg_home if avg_home > 0 else 1.0)

    lam_home = avg_home * home_attack * away_defense
    lam_away = avg_away * away_attack * home_defense

    lam_home = float(max(0.25, min(2.20, lam_home)))
    lam_away = float(max(0.20, min(1.90, lam_away)))

    return lam_home, lam_away, lam_home + lam_away


def clamp_prob_o25(prob: float) -> float:
    return float(max(0.22, min(0.72, prob)))


def clamp_prob_btts(prob: float) -> float:
    return float(max(0.22, min(0.68, prob)))


def clamp_edge_o25(edge: float) -> float:
    return float(max(-0.20, min(0.16, edge)))


def clamp_edge_btts(edge: float) -> float:
    return float(max(-0.20, min(0.14, edge)))


def ensure_simple_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cols = [
        "Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€", "Edge%",
        "Apostada", "OddReal", "StakeReal€",
        "Resultado", "Lucro€", "LucroReal€",
    ]
    for col in cols:
        if col not in df.columns:
            df[col] = ""
    return df[cols].copy()


def load_history() -> pd.DataFrame:
    cols = [
        "Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€", "Edge%",
        "Apostada", "OddReal", "StakeReal€",
        "Resultado", "Lucro€", "LucroReal€",
    ]
    if not HISTORY_PATH.exists():
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_csv(HISTORY_PATH, sep=";", dtype=str).fillna("")
        return ensure_simple_columns(df)
    except Exception:
        return pd.DataFrame(columns=cols)


def merge_into_history(simple_df: pd.DataFrame) -> pd.DataFrame:
    history = load_history()
    history = ensure_simple_columns(history)
    simple_df = ensure_simple_columns(simple_df)

    existing_ids = {history_pick_id_from_simple(row) for _, row in history.iterrows()}
    new_rows = []

    for _, row in simple_df.iterrows():
        pid = history_pick_id_from_simple(row)
        if pid not in existing_ids:
            new_rows.append(row.to_dict())

    if new_rows:
        history = pd.concat([history, pd.DataFrame(new_rows)], ignore_index=True)

    if "Data" in history.columns:
        history["_sort_date"] = pd.to_datetime(history["Data"], errors="coerce")
        history = history.sort_values(
            ["_sort_date", "Liga", "Jogo", "Mercado"],
            ascending=[True, True, True, True],
            na_position="last",
        )
        history = history.drop(columns=["_sort_date"])

    history = history.reset_index(drop=True)
    return ensure_simple_columns(history)


# =============================
# Telegram
# =============================
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


def _send_in_chunks(token: str, chat_id: str, text: str, title: str) -> None:
    max_len = 3900
    if not text:
        return
    if len(text) <= max_len:
        send_telegram_message(token, chat_id, text)
        return

    parts = []
    cur = ""
    for line in text.splitlines(True):
        if len(line) > max_len:
            if cur:
                parts.append(cur)
                cur = ""
            for i in range(0, len(line), max_len):
                parts.append(line[i:i + max_len])
            continue

        if len(cur) + len(line) > max_len:
            if cur:
                parts.append(cur)
            cur = line
        else:
            cur += line

    if cur:
        parts.append(cur)

    for i, p in enumerate(parts, 1):
        prefix = f"{title} ({i}/{len(parts)})\n"
        send_telegram_message(token, chat_id, prefix + p)


def df_to_rows(df: pd.DataFrame) -> list[dict]:
    if df is None or len(df) == 0:
        return []
    return df.to_dict(orient="records")


def build_message(rows: list[dict], titulo: str) -> str:
    if not rows:
        return ""

    def _sort_key(r: dict):
        try:
            edge = float(r.get("Edge", 0.0) or 0.0)
        except Exception:
            edge = 0.0
        try:
            kelly = float(r.get("KellyTrue", 0.0) or 0.0)
        except Exception:
            kelly = 0.0
        try:
            prob = float(r.get("ProbModel", 0.0) or 0.0)
        except Exception:
            prob = 0.0
        try:
            odd = float(r.get("Odd", 0.0) or 0.0)
        except Exception:
            odd = 0.0
        return (
            str(r.get("Date", "")),
            -edge,
            -kelly,
            -prob,
            -odd,
            str(r.get("LeagueName", "")),
            str(r.get("HomeTeam", "")),
        )

    rows_sorted = sorted(rows, key=_sort_key)

    grouped = {}
    for r in rows_sorted:
        grouped.setdefault(str(r.get("Date", "")), []).append(r)

    msg = f"📊 {titulo}\n\n"

    for date_key in sorted(grouped.keys()):
        msg += f"📅 {date_key}\n"
        for r in grouped[date_key]:
            try:
                edge_txt = f"{float(r['Edge']):.2%}"
            except Exception:
                edge_txt = "—"
            try:
                stake_txt = f"{float(r.get('Stake€', 0.0)):.2f}€"
            except Exception:
                stake_txt = "0.00€"

            msg += (
                f"{r['LeagueName']} | {r['HomeTeam']} vs {r['AwayTeam']}\n"
                f"Market: {r['Market']} @ {r['Odd']}\n"
                f"Edge: {edge_txt} | Stake: {stake_txt}\n\n"
            )

    return msg.strip()


# =============================
# Modo normal / teste
# =============================
def get_run_mode(cfg: dict) -> str:
    mode = str(cfg.get("run", {}).get("mode", "normal")).strip().lower()
    return mode if mode in {"normal", "test"} else "normal"


def get_market_thresholds(mode: str, market: str) -> dict:
    market = str(market).strip().upper()

    base = {
        "lam_h_min": 0.0,
        "lam_a_min": 0.0,
        "lam_t_min": 0.0,
        "odd_min": 1.01,
        "odd_max": 99.0,
        "edge_min_quality": -1.0,
        "max_lambda_ratio": 99.0,
        "max_lambda_gap": 99.0,
        "min_lambda_product": 0.0,
    }

    if mode == "test":
        if market == "O2.5":
            return {
                **base,
                "lam_t_min": 1.70,
                "odd_min": 1.42,
                "odd_max": 2.90,
                "edge_min_quality": -0.03,
            }

        if market == "BTTS":
            return {
                **base,
                "lam_h_min": 0.62,
                "lam_a_min": 0.62,
                "lam_t_min": 1.88,
                "odd_min": 1.48,
                "odd_max": 2.60,
                "edge_min_quality": -0.04,
                "max_lambda_ratio": 1.90,
                "max_lambda_gap": 0.83,
                "min_lambda_product": 0.65,
            }

    if market == "O2.5":
        return {
            **base,
            "lam_t_min": 1.80,
            "odd_min": 1.50,
            "odd_max": 2.65,
            "edge_min_quality": -0.04,
        }

    if market == "BTTS":
        return {
            **base,
            "lam_h_min": 0.72,
            "lam_a_min": 0.72,
            "lam_t_min": 1.98,
            "odd_min": 1.50,
            "odd_max": 2.45,
            "edge_min_quality": -0.02,
            "max_lambda_ratio": 1.75,
            "max_lambda_gap": 0.72,
            "min_lambda_product": 0.74,
        }

    return base


# =============================
# Ranking limpo
# =============================
def add_rank_fields(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    for col in ["ProbModel", "ProbMarket", "Edge", "KellyTrue", "LambdaHome", "LambdaAway", "LambdaTotal", "Odd"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["ProbGap"] = df["ProbModel"] - df["ProbMarket"]
    return df


def dedupe_correlated_picks(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = add_rank_fields(df.copy())
    game_cols = ["Date", "League", "HomeTeam", "AwayTeam"]
    keep_rows = []

    for _, g in df.groupby(game_cols, dropna=False):
        g = g.sort_values(
            ["Edge", "KellyTrue", "ProbModel", "Odd"],
            ascending=[False, False, False, False],
        ).reset_index(drop=True)

        winner = g.iloc[0].to_dict()
        keep_rows.append(winner)

        try:
            date_txt = str(winner.get("Date", ""))
            league_txt = str(winner.get("LeagueName", winner.get("League", "")))
            game_txt = f"{winner.get('HomeTeam', '?')} vs {winner.get('AwayTeam', '?')}"
            winner_market = str(winner.get("Market", ""))
            winner_edge = float(winner.get("Edge", 0.0) or 0.0)
            winner_kelly = float(winner.get("KellyTrue", 0.0) or 0.0)
            winner_prob = float(winner.get("ProbModel", 0.0) or 0.0)
            winner_odd = float(winner.get("Odd", 0.0) or 0.0)

            if len(g) == 1:
                print(
                    f"[DBG] dedupe jogo | {date_txt} | {league_txt} | {game_txt} | "
                    f"única pick={winner_market} | "
                    f"edge={winner_edge:.4f} | kelly={winner_kelly:.4f} | "
                    f"prob={winner_prob:.4f} | odd={winner_odd:.2f}"
                )
            else:
                losers = []
                for i in range(1, len(g)):
                    row = g.iloc[i]
                    loser_market = str(row.get("Market", ""))
                    loser_edge = float(row.get("Edge", 0.0) or 0.0)
                    loser_kelly = float(row.get("KellyTrue", 0.0) or 0.0)
                    loser_prob = float(row.get("ProbModel", 0.0) or 0.0)
                    loser_odd = float(row.get("Odd", 0.0) or 0.0)
                    losers.append(
                        f"{loser_market}(edge={loser_edge:.4f}, kelly={loser_kelly:.4f}, "
                        f"prob={loser_prob:.4f}, odd={loser_odd:.2f})"
                    )

                print(
                    f"[DBG] dedupe jogo | {date_txt} | {league_txt} | {game_txt} | "
                    f"winner={winner_market}(edge={winner_edge:.4f}, kelly={winner_kelly:.4f}, "
                    f"prob={winner_prob:.4f}, odd={winner_odd:.2f}) | "
                    f"discarded=" + " ; ".join(losers)
                )
        except Exception as e:
            print(f"[DBG] dedupe jogo | erro a construir log: {e}")

    out = pd.DataFrame(keep_rows)
    out = out.sort_values(
        ["Date", "Edge", "KellyTrue", "ProbModel", "Odd"],
        ascending=[True, False, False, False, False],
    ).reset_index(drop=True)
    return out


def limit_picks_per_day(df: pd.DataFrame, max_per_day: int, max_global: int | None = None) -> pd.DataFrame:
    if df.empty:
        return df

    df = add_rank_fields(df.copy())
    kept = []

    for _, group in df.groupby("Date", sort=True, dropna=False):
        group_sorted = group.sort_values(
            ["Edge", "KellyTrue", "ProbModel", "Odd"],
            ascending=[False, False, False, False],
        ).head(max_per_day)
        kept.append(group_sorted)

    out = pd.concat(kept, ignore_index=True) if kept else df.iloc[0:0].copy()
    out = out.sort_values(
        ["Date", "Edge", "KellyTrue", "ProbModel", "Odd"],
        ascending=[True, False, False, False, False],
    ).reset_index(drop=True)

    if max_global is not None and max_global > 0:
        out = out.head(max_global).copy()

    return out


# =============================
# Qualidade / correlação
# =============================
def btts_balance_filter(row: dict, th: dict) -> tuple[bool, str]:
    lam_h = float(row.get("LambdaHome", 0.0) or 0.0)
    lam_a = float(row.get("LambdaAway", 0.0) or 0.0)

    bigger = max(lam_h, lam_a)
    smaller = min(lam_h, lam_a)
    ratio = (bigger / smaller) if smaller > 0 else 99.0
    gap = abs(lam_h - lam_a)
    product = lam_h * lam_a

    if ratio > float(th.get("max_lambda_ratio", 99.0)):
        return False, "btts_ratio"
    if gap > float(th.get("max_lambda_gap", 99.0)):
        return False, "btts_gap"
    if product < float(th.get("min_lambda_product", 0.0)):
        return False, "btts_product"

    return True, "ok"


def evaluate_market_quality(row: dict, mode: str = "normal") -> tuple[bool, str]:
    market = str(row.get("Market", "")).strip().upper()
    odd = float(row.get("Odd", 0.0) or 0.0)
    lam_h = float(row.get("LambdaHome", 0.0) or 0.0)
    lam_a = float(row.get("LambdaAway", 0.0) or 0.0)
    lam_t = float(row.get("LambdaTotal", 0.0) or 0.0)
    edge = float(row.get("Edge", 0.0) or 0.0)

    if odd <= 1.01:
        return False, "odd_invalid"

    th = get_market_thresholds(mode, market)

    if market == "O2.5":
        if lam_t < float(th["lam_t_min"]):
            return False, "lam_t_low"
        if odd < float(th["odd_min"]):
            return False, "odd_low"
        if odd > float(th["odd_max"]):
            return False, "odd_high"
        if edge < float(th["edge_min_quality"]):
            return False, "edge_quality_low"
        return True, "ok"

    if market == "BTTS":
        if lam_h < float(th["lam_h_min"]):
            return False, "lam_h_low"
        if lam_a < float(th["lam_a_min"]):
            return False, "lam_a_low"
        if lam_t < float(th["lam_t_min"]):
            return False, "lam_t_low"
        if odd < float(th["odd_min"]):
            return False, "odd_low"
        if odd > float(th["odd_max"]):
            return False, "odd_high"
        if edge < float(th["edge_min_quality"]):
            return False, "edge_quality_low"

        ok_balance, reason = btts_balance_filter(row, th)
        if not ok_balance:
            return False, reason

        return True, "ok"

    return True, "ok"


def market_quality_filter(row: dict, mode: str = "normal") -> bool:
    ok, _ = evaluate_market_quality(row, mode=mode)
    return ok


# =============================
# Regras de mercado / stake
# =============================
def apply_market_rules(rows: list[dict], bankroll: float, rules: dict, label: str, mode: str = "normal") -> pd.DataFrame:
    if not rows:
        print(f"[DBG] {label}: sem rows à entrada")
        return pd.DataFrame()

    print(f"[DBG] {label}: rows iniciais = {len(rows)}")

    quality_counter = Counter()
    filtered_rows = []

    for r in rows:
        ok, reason = evaluate_market_quality(r, mode=mode)
        quality_counter[reason] += 1
        if ok:
            filtered_rows.append(r)

    quality_parts = [f"{k}={v}" for k, v in sorted(quality_counter.items(), key=lambda x: (-x[1], x[0]))]
    print(f"[DBG] {label}: quality reasons -> " + (" | ".join(quality_parts) if quality_parts else "sem dados"))
    print(f"[DBG] {label}: após quality_filter = {len(filtered_rows)} | mode={mode}")

    if not filtered_rows:
        return pd.DataFrame()

    df = pd.DataFrame(filtered_rows).copy()
    df["Odd"] = pd.to_numeric(df["Odd"], errors="coerce")
    df["Edge"] = pd.to_numeric(df["Edge"], errors="coerce")
    df["KellyTrue"] = pd.to_numeric(df["KellyTrue"], errors="coerce").fillna(0.0)
    df["ProbModel"] = pd.to_numeric(df["ProbModel"], errors="coerce").fillna(0.0)

    df = df[df["Odd"] > 1.01].copy()
    df = df[df["Edge"].notna()].copy()
    print(f"[DBG] {label}: após odd/edge válidos = {len(df)}")

    if df.empty:
        return df

    edge_min = float(rules.get("edge_min", 0.0))
    edge_max = float(rules.get("edge_max", 0.15))
    df = df[(df["Edge"] >= edge_min) & (df["Edge"] <= edge_max)].copy()
    print(f"[DBG] {label}: após edge_min/edge_max = {len(df)} | edge_min={edge_min} edge_max={edge_max}")

    if df.empty:
        return df

    df = add_rank_fields(df)
    df = dedupe_correlated_picks(df)
    print(f"[DBG] {label}: após dedupe = {len(df)}")

    return df


def apply_stakes(df: pd.DataFrame, bankroll: float, rules: dict, label: str) -> pd.DataFrame:
    if df.empty:
        return df

    kfrac = float(rules.get("kelly_fraction", 0.25))
    cap_frac = float(rules.get("cap_frac", 0.05))
    daily_cap_frac = float(rules.get("daily_cap_frac", 0.15))
    min_picks = int(rules.get("min_picks", 1))

    df = df.copy()
    df["StakeFracRaw"] = pd.to_numeric(df["KellyTrue"], errors="coerce").fillna(0.0) * kfrac
    df["StakeFrac"] = df["StakeFracRaw"].clip(lower=0.0, upper=cap_frac)

    total_frac = float(df["StakeFrac"].sum())
    scale = 1.0
    if total_frac > daily_cap_frac and total_frac > 0:
        scale = daily_cap_frac / total_frac
        df["StakeFrac"] = df["StakeFrac"] * scale

    df["Stake€"] = (df["StakeFrac"] * float(bankroll)).round(2)
    df["DailyScale"] = float(scale)
    df["Bankroll€"] = float(bankroll)

    if len(df) < min_picks:
        print(f"[DBG] {label}: abaixo de min_picks={min_picks}")
        return df.iloc[0:0].copy()

    df = df[df["Stake€"] > 0].copy()
    print(f"[DBG] {label}: final após stake = {len(df)}")

    round_cols = {
        "LambdaHome": 3,
        "LambdaAway": 3,
        "LambdaTotal": 3,
        "ProbModel": 3,
        "ProbMarket": 3,
        "ProbGap": 3,
        "Edge": 4,
        "KellyTrue": 4,
        "StakeFracRaw": 4,
        "StakeFrac": 4,
        "Stake€": 2,
    }
    for col, dec in round_cols.items():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(dec)

    return df


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


def upload_csvs_to_github(files: list[Path], owner: str, repo: str, branch: str) -> None:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        print("GitHub: GITHUB_TOKEN em falta (não fiz upload).")
        return

    prefix = os.getenv("GITHUB_PATH_PREFIX", "").strip().strip("/")

    ok = 0
    for fp in files:
        if not fp.exists():
            continue

        rel_path = fp.name if not prefix else f"{prefix}/{fp.name}"

        try:
            content = fp.read_bytes()
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            msg = f"Update {fp.name} ({ts})"
            github_put_file(owner, repo, rel_path, content, branch, token, msg)
            ok += 1
        except Exception as e:
            print(f"GitHub: falhou upload de {fp.name} -> {e}")

    print(f"GitHub: upload concluído ({ok}/{len(files)} ficheiros).")


# =============================
# Main
# =============================
def main():
    cfg_path = BASE / "config.json"
    if not cfg_path.exists():
        raise SystemExit("Falta config.json na pasta do projeto.")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    run_mode = get_run_mode(cfg)
    print(f"[DBG] gerar_picks mode={run_mode}")

    run_cfg = cfg.get("run", {})
    max_picks_per_day = int(run_cfg.get("max_picks_per_day", DEFAULT_MAX_PICKS_PER_DAY))
    max_picks_global = int(run_cfg.get("max_picks_global", DEFAULT_MAX_PICKS_GLOBAL))
    print(f"[DBG] max_picks_per_day={max_picks_per_day} | max_picks_global={max_picks_global}")

    fixtures_path = BASE / "fixtures_today.csv"
    if not fixtures_path.exists():
        raise SystemExit("Falta fixtures_today.csv na pasta do projeto.")

    fixtures = pd.read_csv(fixtures_path, sep=None, engine="python")
    fixtures = normalize_columns(fixtures)

    required = {"Date", "League", "HomeTeam", "AwayTeam", "Odd_Over25"}
    if not required.issubset(set(fixtures.columns)):
        raise SystemExit(f"fixtures_today.csv precisa das colunas: {sorted(required)}")

    fixtures["Date"] = pd.to_datetime(fixtures["Date"], errors="coerce").dt.date
    fixtures = fixtures.dropna(subset=["Date"]).copy()

    try:
        from zoneinfo import ZoneInfo
        now_pt = datetime.now(ZoneInfo("Europe/Lisbon"))
    except Exception:
        now_pt = datetime.utcnow()

    days_ahead = int(cfg.get("run", {}).get("days_ahead", 1))
    days_ahead = max(1, days_ahead)
    start = now_pt.date()
    end = start + timedelta(days=days_ahead - 1)
    today_iso = start.isoformat()

    fixtures = fixtures[(fixtures["Date"] >= start) & (fixtures["Date"] <= end)].copy()
    fixtures["Date"] = fixtures["Date"].astype(str)

    print(f"[DBG] fixtures no range {start} -> {end}: {len(fixtures)}")

    rows25 = []
    rows_btts = []

    history_cfg = cfg.get("history", {})
    window = int(history_cfg.get("window", 12))
    decay = float(history_cfg.get("decay", 0.90))
    min_games_home = int(history_cfg.get("min_games_home", 8))
    min_games_away = int(history_cfg.get("min_games_away", 8))

    leagues_cfg = cfg.get("leagues", {})

    def _to_float(x, default=0.0):
        try:
            if x is None:
                return float(default)
            s = str(x).strip().replace(",", ".")
            if s == "":
                return float(default)
            return float(s)
        except Exception:
            return float(default)

    def get_btts_odd(fx_row) -> float:
        candidates = ["Odd_BTTS_Yes", "Odd_BTTS", "Odd_BTTSYes", "Odd_Btts_Yes", "Odd_Btts"]
        for col in candidates:
            if col in fixtures.columns:
                odd = _to_float(fx_row.get(col, 0.0), 0.0)
                if odd > 1.01:
                    return odd
        return 0.0

    total_fixture_errors = 0

    for league_key, league_meta in leagues_cfg.items():
        try:
            league_fixt = fixtures[fixtures["League"] == league_key].copy()
            print(f"[DBG] liga={league_key} | fixtures={len(league_fixt)}")
            if league_fixt.empty:
                continue

            hist_path = BASE / "data_raw" / f"{league_key}.csv"
            if not hist_path.exists():
                print(f"[WARN] histórico em falta para {league_key}")
                continue

            df_hist = pd.read_csv(hist_path, sep=None, engine="python")
            df_hist = normalize_columns(df_hist)

            need_hist = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
            if not need_hist.issubset(set(df_hist.columns)):
                print(f"{league_key}: histórico sem colunas necessárias -> {sorted(df_hist.columns)}")
                continue

            df_hist["Date"] = pd.to_datetime(df_hist["Date"], dayfirst=True, errors="coerce")
            df_hist = df_hist.dropna(subset=["Date"]).copy()

            league_name = league_meta.get("name", league_key)

            league_boosts = history_cfg.get("league_lambda_boost", {}) or {}
            lambda_boost = float(league_boosts.get(league_key, history_cfg.get("lambda_boost", 1.0)))

            for _, fx in league_fixt.iterrows():
                try:
                    home = str(fx["HomeTeam"])
                    away = str(fx["AwayTeam"])

                    lam_h, lam_a, lam_t = compute_lambdas(
                        df_hist,
                        home,
                        away,
                        window=window,
                        decay=decay,
                        min_games_home=min_games_home,
                        min_games_away=min_games_away,
                    )

                    if lambda_boost and lambda_boost != 1.0:
                        lam_h = max(0.25, min(2.20, lam_h * lambda_boost))
                        lam_a = max(0.20, min(1.90, lam_a * lambda_boost))
                        lam_t = lam_h + lam_a

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

                    odd25 = _to_float(fx.get("Odd_Over25", 0.0), 0.0)
                    if odd25 > 1.01:
                        p25_raw = prob_over25(lam_t)
                        p25 = clamp_prob_o25(p25_raw)
                        pm25 = 1.0 / odd25
                        edge25 = clamp_edge_o25(p25 - pm25)
                        k25 = kelly_fraction(p25, odd25)

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

                    odd_btts = get_btts_odd(fx)
                    if odd_btts > 1.01:
                        pbtts_raw = prob_btts_yes_adjusted(lam_h, lam_a)
                        pbtts = clamp_prob_btts(pbtts_raw)
                        pmbtts = 1.0 / odd_btts
                        edgebtts = clamp_edge_btts(pbtts - pmbtts)
                        kbtts = kelly_fraction(pbtts, odd_btts)

                        rows_btts.append(
                            {
                                **base_row,
                                "Market": "BTTS",
                                "ProbModel": pbtts,
                                "Odd": odd_btts,
                                "ProbMarket": pmbtts,
                                "Edge": edgebtts,
                                "KellyTrue": kbtts,
                            }
                        )

                except Exception as e:
                    total_fixture_errors += 1
                    try:
                        print(
                            f"[ERR] fixture {league_key} | "
                            f"{fx.get('HomeTeam', '?')} vs {fx.get('AwayTeam', '?')} -> {e}"
                        )
                    except Exception:
                        print(f"[ERR] fixture {league_key}: erro ao processar jogo -> {e}")
                    continue

        except Exception as e:
            print(f"[ERR] liga {league_key}: erro geral -> {e}")
            continue

    print(f"[DBG] candidatos O2.5 gerados = {len(rows25)}")
    print(f"[DBG] candidatos BTTS gerados = {len(rows_btts)}")
    print(f"[DBG] erros por fixture = {total_fixture_errors}")

    bankroll_cfg = cfg.get("bankroll", {})
    rules_cfg = cfg.get("rules", {})

    bankroll25 = float(bankroll_cfg.get("over25", 0.0))
    rules25 = dict(rules_cfg.get("over25", {}))
    rules25.setdefault("edge_max", 0.16)

    bankroll_btts = float(bankroll_cfg.get("btts", 0.0))
    rules_btts = dict(rules_cfg.get("btts", {}))
    rules_btts.setdefault("edge_max", 0.14)

    out25 = apply_market_rules(rows25, bankroll25, rules25, "O2.5", mode=run_mode)
    out_btts = apply_market_rules(rows_btts, bankroll_btts, rules_btts, "BTTS", mode=run_mode)

    combo_pre = pd.concat([out25, out_btts], ignore_index=True) if (len(out25) or len(out_btts)) else pd.DataFrame()

    if not combo_pre.empty:
        combo_pre = dedupe_correlated_picks(combo_pre)
        combo_pre = limit_picks_per_day(
            combo_pre,
            max_per_day=max_picks_per_day,
            max_global=max_picks_global,
        )
        print(
            f"[DBG] combo final limitado por dia | "
            f"max_per_day={max_picks_per_day} | max_global={max_picks_global} | total={len(combo_pre)}"
        )
    else:
        print("[DBG] combo final vazio antes do limite")

    if combo_pre.empty:
        out25_final = pd.DataFrame()
        out_btts_final = pd.DataFrame()
        combo = pd.DataFrame()
    else:
        out25_candidates = combo_pre[combo_pre["Market"] == "O2.5"].copy()
        out_btts_candidates = combo_pre[combo_pre["Market"] == "BTTS"].copy()

        out25_final = apply_stakes(out25_candidates, bankroll25, rules25, "O2.5")
        out_btts_final = apply_stakes(out_btts_candidates, bankroll_btts, rules_btts, "BTTS")

        combo = pd.concat([out25_final, out_btts_final], ignore_index=True) if (len(out25_final) or len(out_btts_final)) else pd.DataFrame()
        if not combo.empty:
            combo = add_rank_fields(combo)
            combo = limit_picks_per_day(
                combo,
                max_per_day=max_picks_per_day,
                max_global=max_picks_global,
            ).reset_index(drop=True)

    out25_path = BASE / "picks_over25.csv"
    out_btts_path = BASE / "picks_btts.csv"
    combo_path = BASE / "picks_hoje.csv"

    out25_final.to_csv(out25_path, index=False, encoding="utf-8", sep=";")
    out_btts_final.to_csv(out_btts_path, index=False, encoding="utf-8", sep=";")
    combo.to_csv(combo_path, index=False, encoding="utf-8", sep=";")

    combo_github_path = BASE / "picks_hoje_github.csv"
    combo.to_csv(combo_github_path, index=False, encoding="utf-8", sep=",")

    simple_path = BASE / "picks_hoje_simplificado.csv"
    if len(combo) > 0:
        simple = combo.copy()
        simple["Jogo"] = simple["HomeTeam"].astype(str) + " vs " + simple["AwayTeam"].astype(str)
        simple["Data"] = simple["Date"].astype(str)
        simple["Liga"] = simple["LeagueName"].astype(str)
        simple["Mercado"] = simple["Market"].astype(str)

        simple["Odd"] = pd.to_numeric(simple["Odd"], errors="coerce")
        simple["Stake€"] = pd.to_numeric(simple.get("Stake€", 0.0), errors="coerce")
        simple["Edge%"] = (pd.to_numeric(simple["Edge"], errors="coerce") * 100.0).round(2)

        simple["Apostada"] = ""
        simple["OddReal"] = ""
        simple["StakeReal€"] = ""
        simple["Resultado"] = ""
        simple["Lucro€"] = ""
        simple["LucroReal€"] = ""

        cols = [
            "Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€", "Edge%",
            "Apostada", "OddReal", "StakeReal€",
            "Resultado", "Lucro€", "LucroReal€",
        ]
        simple = simple[cols].copy()
        simple = simple[(simple["Odd"] > 1.01) & (simple["Stake€"] > 0) & (simple["Edge%"] > 0)].copy()
        simple.to_csv(simple_path, index=False, encoding="utf-8", sep=";")
    else:
        simple = pd.DataFrame(columns=[
            "Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€", "Edge%",
            "Apostada", "OddReal", "StakeReal€",
            "Resultado", "Lucro€", "LucroReal€",
        ])
        simple.to_csv(simple_path, index=False, encoding="utf-8", sep=";")

    history = merge_into_history(simple)
    history.to_csv(HISTORY_PATH, index=False, encoding="utf-8", sep=";")

    print("OK. Gerados:")
    print(f"- {out25_path.name} ({len(out25_final)} picks)")
    print(f"- {out_btts_path.name} ({len(out_btts_final)} picks)")
    print(f"- {combo_path.name} ({len(combo)} picks)")
    print(f"- {combo_github_path.name} ({len(combo)} picks)")
    print(f"- {simple_path.name} ({len(simple)} picks)")
    print(f"- {HISTORY_PATH.name} ({len(history)} linhas de histórico)")

    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
    CHAT_ID = os.getenv("CHAT_ID", "").strip()

    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            sent = load_sent_state(today_iso)

            new25 = []
            for r in df_to_rows(out25_final):
                pid = pick_id(r)
                if pid not in sent:
                    new25.append(r)

            new_btts = []
            for r in df_to_rows(out_btts_final):
                pid = pick_id(r)
                if pid not in sent:
                    new_btts.append(r)

            msg_25 = build_message(new25, "PICKS OVER 2.5 (NOVAS)")
            if msg_25:
                _send_in_chunks(TELEGRAM_TOKEN, CHAT_ID, msg_25, "PICKS OVER 2.5")

            msg_btts = build_message(new_btts, "PICKS BTTS (NOVAS)")
            if msg_btts:
                _send_in_chunks(TELEGRAM_TOKEN, CHAT_ID, msg_btts, "PICKS BTTS")

            for r in new25:
                sent.add(pick_id(r))
            for r in new_btts:
                sent.add(pick_id(r))

            save_sent_state(today_iso, sent)

            if msg_25:
                print(f"Telegram: enviei {len(new25)} novas O2.5.")
            else:
                print("Telegram: sem novas picks O2.5.")

            if msg_btts:
                print(f"Telegram: enviei {len(new_btts)} novas BTTS.")
            else:
                print("Telegram: sem novas picks BTTS.")

        except Exception as e:
            print(f"Telegram: erro ao enviar -> {e}")
    else:
        print("Telegram: TOKEN ou CHAT_ID em falta (não enviei mensagem).")

    owner = "jorgepita"
    repo = "apostas-over-futebol"
    branch = "main"
    upload_csvs_to_github(
        [out25_path, out_btts_path, combo_path, combo_github_path, simple_path, HISTORY_PATH],
        owner,
        repo,
        branch,
    )


if __name__ == "__main__":
    main()
