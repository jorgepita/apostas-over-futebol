import math

import pandas as pd


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


def btts_prob_diagnostics(lam_home: float, lam_away: float, adj: float = 0.885) -> dict:
    """
    Compute BTTS adjusted probability with all intermediate values exposed for calibration.
    Returns a dict; the final probability is in key 'final_prob_unclamped'.
    Default adj=0.885 preserves existing production behaviour exactly.
    """
    lam_home = max(0.0, float(lam_home))
    lam_away = max(0.0, float(lam_away))

    p_home0 = math.exp(-lam_home)
    p_away0 = math.exp(-lam_away)
    raw_poisson = 1.0 - p_home0 - p_away0 + (p_home0 * p_away0)
    after_base_adj = raw_poisson * adj

    bigger = max(lam_home, lam_away)
    smaller = min(lam_home, lam_away)
    ratio = (bigger / smaller) if smaller > 0 else 99.0
    gap = abs(lam_home - lam_away)
    product = lam_home * lam_away

    pen_ratio = 0.88 if ratio >= 2.50 else (0.93 if ratio >= 2.10 else 1.0)
    pen_gap = 0.90 if gap >= 1.10 else (0.95 if gap >= 0.90 else 1.0)
    pen_smaller = 0.91 if smaller < 0.55 else (0.96 if smaller < 0.70 else 1.0)
    pen_product = 0.92 if product < 0.55 else (0.97 if product < 0.70 else 1.0)
    total_penalty = pen_ratio * pen_gap * pen_smaller * pen_product

    final_unclamped = float(max(0.0, min(1.0, after_base_adj * total_penalty)))

    return {
        "raw_poisson": round(raw_poisson, 6),
        "base_adj_factor": round(adj, 4),
        "after_base_adj": round(after_base_adj, 6),
        "pen_ratio": pen_ratio,
        "pen_gap": pen_gap,
        "pen_smaller": pen_smaller,
        "pen_product": pen_product,
        "total_penalty": round(total_penalty, 6),
        "final_prob_unclamped": round(final_unclamped, 6),
        "lam_ratio": round(ratio, 4),
        "lam_gap": round(gap, 4),
        "lam_product": round(product, 4),
    }


def prob_btts_yes_adjusted(lam_home: float, lam_away: float, adj: float = 0.885) -> float:
    """
    BTTS ajustado para reduzir inflação do Poisson puro.
    adj is configurable (config.json calibration.btts_probability_adjustment).
    Default 0.885 preserves existing production behaviour exactly.
    """
    return btts_prob_diagnostics(lam_home, lam_away, adj=adj)["final_prob_unclamped"]


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
