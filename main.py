# força deploy
print("### TESTE NOVO CODIGO ###")

import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pandas as pd
from src.history import HISTORY_COLUMNS, HISTORY_PATH
from src.league_stats import update_league_stats
from src.state import (
    load_sent_state,
    save_sent_state,
    pick_id,
)
from src.config import (
    DEFAULT_CAP_FRAC,
    DEFAULT_DAILY_CAP_FRAC,
    DEFAULT_KELLY_FRACTION,
    DEFAULT_MAX_ODD_BTTS,
    DEFAULT_MAX_ODD_O25,
    DEFAULT_MAX_PICKS_GLOBAL,
    DEFAULT_MAX_PICKS_PER_DAY,
    load_config,
)
from src.data_loader import (
    load_fixtures,
    normalize_columns,
)
from src.pick_generation import (
    process_league_fixtures,
)
from src.runtime import (
    build_bankroll_settings,
    build_history_settings,
    build_runtime_settings,
)
from src.pipeline import (
    persist_history,
    process_notifications,
    save_all_outputs,
    upload_outputs,
)
from src.integrations import (
    send_telegram_message,
    _send_in_chunks,
    df_to_rows,
    build_message,
    github_request,
    github_get_sha,
    github_put_file,
    upload_csvs_to_github,
)
from src.market_rules import (
    add_rank_fields,
    dedupe_correlated_picks,
    limit_picks_per_day,
    apply_market_rules,
    apply_stakes,
)
# força deploy
print("### TESTE NOVO CODIGO ###")
BASE = Path(__file__).resolve().parent
SENT_STATE_PATH = BASE / "sent_state.json"


# =============================
# Anti-duplicados (por dia)
# =============================


# =============================
# Telegram
# =============================



