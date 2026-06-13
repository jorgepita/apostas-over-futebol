from pathlib import Path

import pandas as pd

HISTORY_COLUMNS = [
    "Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€", "Edge%",
    "Apostada", "OddReal", "StakeReal€",
    "Resultado", "Lucro€", "LucroReal€", "KickoffUTC",
]

BASE = Path(__file__).resolve().parent.parent
HISTORY_PATH = BASE / "picks_history.csv"


def history_pick_id_from_simple(row: pd.Series) -> str:
    return (
        f"{str(row.get('Data', '')).strip()}|"
        f"{str(row.get('Liga', '')).strip()}|"
        f"{str(row.get('Jogo', '')).strip()}|"
        f"{str(row.get('Mercado', '')).strip()}"
    )
