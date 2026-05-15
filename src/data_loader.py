import requests
from io import StringIO

import pandas as pd

FIXTURES_COLUMNS: set[str] = set()


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    return df


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
        if col in FIXTURES_COLUMNS:
            odd = _to_float(fx_row.get(col, 0.0), 0.0)
            if odd > 1.01:
                return odd
    return 0.0


def load_fixtures(fixtures_url: str) -> pd.DataFrame:
    response = requests.get(fixtures_url)
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text), sep=";")
    df = normalize_columns(df)

    global FIXTURES_COLUMNS
    FIXTURES_COLUMNS = set(df.columns)

    return df