# =============================
# Main
# =============================
def main():
    print("### TESTE NOVO CODIGO ###")
    cfg = load_config(BASE)

    runtime_settings = build_runtime_settings(cfg)
    run_mode = runtime_settings["run_mode"]
    max_picks_per_day = runtime_settings["max_picks_per_day"]
    max_picks_global = runtime_settings["max_picks_global"]
    days_ahead = runtime_settings["days_ahead"]
    print(f"[DBG] gerar_picks mode={run_mode}")
    print(f"[DBG] max_picks_per_day={max_picks_per_day} | max_picks_global={max_picks_global}")

    GITHUB_RAW_URL = "https://raw.githubusercontent.com/jorgepita/apostas-over-futebol/main/fixtures_today.csv"

    fixtures = load_fixtures(GITHUB_RAW_URL)

    fixtures["Date"] = pd.to_datetime(fixtures["Date"], errors="coerce")
    
    print(f"[DBG] total fixtures: {len(fixtures)}")
    all_leagues = fixtures["League"].unique() if not fixtures.empty else []
    
    fixtures["Date"] = pd.to_datetime(fixtures["Date"], errors="coerce").dt.date
    fixtures = fixtures.dropna(subset=["Date"]).copy()

    try:
        from zoneinfo import ZoneInfo
        now_pt = datetime.now(ZoneInfo("Europe/Lisbon"))
    except Exception:
        # datetime.utcnow() is deprecated, use now(timezone.utc)
        now_pt = datetime.now(timezone.utc)

    start = now_pt.date()
    end = start + timedelta(days=days_ahead - 1)
    today_iso = start.isoformat()

    fixtures_filtered = fixtures[(fixtures["Date"] >= start) & (fixtures["Date"] <= end)].copy()
    
    leagues_after_date = fixtures_filtered["League"].unique() if not fixtures_filtered.empty else []
    for l_key in all_leagues:
        if l_key not in leagues_after_date:
            print(f"[FIXTURE FILTERED] league={l_key.upper()} reason=date_filter")

    fixtures = fixtures_filtered
   
    print("==== DEBUG DATES ====")
    print(fixtures["Date"].value_counts().sort_index())
    
    fixtures["Date"] = fixtures["Date"].astype(str)

    print(f"[DBG] fixtures no range {start} -> {end}: {len(fixtures)}")

    rows25 = []
    rows_btts = []

    history_settings = build_history_settings(cfg)
    history_cfg = history_settings["history_cfg"]
    window = history_settings["window"]
    decay = history_settings["decay"]
    min_games_home = history_settings["min_games_home"]
    min_games_away = history_settings["min_games_away"]

    leagues_cfg = cfg.get("leagues", {})

    total_fixture_errors = 0

    for league_key, league_meta in leagues_cfg.items():
        rows_for_league25, rows_for_league_btts, league_errors = process_league_fixtures(
            fixtures=fixtures,
            league_key=league_key,
            league_meta=league_meta,
            history_cfg=history_cfg,
            window=window,
            decay=decay,
            min_games_home=min_games_home,
            min_games_away=min_games_away,
            data_raw_dir=BASE / "data_raw",
        )
        rows25.extend(rows_for_league25)
        rows_btts.extend(rows_for_league_btts)
        total_fixture_errors += league_errors

    print(f"[DBG] candidatos O2.5 gerados = {len(rows25)}")
    print(f"[DBG] candidatos BTTS gerados = {len(rows_btts)}")
    print(f"[DBG] erros por fixture = {total_fixture_errors}")

    bankroll_settings = build_bankroll_settings(cfg)
    bankroll25 = bankroll_settings["bankroll25"]
    rules25 = bankroll_settings["rules25"]
    bankroll_btts = bankroll_settings["bankroll_btts"]
    rules_btts = bankroll_settings["rules_btts"]

    out25 = apply_market_rules(rows25, bankroll25, rules25, "O2.5", mode=run_mode)
    out_btts = apply_market_rules(rows_btts, bankroll_btts, rules_btts, "BTTS", mode=run_mode)

    # ── Stage-trace helper ───────────────────────────────────────────────────
    def _trace(label: str, df: pd.DataFrame) -> None:
        """Print every row whose League is not a known European league."""
        eu = {
            "premier", "championship", "alemanha", "alemanha2", "espanha", "franca",
            "franca2", "italia", "italia2", "paises_baixos", "belgica", "portugal",
            "turquia",
        }
        if df is None or df.empty:
            print(f"[TRACE] {label}: dataframe vazio")
            return
        non_eu = df[~df.get("League", pd.Series(dtype=str)).isin(eu)] if "League" in df.columns else df.iloc[0:0]
        eu_count = len(df) - len(non_eu)
        print(f"[TRACE] {label}: total={len(df)} eu={eu_count} non_eu={len(non_eu)}")
        for _, r in non_eu.iterrows():
            edge_pct = float(r.get("Edge", 0) or 0) * 100
            stake    = float(r.get("Stake€", 0) or 0)
            kelly    = float(r.get("KellyTrue", 0) or 0)
            odd      = float(r.get("Odd", 0) or 0)
            print(
                f"[TRACE]   {label} | {r.get('League','')} | "
                f"{r.get('HomeTeam','')} vs {r.get('AwayTeam','')} | "
                f"date={r.get('Date','')} market={r.get('Market','')} | "
                f"odd={odd:.2f} edge={edge_pct:.2f}% kelly={kelly:.4f} stake={stake:.2f}"
            )

    def _trace_dropped(label: str, before: pd.DataFrame, after: pd.DataFrame) -> None:
        """Print rows present in before but absent in after, keyed by (League,HomeTeam,AwayTeam,Market)."""
        eu = {
            "premier", "championship", "alemanha", "alemanha2", "espanha", "franca",
            "franca2", "italia", "italia2", "paises_baixos", "belgica", "portugal",
            "turquia",
        }
        if before is None or before.empty:
            return
        cols_key = ["League", "HomeTeam", "AwayTeam", "Market"]
        before_keys = set(
            tuple(str(r.get(c, "")) for c in cols_key)
            for _, r in before.iterrows()
        )
        after_keys  = set(
            tuple(str(r.get(c, "")) for c in cols_key)
            for _, r in (after.iterrows() if (after is not None and not after.empty) else iter([]))
        )
        dropped = before_keys - after_keys
        non_eu_dropped = [k for k in dropped if k[0] not in eu]
        if non_eu_dropped:
            for k in sorted(non_eu_dropped):
                print(f"[TRACE] DROPPED at {label}: {k}")
        elif dropped:
            print(f"[TRACE] {label}: {len(dropped)} EU picks dropped (no non-EU drops)")
    # ────────────────────────────────────────────────────────────────────────

    _trace("after_apply_market_rules_O25",  out25)
    _trace("after_apply_market_rules_BTTS", out_btts)

    combo_pre = pd.concat([out25, out_btts], ignore_index=True) if (len(out25) or len(out_btts)) else pd.DataFrame()

    if not combo_pre.empty:
        combo_pre_before_dedupe = combo_pre.copy()
        combo_pre = dedupe_correlated_picks(combo_pre)
        _trace_dropped("combined_dedupe", combo_pre_before_dedupe, combo_pre)
        _trace("after_combined_dedupe", combo_pre)

        combo_pre_before_limit = combo_pre.copy()
        combo_pre = limit_picks_per_day(
            combo_pre,
            max_per_day=max_picks_per_day,
            max_global=max_picks_global,
        )
        _trace_dropped("limit_picks_per_day_1", combo_pre_before_limit, combo_pre)
        _trace("after_limit_picks_per_day_1", combo_pre)
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

        _trace_dropped("apply_stakes_O25",  out25_candidates,  out25_final)
        _trace_dropped("apply_stakes_BTTS", out_btts_candidates, out_btts_final)
        _trace("after_apply_stakes_O25",  out25_final)
        _trace("after_apply_stakes_BTTS", out_btts_final)

        combo = pd.concat([out25_final, out_btts_final], ignore_index=True) if (len(out25_final) or len(out_btts_final)) else pd.DataFrame()
        if not combo.empty:
            combo = add_rank_fields(combo)
            combo_before_limit2 = combo.copy()
            combo = limit_picks_per_day(
                combo,
                max_per_day=max_picks_per_day,
                max_global=max_picks_global,
            ).reset_index(drop=True)
            _trace_dropped("limit_picks_per_day_2", combo_before_limit2, combo)
            _trace("after_limit_picks_per_day_2", combo)

    simple, out25_path, out_btts_path, combo_path, combo_github_path, simple_path = save_all_outputs(
        out25_final=out25_final,
        out_btts_final=out_btts_final,
        combo=combo,
        base_dir=BASE,
    )
    _trace_dropped("save_all_outputs", combo, simple)
    _trace("after_save_all_outputs (simple)", simple)

    # Persistir histórico (append mode)
    history = persist_history(simple)
    _trace("after_persist_history", history[history["Liga"].notna()].rename(columns={"Liga": "League"}) if "Liga" in history.columns else history)

    print("OK. Gerados:")
    print(f"- {out25_path.name} ({len(out25_final)} picks)")
    print(f"- {out_btts_path.name} ({len(out_btts_final)} picks)")
    print(f"- {combo_path.name} ({len(combo)} picks)")
    print(f"- {combo_github_path.name} ({len(combo)} picks)")
    print(f"- {simple_path.name} ({len(simple)} picks)")
    print(f"- {HISTORY_PATH.name} ({len(history)} linhas de histórico)")

    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
    CHAT_ID = os.getenv("CHAT_ID", "").strip()

    process_notifications(
        out25_final=out25_final,
        out_btts_final=out_btts_final,
        today_iso=today_iso,
    )

    owner = "jorgepita"
    repo = "apostas-over-futebol"
    branch = "main"
    upload_outputs(
        [out25_path, out_btts_path, combo_path, combo_github_path, simple_path, HISTORY_PATH],
        owner,
        repo,
        branch,
    )


if __name__ == "__main__":
    main()
