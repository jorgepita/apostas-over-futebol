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

DEFAULT_BTTS_PROBABILITY_ADJUSTMENT = 0.885

# Void policy — see docs/09_Architecture_Decisions.md ADR-017 and
# docs/05_Known_Issues.md. These are the fallback values used whenever
# config.json["settlement"]["void_policy"] is missing or a given key is
# absent/invalid; the canonical, operator-editable values live in
# config.json, not here.
DEFAULT_POSTPONED_VOID_AFTER_HOURS = 48
DEFAULT_MISSING_FIXTURE_VOID_AFTER_HOURS = 72
DEFAULT_MANUAL_VOID_AVAILABLE_AFTER_HOURS = 24
DEFAULT_MISSING_FIXTURE_MIN_ATTEMPTS = 3


def load_config(base_path: Path) -> dict:
    cfg_path = Path(base_path) / "config.json"

    if not cfg_path.exists():
        raise SystemExit("Falta config.json na pasta do projeto.")

    return json.loads(cfg_path.read_text(encoding="utf-8"))


def get_void_policy(cfg: dict) -> dict:
    """Reads config.json["settlement"]["void_policy"], defensively validating
    each value (must coerce to a positive number) and falling back to the
    DEFAULT_* constant above per-key on anything missing or invalid — a bad
    single key never disables the other three."""
    raw = ((cfg or {}).get("settlement", {}) or {}).get("void_policy", {}) or {}

    def _positive_number(value, default):
        try:
            v = float(value)
            return v if v > 0 else default
        except (TypeError, ValueError):
            return default

    def _positive_int(value, default):
        try:
            v = int(value)
            return v if v > 0 else default
        except (TypeError, ValueError):
            return default

    return {
        "postponed_void_after_hours": _positive_number(
            raw.get("postponed_void_after_hours"), DEFAULT_POSTPONED_VOID_AFTER_HOURS,
        ),
        "missing_fixture_void_after_hours": _positive_number(
            raw.get("missing_fixture_void_after_hours"), DEFAULT_MISSING_FIXTURE_VOID_AFTER_HOURS,
        ),
        "manual_void_available_after_hours": _positive_number(
            raw.get("manual_void_available_after_hours"), DEFAULT_MANUAL_VOID_AVAILABLE_AFTER_HOURS,
        ),
        "missing_fixture_min_attempts": _positive_int(
            raw.get("missing_fixture_min_attempts"), DEFAULT_MISSING_FIXTURE_MIN_ATTEMPTS,
        ),
    }
