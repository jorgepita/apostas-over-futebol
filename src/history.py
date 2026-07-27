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


def fixture_id_from_parts(date, liga, jogo) -> str:
    """Fixture-only identity — Date + League + Game, deliberately WITHOUT Market.

    This is the canonical identity used to answer "has this bot fixture already
    received a persisted market recommendation?" (the Policy A fixture-level
    market lock — see ADR-018). It is intentionally the same three components as
    history_pick_id_from_simple(), minus Mercado, so the two never drift apart.
    """
    return f"{str(date).strip()}|{str(liga).strip()}|{str(jogo).strip()}"


def fixture_id_from_simple(row) -> str:
    """Fixture-only identity from a Data|Liga|Jogo|Mercado-shaped row — the schema
    used by picks_history.csv, picks_hoje_simplificado.csv, and load_history()."""
    return fixture_id_from_parts(row.get("Data", ""), row.get("Liga", ""), row.get("Jogo", ""))


def fixture_id_from_candidate(row) -> str:
    """Fixture-only identity from an in-memory generation candidate row — the
    Date/LeagueName/HomeTeam/AwayTeam schema used in main.py's combo_pre before
    save_all_outputs() flattens it into Data/Liga/Jogo. 'Jogo' is built exactly
    the way save_all_outputs() builds it (HomeTeam + ' vs ' + AwayTeam), so a
    candidate row and the history row it eventually becomes always resolve to
    the identical fixture id.
    """
    jogo = f"{row.get('HomeTeam', '')} vs {row.get('AwayTeam', '')}"
    return fixture_id_from_parts(row.get("Date", ""), row.get("LeagueName", ""), jogo)


def history_pick_id_from_simple(row: pd.Series) -> str:
    return f"{fixture_id_from_simple(row)}|{str(row.get('Mercado', '')).strip()}"
