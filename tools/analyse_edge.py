"""
Edge distribution analysis — per-league calibration and threshold sensitivity.

Loads data_raw/*.csv for target leagues, simulates the full lambda pipeline
for every historical fixture, then reports:
  1. Model-probability distribution
  2. Lambda-fallback rate (proxy for team-name mismatch)
  3. O2.5 calibration: model prob vs actual over-2.5 rate (by decile)
  4. Edge distribution at typical odds scenarios
  5. Pass-rate sensitivity at edge_min = 1.0 / 0.75 / 0.50 %
  6. Historical simulated ROI at each threshold
  7. Recommended per-league adaptive edge_min
"""

import sys
import math
from pathlib import Path
from collections import defaultdict

import pandas as pd

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from src.calculations import (
    compute_lambdas,
    prob_over25,
    prob_btts_yes_adjusted,
    clamp_prob_o25,
    clamp_prob_btts,
)
from src.data_loader import normalize_columns

# ── Configuration (mirrors config.json) ────────────────────────────────────
WINDOW         = 12
DECAY          = 0.88
MIN_GAMES_HOME = 8
MIN_GAMES_AWAY = 8
LAMBDA_BOOST   = 1.12

# Minimum history rows before we start trusting a fixture's lambda
MIN_HIST_WARMUP = 20

LEAGUES = {
    # non-EU (focus)
    "mls":     "MLS",
    "noruega": "Eliteserien",
    "suecia":  "Allsvenskan",
    "japao":   "J1 League",
    "coreia":  "K League 1",
    # EU (reference)
    "premier": "Premier League",
    "italia":  "Serie A",
}

# Typical O2.5 odds range per league (used for edge simulation when we have no
# historical odds).  Derived from observed fixtures_today.csv + known ranges.
TYPICAL_ODDS = {
    "mls":     [1.65, 1.70, 1.75, 1.80, 1.90],
    "noruega": [1.65, 1.72, 1.78, 1.85],
    "suecia":  [1.65, 1.72, 1.78, 1.85],
    "japao":   [1.68, 1.75, 1.82, 1.90],
    "coreia":  [1.68, 1.75, 1.82, 1.90],
    "premier": [1.45, 1.52, 1.60, 1.70],
    "italia":  [1.76, 1.85, 1.92, 2.00],
}

EDGE_THRESHOLDS = [0.010, 0.0075, 0.005]
ODDS_DYNAMIC_BUMPS = [(2.05, 0.025), (1.90, 0.015), (1.75, 0.010)]


def dynamic_edge_min(edge_min_base: float, odd: float) -> float:
    req = edge_min_base
    for threshold, bump in ODDS_DYNAMIC_BUMPS:
        if odd >= threshold:
            req += bump
            break
    return req


def load_history(league_key: str) -> pd.DataFrame | None:
    path = BASE / "data_raw" / f"{league_key}.csv"
    if not path.exists():
        print(f"  [WARN] data_raw/{league_key}.csv não existe")
        return None
    df = pd.read_csv(path, sep=None, engine="python")
    df = normalize_columns(df)
    need = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not need.issubset(set(df.columns)):
        print(f"  [WARN] {league_key}: colunas ausentes — {sorted(df.columns)}")
        return None
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Date", "FTHG", "FTAG"]).copy()
    df["FTHG"] = pd.to_numeric(df["FTHG"], errors="coerce").fillna(0)
    df["FTAG"] = pd.to_numeric(df["FTAG"], errors="coerce").fillna(0)
    df = df.sort_values("Date").reset_index(drop=True)
    return df


