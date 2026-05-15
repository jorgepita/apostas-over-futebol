DEFAULT_MAX_ODD_O25 = 2.20
DEFAULT_MAX_ODD_BTTS = 2.20


def get_market_thresholds(mode: str, market: str) -> dict:
    market = str(market).strip().upper()

    base = {
        "lam_h_min": 0.0,
        "lam_a_min": 0.0,
        "lam_t_min": 0.0,
        "odd_min": 1.01,
        "odd_max": 99.0,
        "edge_min_quality": -1.0,
        "max_lambda_ratio": 99.0,
        "max_lambda_gap": 99.0,
        "min_lambda_product": 0.0,
    }

    if market == "O2.5":
        return {
            **base,
            "lam_t_min": 1.90,
            "odd_min": 1.55,
            "odd_max": DEFAULT_MAX_ODD_O25,
            "edge_min_quality": 0.00,
        }

    if market == "BTTS":
        return {
            **base,
            "lam_h_min": 0.75,
            "lam_a_min": 0.75,
            "lam_t_min": 2.05,
            "odd_min": 1.55,
            "odd_max": DEFAULT_MAX_ODD_BTTS,
            "edge_min_quality": 0.00,
            "max_lambda_ratio": 1.65,
            "max_lambda_gap": 0.65,
            "min_lambda_product": 0.80,
        }

    return base


def get_effective_max_odd(rules: dict, market: str, mode: str) -> float:
    market = str(market).strip().upper()
    th = get_market_thresholds(mode, market)
    th_max = float(th.get("odd_max", 99.0))

    if market == "O2.5":
        fallback = DEFAULT_MAX_ODD_O25
    elif market == "BTTS":
        fallback = DEFAULT_MAX_ODD_BTTS
    else:
        fallback = th_max

    rules_max = rules.get("odd_max", fallback)
    try:
        rules_max = float(rules_max)
    except Exception:
        rules_max = fallback

    return float(min(th_max, rules_max))


def btts_balance_filter(row: dict, th: dict) -> tuple[bool, str]:
    lam_h = float(row.get("LambdaHome", 0.0) or 0.0)
    lam_a = float(row.get("LambdaAway", 0.0) or 0.0)

    bigger = max(lam_h, lam_a)
    smaller = min(lam_h, lam_a)
    ratio = (bigger / smaller) if smaller > 0 else 99.0
    gap = abs(lam_h - lam_a)
    product = lam_h * lam_a

    if ratio > float(th.get("max_lambda_ratio", 99.0)):
        return False, "btts_ratio"
    if gap > float(th.get("max_lambda_gap", 99.0)):
        return False, "btts_gap"
    if product < float(th.get("min_lambda_product", 0.0)):
        return False, "btts_product"

    return True, "ok"


def evaluate_market_quality(row: dict, mode: str = "normal") -> tuple[bool, str]:
    market = str(row.get("Market", "")).strip().upper()
    odd = float(row.get("Odd", 0.0) or 0.0)
    lam_h = float(row.get("LambdaHome", 0.0) or 0.0)
    lam_a = float(row.get("LambdaAway", 0.0) or 0.0)
    lam_t = float(row.get("LambdaTotal", 0.0) or 0.0)
    edge = float(row.get("Edge", 0.0) or 0.0)

    if odd <= 1.01:
        return False, "odd_invalid"

    th = get_market_thresholds(mode, market)

    if market == "O2.5":
        if lam_t < float(th["lam_t_min"]):
            return False, "lam_t_low"
        if odd < float(th["odd_min"]):
            return False, "odd_low"
        if odd > float(th["odd_max"]):
            return False, "odd_high"
        if edge < float(th["edge_min_quality"]):
            return False, "edge_quality_low"
        return True, "ok"

    if market == "BTTS":
        if lam_h < float(th["lam_h_min"]):
            return False, "lam_h_low"
        if lam_a < float(th["lam_a_min"]):
            return False, "lam_a_low"
        if lam_t < float(th["lam_t_min"]):
            return False, "lam_t_low"
        if odd < float(th["odd_min"]):
            return False, "odd_low"
        if odd > float(th["odd_max"]):
            return False, "odd_high"
        if edge < float(th["edge_min_quality"]):
            return False, "edge_quality_low"

        ok_balance, reason = btts_balance_filter(row, th)
        if not ok_balance:
            return False, reason

        return True, "ok"

    return True, "ok"


def market_quality_filter(row: dict, mode: str = "normal") -> bool:
    ok, _ = evaluate_market_quality(row, mode=mode)
    return ok
