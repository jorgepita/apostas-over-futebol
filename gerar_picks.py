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
from src.calculations import (
    poisson_cdf,
    prob_over25,
    prob_btts_yes_adjusted,
    kelly_fraction,
    safe_mean,
    weighted_mean,
    clamp_strength,
    league_avgs,
    last_n_home,
    last_n_away,
    compute_lambdas,
    clamp_prob_o25,
    clamp_prob_btts,
    clamp_edge_o25,
    clamp_edge_btts,
)
from src.state import (
    load_sent_state,
    save_sent_state,
    pick_id,
)
from src.history import (
    history_pick_id_from_simple,
    ensure_simple_columns,
    load_history,
    merge_into_history,
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

DEFAULT_MAX_PICKS_PER_DAY = 12
DEFAULT_MAX_PICKS_GLOBAL = 36

DEFAULT_KELLY_FRACTION = 0.18
DEFAULT_CAP_FRAC = 0.04
DEFAULT_DAILY_CAP_FRAC = 0.12
DEFAULT_MAX_ODD_O25 = 2.20
DEFAULT_MAX_ODD_BTTS = 2.20


# =============================
# Anti-duplicados (por dia)
# =============================

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    return df


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
    
    cfg_path = BASE / "config.json"
    if not cfg_path.exists():
        raise SystemExit("Falta config.json na pasta do projeto.")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    run_mode = "normal"
    print(f"[DBG] gerar_picks mode={run_mode}")

    run_cfg = cfg.get("run", {})
    max_picks_per_day = int(run_cfg.get("max_picks_per_day", DEFAULT_MAX_PICKS_PER_DAY))
    max_picks_global = int(run_cfg.get("max_picks_global", DEFAULT_MAX_PICKS_GLOBAL))
    print(f"[DBG] max_picks_per_day={max_picks_per_day} | max_picks_global={max_picks_global}")

    GITHUB_RAW_URL = "https://raw.githubusercontent.com/jorgepita/apostas-over-futebol/main/fixtures_today.csv"

    response = requests.get(GITHUB_RAW_URL)
    response.raise_for_status()

    fixtures = pd.read_csv(StringIO(response.text), sep=";")
    fixtures = normalize_columns(fixtures)

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