def simulate_league(df: pd.DataFrame, league_key: str) -> pd.DataFrame:
    """
    For each fixture (after MIN_HIST_WARMUP rows), compute lambdas using only
    rows strictly before that fixture (no look-ahead), then compute model probs
    and whether the actual outcome was over 2.5.
    """
    records = []
    for i in range(MIN_HIST_WARMUP, len(df)):
        row = df.iloc[i]
        history = df.iloc[:i].copy()

        home = str(row["HomeTeam"])
        away = str(row["AwayTeam"])

        # Check fallback BEFORE compute_lambdas (mirrors production logic)
        h_last = history[history["HomeTeam"] == home].tail(WINDOW)
        a_last = history[history["AwayTeam"] == away].tail(WINDOW)
        used_fallback = (len(h_last) < MIN_GAMES_HOME) or (len(a_last) < MIN_GAMES_AWAY)

        lam_h, lam_a, lam_t = compute_lambdas(
            history, home, away,
            window=WINDOW, decay=DECAY,
            min_games_home=MIN_GAMES_HOME,
            min_games_away=MIN_GAMES_AWAY,
        )

        # Apply lambda boost (mirrors config.json lambda_boost)
        lam_h = max(0.25, min(2.20, lam_h * LAMBDA_BOOST))
        lam_a = max(0.20, min(1.90, lam_a * LAMBDA_BOOST))
        lam_t = lam_h + lam_a

        p_o25  = clamp_prob_o25(prob_over25(lam_t))
        p_btts = clamp_prob_btts(prob_btts_yes_adjusted(lam_h, lam_a))

        actual_goals = int(row["FTHG"]) + int(row["FTAG"])
        is_over25    = actual_goals >= 3
        is_btts      = int(row["FTHG"]) >= 1 and int(row["FTAG"]) >= 1

        records.append({
            "Date":         row["Date"],
            "HomeTeam":     home,
            "AwayTeam":     away,
            "LambdaHome":   lam_h,
            "LambdaAway":   lam_a,
            "LambdaTotal":  lam_t,
            "ProbO25":      p_o25,
            "ProbBTTS":     p_btts,
            "UsedFallback": used_fallback,
            "ActualGoals":  actual_goals,
            "IsOver25":     is_over25,
            "IsBTTS":       is_btts,
        })

    return pd.DataFrame(records)


def section(title: str):
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def subsection(title: str):
    print(f"\n--- {title} ---")


def print_calibration(df: pd.DataFrame, prob_col: str, outcome_col: str, label: str):
    """Print model probability vs actual outcome rate, grouped into decile buckets."""
    bins   = [0.22, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.72]
    labels = ["<35", "35-40", "40-45", "45-50", "50-55", "55-60", "60-65", "65+"]

    df = df.copy()
    df["_bucket"] = pd.cut(df[prob_col], bins=bins, labels=labels, right=True)
    grp = df.groupby("_bucket", observed=True).agg(
        n=("_bucket", "count"),
        model_prob=(prob_col, "mean"),
        actual_rate=(outcome_col, "mean"),
    )
    grp["delta"] = grp["actual_rate"] - grp["model_prob"]

    print(f"  {'Bucket':<10} {'N':>5}  {'ModelProb':>9}  {'ActualRate':>10}  {'Delta':>7}")
    print(f"  {'-'*10} {'-'*5}  {'-'*9}  {'-'*10}  {'-'*7}")
    for bucket, r in grp.iterrows():
        if r["n"] > 0:
            flag = "  <<< under" if r["delta"] < -0.04 else ("  >>> over" if r["delta"] > 0.04 else "")
            print(
                f"  {str(bucket):<10} {int(r['n']):>5}  {r['model_prob']:>9.3f}  "
                f"{r['actual_rate']:>10.3f}  {r['delta']:>+7.3f}{flag}"
            )


def edge_pass_analysis(df: pd.DataFrame, league_key: str):
    """
    For a range of typical odds, compute how many historical fixtures would
    pass at each edge_min threshold (0.50%, 0.75%, 1.00%) under both static
    and dynamic edge_min logic.
    """
    odds_list = TYPICAL_ODDS.get(league_key, [1.70, 1.78, 1.85])
    total = len(df)
    if total == 0:
        return

    print(f"\n  {'Odds':>6}  {'ModelProb(med)':>14}  ", end="")
    for t in EDGE_THRESHOLDS:
        label = f"pass@{t*100:.2f}%"
        print(f"{'  '+label:>13}", end="")
    print(f"  {'SimROI@1%':>9}")
    print(f"  {'-'*6}  {'-'*14}  " + "  " + "  ".join(["-"*11]*len(EDGE_THRESHOLDS)) + "  " + "-"*9)

    for odd in odds_list:
        implied = 1.0 / odd
        edges = df["ProbO25"] - implied

        # lam_t_min gate (quality filter) — 1.90 for O2.5, odd_min 1.55
        quality_pass = (df["LambdaTotal"] >= 1.90) & (odd >= 1.55) & (edges >= 0.0)
        n_quality = quality_pass.sum()

        rows_list = []
        for t in EDGE_THRESHOLDS:
            dyn_min = dynamic_edge_min(t, odd)
            passed = quality_pass & (edges >= dyn_min) & (edges <= 0.15)
            rows_list.append(passed.sum())

        # Simulated ROI at 1% threshold (static)
        dyn_1pct = dynamic_edge_min(0.01, odd)
        bet_mask = quality_pass & (edges >= dyn_1pct) & (edges <= 0.15)
        if bet_mask.sum() > 0:
            wins = df[bet_mask]["IsOver25"].sum()
            n_bets = bet_mask.sum()
            roi = (wins * odd - n_bets) / n_bets
            roi_str = f"{roi:>+.2%}"
        else:
            roi_str = "    n/a"

        med_prob = df["ProbO25"].median()
        print(
            f"  {odd:>6.2f}  {med_prob:>14.4f}  "
            + "  ".join(f"  {v:>4}/{total}" for v in rows_list)
            + f"  {roi_str:>9}"
        )


