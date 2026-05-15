from __future__ import annotations

from src.config import (
    DEFAULT_CAP_FRAC,
    DEFAULT_DAILY_CAP_FRAC,
    DEFAULT_KELLY_FRACTION,
    DEFAULT_MAX_ODD_BTTS,
    DEFAULT_MAX_ODD_O25,
    DEFAULT_MAX_PICKS_GLOBAL,
    DEFAULT_MAX_PICKS_PER_DAY,
)


def build_runtime_settings(cfg: dict) -> dict:
    run_cfg = cfg.get("run", {})
    return {
        "run_mode": "normal",
        "run_cfg": run_cfg,
        "max_picks_per_day": int(run_cfg.get("max_picks_per_day", DEFAULT_MAX_PICKS_PER_DAY)),
        "max_picks_global": int(run_cfg.get("max_picks_global", DEFAULT_MAX_PICKS_GLOBAL)),
        "days_ahead": max(1, int(run_cfg.get("days_ahead", 1))),
    }


def build_bankroll_settings(cfg: dict) -> dict:
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

    return {
        "bankroll_cfg": bankroll_cfg,
        "rules_cfg": rules_cfg,
        "bankroll25": bankroll25,
        "rules25": rules25,
        "bankroll_btts": bankroll_btts,
        "rules_btts": rules_btts,
    }


def build_history_settings(cfg: dict) -> dict:
    history_cfg = cfg.get("history", {})
    return {
        "history_cfg": history_cfg,
        "window": int(history_cfg.get("window", 12)),
        "decay": float(history_cfg.get("decay", 0.90)),
        "min_games_home": int(history_cfg.get("min_games_home", 8)),
        "min_games_away": int(history_cfg.get("min_games_away", 8)),
    }
