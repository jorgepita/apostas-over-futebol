from pathlib import Path

import pandas as pd
from src.calculations import (
    compute_lambdas,
    prob_over25,
    prob_btts_yes_adjusted,
    btts_prob_diagnostics,
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
        "KickoffUTC": str(fx.get("KickoffUTC", "") or ""),
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


def generate_btts_pick(base_row: dict, fx: pd.Series, btts_adj: float = 0.885) -> dict | None:
    odd_btts = get_btts_odd(fx)
    if odd_btts <= 1.01:
        return None

    lam_h = float(base_row.get("LambdaHome", 0.0) or 0.0)
    lam_a = float(base_row.get("LambdaAway", 0.0) or 0.0)
    diag = btts_prob_diagnostics(lam_h, lam_a, adj=btts_adj)
    pbtts_unclamped = diag["final_prob_unclamped"]
    pbtts = clamp_prob_btts(pbtts_unclamped)
    pmbtts = 1.0 / odd_btts
    edge_before_clamp = pbtts - pmbtts
    edgebtts = clamp_edge_btts(edge_before_clamp)
    kbtts = kelly_fraction(pbtts, odd_btts)

    return {
        **base_row,
        "Market": "BTTS",
        "ProbModel": pbtts,
        "Odd": odd_btts,
        "ProbMarket": pmbtts,
        "Edge": edgebtts,
        "KellyTrue": kbtts,
        # Calibration diagnostics — written to btts_diagnostics.csv, stripped before output CSVs
        "_diag_raw_poisson": diag["raw_poisson"],
        "_diag_base_adj_factor": diag["base_adj_factor"],
        "_diag_after_base_adj": diag["after_base_adj"],
        "_diag_pen_ratio": diag["pen_ratio"],
        "_diag_pen_gap": diag["pen_gap"],
        "_diag_pen_smaller": diag["pen_smaller"],
        "_diag_pen_product": diag["pen_product"],
        "_diag_total_penalty": diag["total_penalty"],
        "_diag_prob_unclamped": pbtts_unclamped,
        "_diag_prob_clamped": round(pbtts, 6),
        "_diag_prob_clamp_delta": round(pbtts - pbtts_unclamped, 6),
        "_diag_market_prob": round(pmbtts, 6),
        "_diag_edge_before_clamp": round(edge_before_clamp, 6),
        "_diag_edge_final": round(edgebtts, 6),
        "_diag_edge_clamp_delta": round(edgebtts - edge_before_clamp, 6),
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
    btts_adj: float = 0.885,
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

    # Audit flag: print full detail for non-EU leagues
    _eu_keys = {
        "premier", "championship", "alemanha", "alemanha2", "espanha", "franca",
        "franca2", "italia", "italia2", "paises_baixos", "belgica", "portugal",
        "turquia",
    }
    verbose = league_key not in _eu_keys

    if verbose:
        from src.data_loader import FIXTURES_COLUMNS as _FC
        print(
            f"[PICK_GEN] league={league_key.upper()} fixtures={len(league_fixt)} "
            f"hist_rows={len(df_hist)} FIXTURES_COLUMNS={sorted(_FC)}"
        )

    for _, fx in league_fixt.iterrows():
        try:
            home = str(fx["HomeTeam"])
            away = str(fx["AwayTeam"])

            # Team-name matching audit
            if verbose:
                h_matches = len(df_hist[df_hist["HomeTeam"] == home])
                a_matches = len(df_hist[df_hist["AwayTeam"] == away])
                h_last_n = len(df_hist[df_hist["HomeTeam"] == home].sort_values("Date").tail(window))
                a_last_n = len(df_hist[df_hist["AwayTeam"] == away].sort_values("Date").tail(window))
                used_fallback = h_last_n < min_games_home or a_last_n < min_games_away
                print(
                    f"[PICK_GEN]   {home} vs {away} | "
                    f"hist_home={h_matches}(last{window}={h_last_n}) "
                    f"hist_away={a_matches}(last{window}={a_last_n}) "
                    f"fallback={used_fallback}"
                )

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

            pbtts_row = generate_btts_pick(base_row, fx, btts_adj=btts_adj)
            if pbtts_row is not None:
                rows_btts.append(pbtts_row)

            if verbose:
                from src.calculations import prob_over25, prob_btts_yes_adjusted, clamp_prob_o25, clamp_prob_btts
                from src.data_loader import get_btts_odd, _to_float
                odd_o25  = _to_float(fx.get("Odd_Over25",  0.0), 0.0)
                odd_btts = get_btts_odd(fx)
                p25_raw  = prob_over25(lam_t)
                p25      = clamp_prob_o25(p25_raw)
                pm25     = (1.0 / odd_o25) if odd_o25 > 1.01 else 0.0
                pbtts    = clamp_prob_btts(prob_btts_yes_adjusted(lam_h, lam_a, adj=btts_adj))
                pmbtts   = (1.0 / odd_btts) if odd_btts > 1.01 else 0.0
                edge_o25  = p25   - pm25
                edge_btts = pbtts - pmbtts
                print(
                    f"[PICK_GEN]     lambdas=({lam_h:.3f},{lam_a:.3f},{lam_t:.3f}) "
                    f"odd_o25={odd_o25:.2f} odd_btts={odd_btts:.2f} | "
                    f"p25={p25:.3f} pm25={pm25:.3f} edge_o25={edge_o25:+.4f} gen_o25={'YES' if p25_row else 'NO'} | "
                    f"pbtts={pbtts:.3f} pmbtts={pmbtts:.3f} edge_btts={edge_btts:+.4f} gen_btts={'YES' if pbtts_row else 'NO'}"
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

    if verbose:
        print(
            f"[PICK_GEN] league={league_key.upper()} done: "
            f"o25_candidates={len(rows25)} btts_candidates={len(rows_btts)}"
        )

    return rows25, rows_btts, total_fixture_errors
