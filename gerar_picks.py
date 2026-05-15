# força deploy
print("### TESTE NOVO CODIGO ###")

import base64
import json
import requests
from io import StringIO
import math
import os
from pathlib import Path
from urllib import request, parse, error
from datetime import datetime, timedelta, timezone

import pandas as pd
from src.state import (
    load_sent_state,
    save_sent_state,
    pick_id,
)
from src.history import (
    history_pick_id_from_simple,
)
from src.output_utils import (
    ensure_simple_columns,
    load_history,
    merge_into_history,
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
HISTORY_PATH = BASE / "picks_history.csv"


# =============================
# Anti-duplicados (por dia)
# =============================


# =============================
# Telegram
# =============================



# =============================
# Modo normal / teste
# =============================
def get_run_mode(cfg: dict) -> str:
    return "normal"


# =============================
# Main
# =============================
def main():
    print("### TESTE NOVO CODIGO ###")
    # RESET TOTAL DO HISTÓRICO (modo arranque limpo)

    if os.getenv("RESET_HISTORY", "1") == "1":
        print("[DBG] RESET_HISTORY ativo -> limpar histórico")
       
        pd.DataFrame(columns=[
            "Data","Liga","Jogo","Mercado","Odd","Stake€","Edge%",
            "Apostada","OddReal","StakeReal€",
            "Resultado","Lucro€","LucroReal€"
    ]).to_csv(HISTORY_PATH, index=False, sep=";", encoding="utf-8")
    
    cfg = load_config(BASE)

    run_mode = "normal"
    print(f"[DBG] gerar_picks mode={run_mode}")

    run_cfg = cfg.get("run", {})
    max_picks_per_day = int(run_cfg.get("max_picks_per_day", DEFAULT_MAX_PICKS_PER_DAY))
    max_picks_global = int(run_cfg.get("max_picks_global", DEFAULT_MAX_PICKS_GLOBAL))
    print(f"[DBG] max_picks_per_day={max_picks_per_day} | max_picks_global={max_picks_global}")

    GITHUB_RAW_URL = "https://raw.githubusercontent.com/jorgepita/apostas-over-futebol/main/fixtures_today.csv"

    fixtures = load_fixtures(GITHUB_RAW_URL)

    fixtures["Date"] = pd.to_datetime(fixtures["Date"], errors="coerce")
    
    print("[DEBUG] total fixtures:", len(fixtures))
    print("[DEBUG] datas únicas:", sorted(fixtures["Date"].astype(str).unique())[:10])

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
   
    print("==== DEBUG DATES ====")
    print(fixtures["Date"].value_counts().sort_index())
    
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

    bankroll_cfg = cfg.get("bankroll", {})
    rules_cfg = cfg.get("rules", {})

    bankroll25 = float(bankroll_cfg.get("over25", 0.0))
    rules25 = dict(rules_cfg.get("over25", {}))
    rules25.setdefault("edge_max", 0.16)
    rules25.setdefault("odd_max", DEFAULT_MAX_ODD_O25)
    rules25.setdefault("kelly_fraction", DEFAULT_KELLY_FRACTION)
    rules25.setdefault("cap_frac", DEFAULT_CAP_FRAC)
    rules25.setdefault("daily_cap_frac", DEFAULT_DAILY_CAP_FRAC)

    bankroll_btts = float(bankroll_cfg.get("btts", 0.0))
    rules_btts = dict(rules_cfg.get("btts", {}))
    rules_btts.setdefault("edge_max", 0.14)
    rules_btts.setdefault("odd_max", DEFAULT_MAX_ODD_BTTS)
    rules_btts.setdefault("kelly_fraction", DEFAULT_KELLY_FRACTION)
    rules_btts.setdefault("cap_frac", DEFAULT_CAP_FRAC)
    rules_btts.setdefault("daily_cap_frac", DEFAULT_DAILY_CAP_FRAC)

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

    # RESET TOTAL DO HISTÓRICO (modo produção inicial)
    
    today_str = datetime.now().date().isoformat()
    simple = simple[simple["Data"] >= today_str].copy()

    history = simple.copy()

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