def simulate_roi_by_threshold(df: pd.DataFrame, typical_odd: float) -> dict:
    """
    Full historical ROI simulation at each edge_min threshold.
    Returns dict: threshold -> {n_bets, wins, roi, win_rate}
    """
    implied = 1.0 / typical_odd
    edges = df["ProbO25"] - implied
    quality = (df["LambdaTotal"] >= 1.90) & (typical_odd >= 1.55) & (edges >= 0.0)

    results = {}
    for t in EDGE_THRESHOLDS:
        dyn_min = dynamic_edge_min(t, typical_odd)
        mask = quality & (edges >= dyn_min) & (edges <= 0.15)
        n = mask.sum()
        if n == 0:
            results[t] = {"n": 0, "wins": 0, "roi": 0.0, "win_rate": 0.0}
            continue
        wins = df[mask]["IsOver25"].sum()
        roi = (wins * typical_odd - n) / n
        results[t] = {"n": int(n), "wins": int(wins), "roi": roi, "win_rate": wins / n}
    return results


def main():
    all_results: dict[str, pd.DataFrame] = {}

    print("Running historical simulation for each league...")
    for lk, lname in LEAGUES.items():
        print(f"  Loading {lk} ({lname})...")
        df_hist = load_history(lk)
        if df_hist is None:
            continue
        df_sim = simulate_league(df_hist, lk)
        all_results[lk] = df_sim
        print(f"    => {len(df_hist)} total rows, {len(df_sim)} simulated fixtures")

    # ── 1. Overview ──────────────────────────────────────────────────────────
    section("1. OVERVIEW — FIXTURES & FALLBACK RATE")
    print(f"\n  {'League':<12} {'LgName':<16} {'N':>6}  {'Fallback%':>10}  "
          f"{'MedProb O25':>11}  {'ActualO25%':>10}  {'MedProb BTTS':>12}  {'ActualBTTS%':>11}")
    print(f"  {'-'*12} {'-'*16} {'-'*6}  {'-'*10}  {'-'*11}  {'-'*10}  {'-'*12}  {'-'*11}")

    for lk, lname in LEAGUES.items():
        if lk not in all_results:
            continue
        df = all_results[lk]
        fb_rate = df["UsedFallback"].mean()
        med_o25 = df["ProbO25"].median()
        actual_o25 = df["IsOver25"].mean()
        med_btts = df["ProbBTTS"].median()
        actual_btts = df["IsBTTS"].mean()
        print(
            f"  {lk:<12} {lname:<16} {len(df):>6}  {fb_rate:>10.1%}  "
            f"{med_o25:>11.4f}  {actual_o25:>10.1%}  {med_btts:>12.4f}  {actual_btts:>11.1%}"
        )

    # ── 2. O2.5 Calibration per league ──────────────────────────────────────
    section("2. O2.5 CALIBRATION — MODEL PROB vs ACTUAL OVER-2.5 RATE")
    print("  (Delta > +0.04: model over-estimates. Delta < -0.04: model under-estimates)")
    for lk, lname in LEAGUES.items():
        if lk not in all_results:
            continue
        df = all_results[lk]
        subsection(f"{lk.upper()} — {lname} (n={len(df)})")
        print_calibration(df, "ProbO25", "IsOver25", lk)

    # ── 3. Calibration split: fallback vs team-specific ─────────────────────
    section("3. CALIBRATION SPLIT — FALLBACK vs TEAM-SPECIFIC LAMBDAS (O2.5)")
    for lk in ["mls", "noruega", "suecia", "japao", "coreia"]:
        if lk not in all_results:
            continue
        df = all_results[lk]
        df_fb  = df[df["UsedFallback"]]
        df_ts  = df[~df["UsedFallback"]]
        lname  = LEAGUES[lk]
        subsection(f"{lk.upper()} — {lname}")
        if len(df_fb) > 0:
            print(f"  [FALLBACK  n={len(df_fb):>4}] actual O2.5 = {df_fb['IsOver25'].mean():.3f}  "
                  f"model median = {df_fb['ProbO25'].median():.3f}  "
                  f"spread = [{df_fb['ProbO25'].min():.3f}, {df_fb['ProbO25'].max():.3f}]")
        if len(df_ts) > 0:
            print(f"  [TEAM-SPEC n={len(df_ts):>4}] actual O2.5 = {df_ts['IsOver25'].mean():.3f}  "
                  f"model median = {df_ts['ProbO25'].median():.3f}  "
                  f"spread = [{df_ts['ProbO25'].min():.3f}, {df_ts['ProbO25'].max():.3f}]")
        else:
            print("  [TEAM-SPEC] 0 fixtures — all fallback (team names never reach min_games threshold)")

    # ── 4. Edge distribution at typical odds ────────────────────────────────
    section("4. EDGE DISTRIBUTION AT TYPICAL ODDS — PASS RATES & SIMULATED ROI")
    print("  Columns: pass@T = fixtures (out of total) that pass quality + dynamic edge_min T%")
    print("  SimROI@1% = simulated return on investment if we bet all fixtures passing 1% threshold")
    print()
    for lk, lname in LEAGUES.items():
        if lk not in all_results:
            continue
        df = all_results[lk]
        subsection(f"{lk.upper()} — {lname} (n={len(df)})")
        edge_pass_analysis(df, lk)

    # ── 5. Detailed threshold sensitivity at median typical odds ─────────────
    section("5. THRESHOLD SENSITIVITY — SIMULATED ROI BY LEAGUE")
    print("  Using the median typical odds for each league.")
    print(f"\n  {'League':<12} {'TypOdd':>7}  {'Thresh':>7}  {'N_bets':>7}  {'WinRate':>9}  {'ROI':>9}")
    print(f"  {'-'*12} {'-'*7}  {'-'*7}  {'-'*7}  {'-'*9}  {'-'*9}")

    for lk, lname in LEAGUES.items():
        if lk not in all_results:
            continue
        df = all_results[lk]
        odds_list = TYPICAL_ODDS.get(lk, [1.75])
        # Use the middle odds as representative
        typical = sorted(odds_list)[len(odds_list) // 2]
        roi_data = simulate_roi_by_threshold(df, typical)
        for t, r in sorted(roi_data.items()):
            t_str = f"{t*100:.2f}%"
            if r["n"] > 0:
                print(
                    f"  {lk:<12} {typical:>7.2f}  {t_str:>7}  {r['n']:>7}  "
                    f"{r['win_rate']:>9.2%}  {r['roi']:>+9.2%}"
                )
            else:
                print(f"  {lk:<12} {typical:>7.2f}  {t_str:>7}  {'0':>7}  {'n/a':>9}  {'n/a':>9}")

    # ── 6. Edge histogram (text-based) ───────────────────────────────────────
    section("6. EDGE HISTOGRAM AT REPRESENTATIVE ODDS (text)")
    print("  Each bar = fraction of historical fixtures in that edge bin")
    print("  Threshold marks: | = 0.50%   || = 0.75%   ||| = 1.00%")

    BINS = [-0.20, -0.10, -0.05, -0.02, 0.0, 0.005, 0.0075, 0.01, 0.02, 0.04, 0.08, 0.16]
    BIN_LABELS = ["<-10%", "-10–5%", "-5–2%", "-2–0%", "0–0.5%", "0.5–0.75%", "0.75–1%", "1–2%", "2–4%", "4–8%", "8–16%"]

    for lk, lname in LEAGUES.items():
        if lk not in all_results:
            continue
        df = all_results[lk]
        odds_list = TYPICAL_ODDS.get(lk, [1.75])
        typical = sorted(odds_list)[len(odds_list) // 2]
        implied = 1.0 / typical
        edges = df["ProbO25"] - implied

        subsection(f"{lk.upper()} at odds={typical:.2f}  (n={len(df)}, implied={implied:.3f})")
        total = len(edges)
        for j, label in enumerate(BIN_LABELS):
            lo, hi = BINS[j], BINS[j + 1]
            count = ((edges >= lo) & (edges < hi)).sum()
            frac = count / total if total > 0 else 0
            bar = "#" * int(frac * 50)
            thresh_mark = " |||" if hi <= 0.01 and hi > 0.0075 else (" ||" if hi <= 0.0075 and hi > 0.005 else (" |" if hi <= 0.005 and hi > 0.0 else ""))
            print(f"  {label:<12}  {count:>4}  {frac:>6.1%}  {bar}{thresh_mark}")

    # ── 7. Recommendation ────────────────────────────────────────────────────
    section("7. RECOMMENDATIONS — ADAPTIVE PER-LEAGUE EDGE_MIN")
    print("""
  METHODOLOGY:
    edge_min is set low enough to capture positive-ROI bets, while high enough
    to avoid noise from low-lambda (fallback) fixtures.

    Key signals from this analysis:
      a) If fallback_rate is HIGH (>60%), team-specific lambdas rarely fire
         => model probability is near-constant per league => edge is noise.
         Need higher threshold OR require team-specific history.
      b) If calibration shows model OVER-estimates (delta < 0), lower threshold
         is dangerous because even "positive edge" bets are losing bets.
      c) If calibration is neutral/under-estimates, lower threshold is safe.
      d) ROI at 0.75% threshold vs 1.0% threshold tells us if the extra bets
         in the 0.75-1.0% band are profitable or not.
    """)

    for lk, lname in LEAGUES.items():
        if lk not in all_results:
            continue
        df = all_results[lk]
        fb_rate = df["UsedFallback"].mean()

        odds_list = TYPICAL_ODDS.get(lk, [1.75])
        typical = sorted(odds_list)[len(odds_list) // 2]
        roi_data = simulate_roi_by_threshold(df, typical)

        roi_1pct  = roi_data[0.010]["roi"] if roi_data[0.010]["n"] > 0 else None
        roi_075pct = roi_data[0.0075]["roi"] if roi_data[0.0075]["n"] > 0 else None
        roi_05pct = roi_data[0.005]["roi"] if roi_data[0.005]["n"] > 0 else None

        # Calibration: average delta across buckets
        buckets = [0.50, 0.55, 0.60, 0.65]  # most relevant prob levels
        calib_bets = df[df["ProbO25"] >= 0.50]
        if len(calib_bets) > 0:
            avg_delta = calib_bets["IsOver25"].mean() - calib_bets["ProbO25"].mean()
        else:
            avg_delta = 0.0

        # Decision logic
        if fb_rate > 0.70:
            recommended = "0.75% (lower bound)"
            reason = f"fallback_rate={fb_rate:.0%} (high) — team-specific history sparse"
        elif avg_delta < -0.04:
            recommended = "1.00% (keep current)"
            reason = f"model OVER-estimates by {avg_delta:.1%} in relevant prob range"
        elif roi_075pct is not None and roi_075pct > 0 and (roi_1pct is None or roi_075pct >= roi_1pct - 0.02):
            recommended = "0.50%"
            reason = f"ROI@0.75%={roi_075pct:.2%} suggests extra bets are profitable"
        elif roi_075pct is not None and roi_075pct >= -0.03:
            recommended = "0.75%"
            reason = f"ROI@0.75%={roi_075pct:.2%} marginally positive; safe to try"
        else:
            recommended = "1.00% (keep current)"
            reason = "insufficient evidence to lower threshold safely"

        print(f"  [{lk.upper():<8}] recommended edge_min = {recommended}")
        print(f"             reason: {reason}")
        if roi_1pct is not None:
            print(f"             ROI @1.00% = {roi_1pct:+.2%} ({roi_data[0.010]['n']} bets)")
        if roi_075pct is not None:
            print(f"             ROI @0.75% = {roi_075pct:+.2%} ({roi_data[0.0075]['n']} bets)")
        if roi_05pct is not None:
            print(f"             ROI @0.50% = {roi_05pct:+.2%} ({roi_data[0.005]['n']} bets)")
        print()

    section("DONE")
    print("  To apply per-league thresholds, add 'league_edge_min' to config.json rules")
    print("  and update apply_market_rules() to read it per-league.")


if __name__ == "__main__":
    main()
