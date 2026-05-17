from pathlib import Path

import pandas as pd
from src.calculations import (
    compute_lambdas,
    prob_over25,
    prob_btts_yes_adjusted,
    kelly_fraction,
    clamp_prob_o25,
    clamp_prob_btts,
    clamp_edge_o25,
    clamp_edge_btts,
)
from src.data_loader import normalize_columns, _to_float, get_btts_odd


def build_base_row(fx: pd.Series, league_key: str, league_name: str, lam_h: float, lam_a: float, lam_t: float) -> dict:
    return {
        "Date": fx["Date"],
        "League": league_key,
        "LeagueName": league_name,
        "HomeTeam": str(fx["HomeTeam"]),
        "AwayTeam": str(fx["AwayTeam"]),
        "LambdaHome": lam_h,
        "LambdaAway": lam_a,
        "LambdaTotal": lam_t,
    }


def generate_over25_pick(base_row: dict, fx: pd.Series) -> dict | None:
    odd25 = _to_float(fx.get("Odd_Over25", 0.0), 0.0)
    if odd25 <= 1.01:
        return None

    lam_t = float(base_row.get("LambdaTotal", 0.0) or 0.0)
    p25_raw = prob_over25(lam_t)
    p25 = clamp_prob_o25(p25_raw)
    pm25 = 1.0 / odd25
    edge25 = clamp_edge_o25(p25 - pm25)
    k25 = kelly_fraction(p25, odd25)

    return {
        **base_row,
        "Market": "O2.5",
        "ProbModel": p25,
        "Odd": odd25,
        "ProbMarket": pm25,
        "Edge": edge25,
        "KellyTrue": k25,
    }


def generate_btts_pick(base_row: dict, fx: pd.Series) -> dict | None:
    odd_btts = get_btts_odd(fx)
    if odd_btts <= 1.01:
        return None

    lam_h = float(base_row.get("LambdaHome", 0.0) or 0.0)
    lam_a = float(base_row.get("LambdaAway", 0.0) or 0.0)
    pbtts_raw = prob_btts_yes_adjusted(lam_h, lam_a)
    pbtts = clamp_prob_btts(pbtts_raw)
    pmbtts = 1.0 / odd_btts
    edgebtts = clamp_edge_btts(pbtts - pmbtts)
    kbtts = kelly_fraction(pbtts, odd_btts)

    return {
        **base_row,
        "Market": "BTTS",
        "ProbModel": pbtts,
        "Odd": odd_btts,
        "ProbMarket": pmbtts,
        "Edge": edgebtts,
        "KellyTrue": kbtts,
    }


def process_league_fixtures(
    fixtures: pd.DataFrame,
    league_key: str,
    league_meta: dict,
    history_cfg: dict,
    window: int,
    decay: float,
    min_games_home: int,
    min_games_away: int,
    data_raw_dir: Path,
) -> tuple[list[dict], list[dict], int]:
    rows25: list[dict] = []
    rows_btts: list[dict] = []
    total_fixture_errors = 0

    league_fixt = fixtures[fixtures["League"] == league_key].copy()
    if league_fixt.empty:
        print(f"[FIXTURE SKIP] league={league_key.upper()} reason=no_matches")
        return rows25, rows_btts, total_fixture_errors

    hist_path = data_raw_dir / f"{league_key}.csv"
    if not hist_path.exists():
        print(f"[WARN] histórico em falta para {league_key}")
        return rows25, rows_btts, total_fixture_errors

    df_hist = pd.read_csv(hist_path, sep=None, engine="python")
    df_hist = normalize_columns(df_hist)

    need_hist = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not need_hist.issubset(set(df_hist.columns)):
        print(f"{league_key}: histórico sem colunas necessárias -> {sorted(df_hist.columns)}")
        return rows25, rows_btts, total_fixture_errors

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

            base_row = build_base_row(fx, league_key, league_name, lam_h, lam_a, lam_t)

            p25_row = generate_over25_pick(base_row, fx)
            if p25_row is not None:
                rows25.append(p25_row)

            pbtts_row = generate_btts_pick(base_row, fx)
            if pbtts_row is not None:
                rows_btts.append(pbtts_row)

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

    return rows25, rows_btts, total_fixture_errors
