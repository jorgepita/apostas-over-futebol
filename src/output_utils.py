from pathlib import Path

import pandas as pd
from src.history import history_pick_id_from_simple

BASE = Path(__file__).resolve().parent.parent
HISTORY_PATH = BASE / "picks_history.csv"


def ensure_simple_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cols = [
        "Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€", "Edge%",
        "Apostada", "OddReal", "StakeReal€",
        "Resultado", "Lucro€", "LucroReal€",
    ]
    for col in cols:
        if col not in df.columns:
            df[col] = ""
    return df[cols].copy()


def load_history() -> pd.DataFrame:
    cols = [
        "Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€", "Edge%",
        "Apostada", "OddReal", "StakeReal€",
        "Resultado", "Lucro€", "LucroReal€",
    ]
    if not HISTORY_PATH.exists():
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_csv(HISTORY_PATH, sep=";", dtype=str).fillna("")
        return ensure_simple_columns(df)
    except Exception:
        return pd.DataFrame(columns=cols)


def merge_into_history(simple_df: pd.DataFrame) -> pd.DataFrame:
    history = load_history()
    history = ensure_simple_columns(history)
    simple_df = ensure_simple_columns(simple_df)

    existing_ids = {history_pick_id_from_simple(row) for _, row in history.iterrows()}
    new_rows = []

    for _, row in simple_df.iterrows():
        pid = history_pick_id_from_simple(row)
        if pid not in existing_ids:
            new_rows.append(row.to_dict())

    if new_rows:
        history = pd.concat([history, pd.DataFrame(new_rows)], ignore_index=True)

    if "Data" in history.columns:
        history["_sort_date"] = pd.to_datetime(history["Data"], errors="coerce")
        history = history.sort_values(
            ["_sort_date", "Liga", "Jogo", "Mercado"],
            ascending=[True, True, True, True],
            na_position="last",
        )
        history = history.drop(columns=["_sort_date"])

    history = history.reset_index(drop=True)
    return ensure_simple_columns(history)
