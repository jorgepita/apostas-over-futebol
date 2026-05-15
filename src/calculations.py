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

    if smaller < 0.55:
        adj *= 0.91
    elif smaller < 0.70:
        adj *= 0.96

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
