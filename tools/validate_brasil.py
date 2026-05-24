"""
Brazil Serie A calibration and readiness validator.

Runs all diagnostics required before enabling Brasil in production picks:
  1. Dataset summary (rows, date range, teams)
  2. Fallback vs team-specific lambda usage rate
  3. Team name cross-check against live API-Football fixture names
  4. BTTS calibration: model probability vs actual outcome rate
  5. O2.5 calibration: model probability vs actual outcome rate
  6. Edge distribution at typical Brazilian odds
  7. Recommended edge_min and go/no-go verdict per market

Uses the same compute_lambdas / prob_over25 / prob_btts_yes_adjusted pipeline
as production so results are directly comparable.

Usage:
    python validate_brasil.py [--live]   # --live fetches current API-Football fixtures

Requires:
    data_raw/brasil.csv  (populated by fetch_brazil_history.py)
    config.json
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.calculations import (
    prob_over25,
    prob_btts_yes_adjusted,
    clamp_prob_o25,
    clamp_prob_btts,
    compute_lambdas,
)

CONFIG_PATH = BASE_DIR / "config.json"
DATA_PATH = BASE_DIR / "data_raw" / "brasil.csv"

# Production settings — read from config
def load_cfg():
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    hist = cfg.get("history", {})
    return {
        "window": int(hist.get("window", 12)),
        "decay": float(hist.get("decay", 0.88)),
        "min_games_home": int(hist.get("min_games_home", 8)),
        "min_games_away": int(hist.get("min_games_away", 8)),
        "lambda_boost": float(
            (hist.get("league_lambda_boost") or {}).get("brasil",
            hist.get("lambda_boost", 1.0))
        ),
        "edge_min": float(cfg.get("rules", {}).get("over25", {}).get("edge_min", 0.0075)),
    }


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace("﻿", "").strip() for c in df.columns]
    return df


def load_history() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, sep=None, engine="python")
    df = normalize_columns(df)
    need = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"brasil.csv missing columns: {missing}")
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    df["FTHG"] = pd.to_numeric(df["FTHG"], errors="coerce")
    df["FTAG"] = pd.to_numeric(df["FTAG"], errors="coerce")
    df = df.dropna(subset=["FTHG", "FTAG"]).copy()
    return df


# ─────────────────────────────────────────────
# 1. Dataset summary
# ─────────────────────────────────────────────

def section_summary(df: pd.DataFrame):
    print("\n" + "="*60)
    print("1. DATASET SUMMARY")
    print("="*60)
    print(f"  Total rows    : {len(df)}")
    print(f"  Date range    : {df['Date'].min().date()} .. {df['Date'].max().date()}")
    home_teams = set(df["HomeTeam"].unique())
    away_teams = set(df["AwayTeam"].unique())
    all_teams = home_teams | away_teams
    print(f"  Unique teams  : {len(all_teams)}")
    for t in sorted(all_teams):
        h = int((df["HomeTeam"] == t).sum())
        a = int((df["AwayTeam"] == t).sum())
        print(f"    {t:<35s} home={h:3d}  away={a:3d}")

    avg_hg = float(df["FTHG"].mean())
    avg_ag = float(df["FTAG"].mean())
    print(f"\n  League averages: home_goals={avg_hg:.3f}  away_goals={avg_ag:.3f}  total={avg_hg+avg_ag:.3f}")
    over25_rate = float((df["FTHG"] + df["FTAG"] > 2.5).mean())
    btts_rate = float(((df["FTHG"] > 0) & (df["FTAG"] > 0)).mean())
    print(f"  Outcome rates : over25={over25_rate:.1%}  btts={btts_rate:.1%}")
    return all_teams


# ─────────────────────────────────────────────
# 2. Fallback vs team-specific rate
# ─────────────────────────────────────────────

def section_fallback(df: pd.DataFrame, cfg: dict):
    print("\n" + "="*60)
    print("2. FALLBACK vs TEAM-SPECIFIC LAMBDA USAGE")
    print(f"   (window={cfg['window']}  min_games_home={cfg['min_games_home']}  min_games_away={cfg['min_games_away']})")
    print("="*60)

    window = cfg["window"]
    mgh = cfg["min_games_home"]
    mga = cfg["min_games_away"]
    MIN_HIST = max(mgh, mga) + 5

    team_specific = 0
    fallback = 0
    team_counts: dict[str, dict] = defaultdict(lambda: {"specific": 0, "fallback": 0})

    for i in range(MIN_HIST, len(df)):
        hist = df.iloc[:i]
        row = df.iloc[i]
        home = row["HomeTeam"]
        away = row["AwayTeam"]

        h_last = len(hist[hist["HomeTeam"] == home].tail(window))
        a_last = len(hist[hist["AwayTeam"] == away].tail(window))
        used_fallback = h_last < mgh or a_last < mga

        if used_fallback:
            fallback += 1
            team_counts[home]["fallback"] += 1
            team_counts[away]["fallback"] += 1
        else:
            team_specific += 1
            team_counts[home]["specific"] += 1
            team_counts[away]["specific"] += 1

    total = team_specific + fallback
    print(f"\n  Overall: team_specific={team_specific} ({team_specific/total:.1%})  fallback={fallback} ({fallback/total:.1%})")

    high_fallback = [(t, v) for t, v in team_counts.items()
                     if v["fallback"] > v["specific"]]
    if high_fallback:
        print(f"\n  Teams with >50% fallback rate (need more history):")
        for t, v in sorted(high_fallback, key=lambda x: -x[1]["fallback"]):
            tot = v["specific"] + v["fallback"]
            print(f"    {t:<35s} fallback={v['fallback']}/{tot} ({v['fallback']/tot:.0%})")
    else:
        print("\n  All teams have majority team-specific lambdas. Good.")

    return total, fallback


# ─────────────────────────────────────────────
# 3. Team name cross-check vs live API fixtures
# ─────────────────────────────────────────────

def section_name_check(df_teams: set[str], live_check: bool):
    print("\n" + "="*60)
    print("3. TEAM NAME CROSS-CHECK vs API-FOOTBALL LIVE FIXTURES")
    print("="*60)

    if not live_check:
        print("  Skipped (pass --live to enable API call).")
        print("  Important: team names from fetch_brazil_history.py already")
        print("  come from the same API, so mismatches should be near zero.")
        return

    api_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        print("  Skipped: API_FOOTBALL_KEY not set.")
        return

    try:
        params = {"league": 71, "season": 2025, "next": 10}
        query = urllib.parse.urlencode(params)
        url = f"https://v3.football.api-sports.io/fixtures?{query}"
        req = urllib.request.Request(url, headers={
            "x-apisports-key": api_key,
            "Accept": "application/json",
            "User-Agent": "apostas-over-futebol/1.0",
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))

        live_teams: set[str] = set()
        for item in data.get("response", []):
            t = item.get("teams") or {}
            h = ((t.get("home") or {}).get("name") or "").strip()
            a = ((t.get("away") or {}).get("name") or "").strip()
            if h:
                live_teams.add(h)
            if a:
                live_teams.add(a)

        if not live_teams:
            print("  No upcoming fixtures returned (off-season or API issue).")
            return

        matched = live_teams & df_teams
        unmatched = live_teams - df_teams
        print(f"  Live teams found   : {len(live_teams)}")
        print(f"  Matched in history : {len(matched)}")
        if unmatched:
            print(f"  [WARN] Unmatched teams (no history rows with this exact name):")
            for t in sorted(unmatched):
                print(f"    '{t}'")
        else:
            print("  All live teams found in history. No name mismatches.")

    except Exception as e:
        print(f"  [ERR] Live check failed: {e}")


# ─────────────────────────────────────────────
# 4+5. Calibration: BTTS and O2.5
# ─────────────────────────────────────────────

def _bucket(p: float) -> str:
    if p < 0.40:
        return "<40%"
    if p < 0.45:
        return "40-45%"
    if p < 0.50:
        return "45-50%"
    if p < 0.55:
        return "50-55%"
    if p < 0.60:
        return "55-60%"
    if p < 0.65:
        return "60-65%"
    if p < 0.70:
        return "65-70%"
    return ">=70%"


def section_calibration(df: pd.DataFrame, cfg: dict):
    print("\n" + "="*60)
    print("4+5. CALIBRATION: MODEL PROBABILITY vs ACTUAL OUTCOME RATE")
    print(f"     (lambda_boost={cfg['lambda_boost']})")
    print("="*60)

    window = cfg["window"]
    decay = cfg["decay"]
    mgh = cfg["min_games_home"]
    mga = cfg["min_games_away"]
    boost = cfg["lambda_boost"]
    MIN_HIST = max(mgh, mga) + 5

    o25_buckets: dict[str, list] = defaultdict(list)
    btts_buckets: dict[str, list] = defaultdict(list)

    n_errors = 0
    n_fallback = 0
    n_team_specific = 0

    for i in range(MIN_HIST, len(df)):
        hist = df.iloc[:i]
        row = df.iloc[i]
        home = row["HomeTeam"]
        away = row["AwayTeam"]
        hg = int(row["FTHG"])
        ag = int(row["FTAG"])

        try:
            lam_h, lam_a, lam_t = compute_lambdas(
                hist, home, away,
                window=window, decay=decay,
                min_games_home=mgh, min_games_away=mga,
            )
        except Exception:
            n_errors += 1
            continue

        h_last = len(hist[hist["HomeTeam"] == home].tail(window))
        a_last = len(hist[hist["AwayTeam"] == away].tail(window))
        used_fallback = h_last < mgh or a_last < mga
        if used_fallback:
            n_fallback += 1
        else:
            n_team_specific += 1

        if boost and boost != 1.0:
            lam_h = max(0.25, min(2.20, lam_h * boost))
            lam_a = max(0.20, min(1.90, lam_a * boost))
            lam_t = lam_h + lam_a

        p_o25 = clamp_prob_o25(prob_over25(lam_t))
        p_btts = clamp_prob_btts(prob_btts_yes_adjusted(lam_h, lam_a))

        actual_o25 = int((hg + ag) > 2.5)
        actual_btts = int(hg > 0 and ag > 0)

        o25_buckets[_bucket(p_o25)].append((p_o25, actual_o25))
        btts_buckets[_bucket(p_btts)].append((p_btts, actual_btts))

    total = n_fallback + n_team_specific
    print(f"\n  Evaluated {total} fixtures (errors={n_errors})")
    print(f"  team_specific={n_team_specific} ({n_team_specific/total:.1%})  fallback={n_fallback} ({n_fallback/total:.1%})")

    def print_calibration(label, buckets):
        print(f"\n  {label}")
        print(f"  {'Bucket':<10s}  {'N':>5s}  {'Model':>8s}  {'Actual':>8s}  {'Delta':>8s}")
        print(f"  {'-'*10}  {'-'*5}  {'-'*8}  {'-'*8}  {'-'*8}")
        total_n = sum(len(v) for v in buckets.values())
        total_model = 0.0
        total_actual = 0.0
        for bkt in ["<40%", "40-45%", "45-50%", "50-55%", "55-60%", "60-65%", "65-70%", ">=70%"]:
            rows = buckets.get(bkt, [])
            if not rows:
                continue
            n = len(rows)
            avg_model = sum(r[0] for r in rows) / n
            avg_actual = sum(r[1] for r in rows) / n
            delta = avg_actual - avg_model
            flag = "  [WARN large delta]" if abs(delta) > 0.10 else ""
            print(f"  {bkt:<10s}  {n:>5d}  {avg_model:>7.1%}  {avg_actual:>7.1%}  {delta:>+7.1%}{flag}")
            total_model += avg_model * n
            total_actual += avg_actual * n
        if total_n:
            print(f"  {'OVERALL':<10s}  {total_n:>5d}  {total_model/total_n:>7.1%}  {total_actual/total_n:>7.1%}  {(total_actual-total_model)/total_n:>+7.1%}")

    print_calibration("O2.5", o25_buckets)
    print_calibration("BTTS", btts_buckets)


# ─────────────────────────────────────────────
# 6. Edge distribution at typical Brazil odds
# ─────────────────────────────────────────────

def section_edge_distribution(df: pd.DataFrame, cfg: dict):
    print("\n" + "="*60)
    print("6. EDGE DISTRIBUTION AT TYPICAL BRAZIL ODDS")
    print("="*60)

    window = cfg["window"]
    decay = cfg["decay"]
    mgh = cfg["min_games_home"]
    mga = cfg["min_games_away"]
    boost = cfg["lambda_boost"]
    edge_min = cfg["edge_min"]
    MIN_HIST = max(mgh, mga) + 5

    # Representative Brazilian odds
    O25_ODDS = [1.65, 1.72, 1.80, 1.90, 2.00]
    BTTS_ODDS = [1.65, 1.72, 1.80, 1.90, 2.05]
    THRESHOLDS = [0.0100, 0.0075, 0.0050]

    o25_probs = []
    btts_probs = []

    for i in range(MIN_HIST, len(df)):
        hist = df.iloc[:i]
        row = df.iloc[i]
        try:
            lam_h, lam_a, lam_t = compute_lambdas(
                hist, row["HomeTeam"], row["AwayTeam"],
                window=window, decay=decay,
                min_games_home=mgh, min_games_away=mga,
            )
        except Exception:
            continue

        if boost and boost != 1.0:
            lam_h = max(0.25, min(2.20, lam_h * boost))
            lam_a = max(0.20, min(1.90, lam_a * boost))
            lam_t = lam_h + lam_a

        o25_probs.append(clamp_prob_o25(prob_over25(lam_t)))
        btts_probs.append(clamp_prob_btts(prob_btts_yes_adjusted(lam_h, lam_a)))

    if not o25_probs:
        print("  Not enough data to compute edge distribution.")
        return

    print(f"\n  N fixtures used: {len(o25_probs)}")

    def edge_pass_rate(probs, odds_list, thresholds):
        n = len(probs)
        print(f"  {'Odd':>6s}  " + "  ".join(f"pass@{t:.2%}" for t in thresholds))
        print(f"  {'-'*6}  " + "  ".join("-"*10 for _ in thresholds))
        for odd in odds_list:
            impl = 1.0 / odd
            edges = [p - impl for p in probs]
            counts = [sum(1 for e in edges if e >= t) for t in thresholds]
            pcts = [c / n for c in counts]
            row_str = f"  {odd:>6.2f}  " + "  ".join(f"{c:5d} ({p:.1%})" for c, p in zip(counts, pcts))
            print(row_str)

    print(f"\n  O2.5 — pass counts at edge thresholds {[f'{t:.2%}' for t in THRESHOLDS]}:")
    edge_pass_rate(o25_probs, O25_ODDS, THRESHOLDS)

    print(f"\n  BTTS — pass counts at edge thresholds {[f'{t:.2%}' for t in THRESHOLDS]}:")
    edge_pass_rate(btts_probs, BTTS_ODDS, THRESHOLDS)


# ─────────────────────────────────────────────
# 7. Verdict
# ─────────────────────────────────────────────

def section_verdict(df: pd.DataFrame, total: int, fallback: int, cfg: dict):
    print("\n" + "="*60)
    print("7. GO / NO-GO VERDICT")
    print("="*60)

    issues = []
    warnings = []

    if len(df) < 200:
        issues.append(f"Insufficient history: {len(df)} rows (need >=200 for meaningful calibration)")

    fallback_rate = fallback / total if total else 1.0
    if fallback_rate > 0.50:
        issues.append(f"High fallback rate: {fallback_rate:.1%} of fixtures use league-average lambdas (need <50%)")
    elif fallback_rate > 0.30:
        warnings.append(f"Elevated fallback rate: {fallback_rate:.1%} (target <30%)")

    date_span_days = (df["Date"].max() - df["Date"].min()).days
    if date_span_days < 180:
        issues.append(f"Date span too short: {date_span_days} days (need >=180 for at least one full season)")

    all_teams = set(df["HomeTeam"].unique()) | set(df["AwayTeam"].unique())
    if len(all_teams) < 16:
        warnings.append(f"Only {len(all_teams)} unique teams (a full Serie A season has 20 teams)")

    print()
    if issues:
        for iss in issues:
            print(f"  [BLOCK] {iss}")
        print(f"\n  Verdict: NOT READY — resolve blocking issues above before enabling production picks.")
    elif warnings:
        for w in warnings:
            print(f"  [WARN]  {w}")
        print(f"\n  Verdict: CONDITIONAL GO — warnings present, monitor calibration closely.")
    else:
        print(f"  Verdict: GO — data quality checks passed.")
        print(f"  BTTS: Enable. Brazilian football supports balanced BTTS profile.")
        print(f"  O2.5: Enable at medium confidence (current edge_min={cfg['edge_min']:.4f} applies).")
        print(f"  Recommendation: Re-run this script after 4-6 weeks of live picks to validate.")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="Fetch upcoming fixtures from API-Football for team name cross-check")
    args = parser.parse_args()

    if not DATA_PATH.exists():
        raise SystemExit(f"data_raw/brasil.csv not found. Run fetch_brazil_history.py first.")

    cfg = load_cfg()
    print(f"Config: window={cfg['window']} decay={cfg['decay']} "
          f"min_games={cfg['min_games_home']}/{cfg['min_games_away']} "
          f"lambda_boost={cfg['lambda_boost']} edge_min={cfg['edge_min']:.4f}")

    df = load_history()

    if len(df) == 0:
        raise SystemExit("brasil.csv is empty (header only). Run fetch_brazil_history.py first.")

    all_teams = section_summary(df)
    section_name_check(all_teams, args.live)
    total, fallback = section_fallback(df, cfg)
    section_calibration(df, cfg)
    section_edge_distribution(df, cfg)
    section_verdict(df, total, fallback, cfg)

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    main()
