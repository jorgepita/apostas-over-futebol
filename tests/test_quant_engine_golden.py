"""
tests/test_quant_engine_golden.py

Golden-vector conformance test — Python side.

tests/golden_vectors.json is a frozen set of input -> output pairs computed
once from the real src/calculations.py functions (the canonical
implementation). This test re-runs those same functions against the same
inputs and asserts the outputs still match.

This file alone does not prove cross-language equivalence — its JS sibling,
run separately with Node (see DEVELOPMENT_GUIDELINES.md / 04_Backend.md for
the run command), re-checks the SAME vectors against the QuantEngine module
in index.html. Together, the two suites are the permanent safeguard against
the Python and JS engines silently drifting apart. If a formula in
src/calculations.py is intentionally changed, regenerate golden_vectors.json
(see the generation script referenced in 04_Backend.md) and update the JS
QuantEngine to match before both suites will pass again.

Run with:  python -m pytest tests/test_quant_engine_golden.py -v
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from src.calculations import (
    poisson_cdf,
    prob_over25,
    btts_prob_diagnostics,
    prob_btts_yes_adjusted,
    kelly_fraction,
    clamp_strength,
    clamp_prob_o25,
    clamp_prob_btts,
    clamp_edge_o25,
    clamp_edge_btts,
    confidence_factor,
    fair_odds,
    expected_value,
    apply_lambda_boost,
    weighted_mean,
    compute_lambdas,
)

VECTORS_PATH = Path(__file__).resolve().parent / "golden_vectors.json"
VECTORS = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))

TOL = 1e-9


def approx(actual, expected):
    if expected is None:
        return actual is None
    return actual == pytest.approx(expected, abs=TOL, rel=TOL)


@pytest.mark.parametrize("case", VECTORS["poisson_cdf"])
def test_golden_poisson_cdf(case):
    assert approx(poisson_cdf(case["k"], case["lam"]), case["expected"])


@pytest.mark.parametrize("case", VECTORS["prob_over25"])
def test_golden_prob_over25(case):
    assert approx(prob_over25(case["lam_total"]), case["expected"])


@pytest.mark.parametrize("case", VECTORS["btts_prob_diagnostics"])
def test_golden_btts_prob_diagnostics(case):
    result = btts_prob_diagnostics(case["lam_home"], case["lam_away"], adj=case["adj"])
    for key, expected_value_ in case["expected"].items():
        assert approx(result[key], expected_value_), f"key={key}"


@pytest.mark.parametrize("case", VECTORS["prob_btts_yes_adjusted"])
def test_golden_prob_btts_yes_adjusted(case):
    result = prob_btts_yes_adjusted(case["lam_home"], case["lam_away"], adj=case["adj"])
    assert approx(result, case["expected"])


@pytest.mark.parametrize("case", VECTORS["kelly_fraction"])
def test_golden_kelly_fraction(case):
    assert approx(kelly_fraction(case["p"], case["odd"]), case["expected"])


@pytest.mark.parametrize("case", VECTORS["clamp_strength"])
def test_golden_clamp_strength(case):
    assert approx(clamp_strength(case["x"]), case["expected"])


@pytest.mark.parametrize("case", VECTORS["clamp_prob_o25"])
def test_golden_clamp_prob_o25(case):
    assert approx(clamp_prob_o25(case["prob"]), case["expected"])


@pytest.mark.parametrize("case", VECTORS["clamp_prob_btts"])
def test_golden_clamp_prob_btts(case):
    assert approx(clamp_prob_btts(case["prob"]), case["expected"])


@pytest.mark.parametrize("case", VECTORS["clamp_edge_o25"])
def test_golden_clamp_edge_o25(case):
    assert approx(clamp_edge_o25(case["edge"]), case["expected"])


@pytest.mark.parametrize("case", VECTORS["clamp_edge_btts"])
def test_golden_clamp_edge_btts(case):
    assert approx(clamp_edge_btts(case["edge"]), case["expected"])


@pytest.mark.parametrize("case", VECTORS["confidence_factor"])
def test_golden_confidence_factor(case):
    assert approx(confidence_factor(case["edge"], scale=case["scale"]), case["expected"])


@pytest.mark.parametrize("case", VECTORS["fair_odds"])
def test_golden_fair_odds(case):
    assert approx(fair_odds(case["prob_model"]), case["expected"])


@pytest.mark.parametrize("case", VECTORS["expected_value"])
def test_golden_expected_value(case):
    assert approx(expected_value(case["prob_model"], case["odd"], case["stake"]), case["expected"])


@pytest.mark.parametrize("case", VECTORS["apply_lambda_boost"])
def test_golden_apply_lambda_boost(case):
    lam_h, lam_a, lam_t = apply_lambda_boost(case["lam_home"], case["lam_away"], case["boost"])
    assert approx(lam_h, case["expected"]["lam_home"])
    assert approx(lam_a, case["expected"]["lam_away"])
    assert approx(lam_t, case["expected"]["lam_total"])


@pytest.mark.parametrize("case", VECTORS["weighted_mean"])
def test_golden_weighted_mean(case):
    assert approx(weighted_mean(case["values"], decay=case["decay"]), case["expected"])


@pytest.mark.parametrize("case", VECTORS["compute_lambdas"], ids=lambda c: c["label"])
def test_golden_compute_lambdas(case):
    df = pd.DataFrame(case["history"])
    df["Date"] = pd.to_datetime(df["Date"])
    lam_h, lam_a, lam_t = compute_lambdas(
        df, case["home"], case["away"],
        window=case["window"], decay=case["decay"],
        min_games_home=case["min_games_home"], min_games_away=case["min_games_away"],
    )
    assert approx(lam_h, case["expected"]["lam_home"])
    assert approx(lam_a, case["expected"]["lam_away"])
    assert approx(lam_t, case["expected"]["lam_total"])
