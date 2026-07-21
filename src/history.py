from pathlib import Path

import pandas as pd

HISTORY_COLUMNS = [
    "Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€", "Edge%",
    "Apostada", "OddReal", "StakeReal€",
    "Resultado", "Placar", "Lucro€", "LucroReal€", "KickoffUTC",
    "SettlementReason", "MissingAttempts",
]
# Must stay a superset-compatible mirror of update_results.py's CSV_COLUMNS —
# same names, same order — for every settlement-written field. This list was
# not updated when Placar was added (Phase 26.19), which caused
# ensure_simple_columns()'s reindex (below) to silently strip Placar from
# every settled row on each daily generation cycle (merge_into_history()) —
# already active in production, confirmed against real data by a dedicated
# pre-commit safety audit of Phase 26.43. SettlementReason/MissingAttempts
# (also Phase 26.43) would have suffered the identical fate. If
# update_results.py's CSV_COLUMNS ever gains another
# settlement-written field, add it here too in the same position, or this
# erasure bug recurs for the new field.

BASE = Path(__file__).resolve().parent.parent
HISTORY_PATH = BASE / "picks_history.csv"


def history_pick_id_from_simple(row: pd.Series) -> str:
    return (
        f"{str(row.get('Data', '')).strip()}|"
        f"{str(row.get('Liga', '')).strip()}|"
        f"{str(row.get('Jogo', '')).strip()}|"
        f"{str(row.get('Mercado', '')).strip()}"
    )
