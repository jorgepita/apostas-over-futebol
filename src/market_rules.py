import pandas as pd
from collections import Counter

DEFAULT_MAX_ODD_O25 = 2.20
DEFAULT_MAX_ODD_BTTS = 2.20

DEFAULT_KELLY_FRACTION = 0.18
DEFAULT_CAP_FRAC = 0.04
DEFAULT_DAILY_CAP_FRAC = 0.12


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

    if market == "O2.5":
        return {
            **base,
            "lam_t_min": 1.90,
            "odd_min": 1.55,
            "odd_max": DEFAULT_MAX_ODD_O25,
            "edge_min_quality": 0.00,
        }

    if market == "BTTS":
        return {
            **base,
            "lam_h_min": 0.75,
            "lam_a_min": 0.75,
            "lam_t_min": 2.05,
            "odd_min": 1.55,
            "odd_max": DEFAULT_MAX_ODD_BTTS,
            "edge_min_quality": 0.00,
            "max_lambda_ratio": 1.65,
            "max_lambda_gap": 0.65,
            "min_lambda_product": 0.80,
        }

    return base


def get_effective_max_odd(rules: dict, market: str, mode: str) -> float:
    market = str(market).strip().upper()
    th = get_market_thresholds(mode, market)
    th_max = float(th.get("odd_max", 99.0))

    if market == "O2.5":
        fallback = DEFAULT_MAX_ODD_O25
    elif market == "BTTS":
        fallback = DEFAULT_MAX_ODD_BTTS
    else:
        fallback = th_max

    rules_max = rules.get("odd_max", fallback)
    try:
        rules_max = float(rules_max)
    except Exception:
        rules_max = fallback

    return float(min(th_max, rules_max))


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

    market_name = str(df["Market"].iloc[0]).strip().upper() if "Market" in df.columns and len(df) else label.strip().upper()
    effective_max_odd = get_effective_max_odd(rules, market_name, mode)
    df = df[df["Odd"] <= effective_max_odd].copy()
    print(f"[DBG] {label}: após filtro odd_max = {len(df)} | odd_max={effective_max_odd:.2f}")

    if df.empty:
        return df

    edge_min_base = float(rules.get("edge_min", 0.05))
    edge_max = float(rules.get("edge_max", 0.15))

    def dynamic_edge_min(row, edge_min_base):
        odd = float(row.get("Odd", 0.0) or 0.0)

        edge_req = edge_min_base

        if odd >= 2.05:
            edge_req += 0.04
        elif odd >= 1.90:
            edge_req += 0.025
        elif odd >= 1.75:
            edge_req += 0.015

        return edge_req

    df["EdgeMinDynamic"] = df.apply(lambda r: dynamic_edge_min(r, edge_min_base), axis=1)

    df = df[
        (df["Edge"] >= df["EdgeMinDynamic"]) &
        (df["Edge"] <= edge_max)
    ].copy()

    print(f"[DBG] {label}: após edge dinâmico = {len(df)}")

    if df.empty:
        return df

    df = add_rank_fields(df)
    df = dedupe_correlated_picks(df)

    print(f"[DBG] {label}: após dedupe = {len(df)}")

    return df


def apply_stakes(df: pd.DataFrame, bankroll: float, rules: dict, label: str) -> pd.DataFrame:
    if df.empty:
        return df

    kfrac = float(rules.get("kelly_fraction", DEFAULT_KELLY_FRACTION))
    cap_frac = float(rules.get("cap_frac", DEFAULT_CAP_FRAC))
    daily_cap_frac = float(rules.get("daily_cap_frac", DEFAULT_DAILY_CAP_FRAC))
    min_picks = int(rules.get("min_picks", 1))

    df = df.copy()

    # base Kelly
    kelly = pd.to_numeric(df["KellyTrue"], errors="coerce").fillna(0.0)

    # confiança baseada no edge (0% → 0 | 10%+ → 1)
    edge = pd.to_numeric(df["Edge"], errors="coerce").fillna(0.0)
    confidence_factor = (edge / 0.10).clip(lower=0.0, upper=1.0)

    # stake ajustado
    df["StakeFracRaw"] = kelly * kfrac * confidence_factor
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

    print(
        f"[DBG] {label}: final após stake = {len(df)} | "
        f"kelly_fraction={kfrac} | cap_frac={cap_frac} | "
        f"daily_cap_frac={daily_cap_frac} | scale={scale:.4f}"
    )

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
