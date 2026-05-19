import pandas as pd
from src.history import HISTORY_COLUMNS, HISTORY_PATH, history_pick_id_from_simple


def ensure_simple_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cols = HISTORY_COLUMNS
    for col in cols:
        if col not in df.columns:
            df[col] = ""
    return df[cols].copy()


def load_history() -> pd.DataFrame:
    if not HISTORY_PATH.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    
    # Se o ficheiro estiver vazio, retornamos apenas as colunas
    if HISTORY_PATH.stat().st_size == 0:
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    try:
        df = pd.read_csv(HISTORY_PATH, sep=";", dtype=str, encoding="utf-8").fillna("")
        return ensure_simple_columns(df)
    except Exception as e:
        print(f"[ERROR] Falha crítica a ler {HISTORY_PATH}: {e}")
        # Em caso de erro, tentamos ler com vírgula (fallback comum)
        try:
            df = pd.read_csv(HISTORY_PATH, sep=",", dtype=str, encoding="utf-8").fillna("")
            return ensure_simple_columns(df)
        except Exception:
            # Se falhar tudo, lançamos erro para evitar que persist_history sobrescreva o ficheiro
            raise RuntimeError(f"Não foi possível ler o histórico em {HISTORY_PATH}. Operação abortada para evitar perda de dados.")


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
