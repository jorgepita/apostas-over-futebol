from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from src.history import HISTORY_COLUMNS, HISTORY_PATH
from src.integrations import _send_in_chunks, build_message, df_to_rows, upload_csvs_to_github
from src.state import load_sent_state, save_sent_state, pick_id


def save_all_outputs(
    out25_final: pd.DataFrame,
    out_btts_final: pd.DataFrame,
    combo: pd.DataFrame,
    base_dir: Path,
) -> tuple[pd.DataFrame, Path, Path, Path, Path, Path]:
    out25_path = base_dir / "picks_over25.csv"
    out_btts_path = base_dir / "picks_btts.csv"
    combo_path = base_dir / "picks_hoje.csv"
    combo_github_path = base_dir / "picks_hoje_github.csv"
    simple_path = base_dir / "picks_hoje_simplificado.csv"

    out25_final.to_csv(out25_path, index=False, encoding="utf-8", sep=";")
    out_btts_final.to_csv(out_btts_path, index=False, encoding="utf-8", sep=";")
    combo.to_csv(combo_path, index=False, encoding="utf-8", sep=";")
    combo.to_csv(combo_github_path, index=False, encoding="utf-8", sep=",")

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

        simple = simple[HISTORY_COLUMNS].copy()
        simple = simple[(simple["Odd"] > 1.01) & (simple["Stake€"] > 0) & (simple["Edge%"] > 0)].copy()
    else:
        simple = pd.DataFrame(columns=HISTORY_COLUMNS)

    simple.to_csv(simple_path, index=False, encoding="utf-8", sep=";")

    return simple, out25_path, out_btts_path, combo_path, combo_github_path, simple_path


def persist_history(simple: pd.DataFrame) -> pd.DataFrame:
    history = simple.copy()
    history.to_csv(HISTORY_PATH, index=False, encoding="utf-8", sep=";")
    return history


def process_notifications(
    out25_final: pd.DataFrame,
    out_btts_final: pd.DataFrame,
    today_iso: str,
) -> None:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
    CHAT_ID = os.getenv("CHAT_ID", "").strip()

    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Telegram: TOKEN ou CHAT_ID em falta (não enviei mensagem).")
        return

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


def upload_outputs(files: list[Path], owner: str, repo: str, branch: str) -> None:
    upload_csvs_to_github(files, owner, repo, branch)
