from __future__ import annotations

import json
from pathlib import Path

DEFAULT_MAX_PICKS_PER_DAY = 12
DEFAULT_MAX_PICKS_GLOBAL = 36

DEFAULT_KELLY_FRACTION = 0.18
DEFAULT_CAP_FRAC = 0.04
DEFAULT_DAILY_CAP_FRAC = 0.12

DEFAULT_MAX_ODD_O25 = 2.20
DEFAULT_MAX_ODD_BTTS = 2.30


def load_config(base_path: Path) -> dict:
    cfg_path = Path(base_path) / "config.json"

    if not cfg_path.exists():
        raise SystemExit("Falta config.json na pasta do projeto.")

    return json.loads(cfg_path.read_text(encoding="utf-8"))
