"""
tests/test_quant_engine.py

Unit tests for the quantitative-engine functions added in src/calculations.py
as part of the shared Python/JS QuantEngine (confidence_factor, fair_odds,
expected_value). The pre-existing calculation functions (compute_lambdas,
prob_over25, prob_btts_yes_adjusted, kelly_fraction, clamp_*) are unchanged
and already covered by production usage; this file focuses on the three new
named functions and their pandas-Series compatibility (relied on by
apply_stakes() in src/market_rules.py).

Run with:  python -m pytest tests/test_quant_engine.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.calculations import confidence_factor, fair_odds, expected_value


def test_confidence_factor_zero_edge():
    assert confidence_factor(0.0) == 0.0


def test_confidence_factor_negative_edge_clamps_to_zero():
    assert confidence_factor(-0.05) == 0.0


def test_confidence_factor_scale_edge_is_one():
    assert confidence_factor(0.10) == 1.0


def test_confidence_factor_above_scale_clamps_to_one():
    assert confidence_factor(0.50) == 1.0


def test_confidence_factor_midpoint():
    assert confidence_factor(0.05) == 0.5


def test_confidence_factor_custom_scale():
    assert confidence_factor(0.05, scale=0.20) == 0.25


def test_confidence_factor_series_matches_scalar_elementwise():
    edges = pd.Series([-0.05, 0.0, 0.05, 0.10, 0.20])
    result = confidence_factor(edges)
    expected = pd.Series([0.0, 0.0, 0.5, 1.0, 1.0])
    assert (result == expected).all()


def test_confidence_factor_series_matches_pre_extraction_formula():
    # This is the exact expression apply_stakes() used before extraction —
    # asserting the refactor is behaviourally identical.
    edges = pd.Series([-0.10, -0.01, 0.0, 0.02, 0.07, 0.10, 0.15])
    old_formula = (edges / 0.10).clip(lower=0.0, upper=1.0)
    new_function = confidence_factor(edges)
    assert (old_formula == new_function).all()


def test_fair_odds_typical_probability():
    assert fair_odds(0.55) == 1.0 / 0.55


def test_fair_odds_zero_probability_returns_none():
    assert fair_odds(0.0) is None


def test_fair_odds_none_probability_returns_none():
    assert fair_odds(None) is None


def test_fair_odds_negative_probability_returns_none():
    assert fair_odds(-0.1) is None


def test_expected_value_positive_edge():
    # p=0.55, odd=2.0, stake=10 -> EV = 10 * (0.55*2.0 - 1) = 1.0
    assert round(expected_value(0.55, 2.0, 10.0), 6) == 1.0


def test_expected_value_negative_edge():
    # p=0.40, odd=2.0, stake=10 -> EV = 10 * (0.40*2.0 - 1) = -2.0
    assert round(expected_value(0.40, 2.0, 10.0), 6) == -2.0


def test_expected_value_zero_stake_is_zero():
    assert expected_value(0.60, 1.90, 0.0) == 0.0
