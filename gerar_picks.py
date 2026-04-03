# =============================
# PATCH PRINCIPAL (ALTERAÇÕES)
# =============================

def prob_btts_yes_adjusted(lam_home: float, lam_away: float) -> float:
    """
    BTTS com penalização realista (remove inflação do modelo)
    """
    p_home0 = math.exp(-max(0.0, lam_home))
    p_away0 = math.exp(-max(0.0, lam_away))
    raw = 1.0 - p_home0 - p_away0 + (p_home0 * p_away0)

    # 🔥 penalização estrutural
    adj = raw * 0.92

    return float(max(0.0, min(1.0, adj)))


def clamp_prob_btts(prob: float) -> float:
    # 🔥 mais realista
    return float(max(0.30, min(0.68, prob)))


def clamp_prob_o25(prob: float) -> float:
    # 🔥 ligeiramente mais permissivo
    return float(max(0.20, min(0.72, prob)))


def get_market_thresholds(mode: str, market: str) -> dict:
    market = str(market).strip().upper()

    if mode == "test":

        if market == "O2.5":
            return {
                "lam_t_min": 1.65,   # 🔥 mais solto
                "odd_min": 1.45,
                "odd_max": 2.80,
                "edge_min_quality": -0.08,
            }

        if market == "BTTS":
            return {
                "lam_h_min": 0.70,
                "lam_a_min": 0.70,
                "lam_t_min": 1.95,
                "odd_min": 1.50,
                "odd_max": 2.20,
                "edge_min_quality": -0.03,
            }

    # fallback normal mode
    return {}


def market_quality_filter(row: dict, mode: str = "normal") -> bool:
    market = str(row.get("Market", "")).strip().upper()
    odd = float(row.get("Odd", 0.0) or 0.0)
    lam_h = float(row.get("LambdaHome", 0.0) or 0.0)
    lam_a = float(row.get("LambdaAway", 0.0) or 0.0)
    lam_t = float(row.get("LambdaTotal", 0.0) or 0.0)
    edge = float(row.get("Edge", 0.0) or 0.0)

    if odd <= 1.01:
        return False

    th = get_market_thresholds(mode, market)

    if market == "O2.5":
        if lam_t < th["lam_t_min"]:
            return False
        if odd < th["odd_min"] or odd > th["odd_max"]:
            return False
        if edge < th["edge_min_quality"]:
            return False

    elif market == "BTTS":

        # 🔥 novo filtro de equilíbrio (muito importante)
        if abs(lam_h - lam_a) > 1.2:
            return False

        if lam_h < th["lam_h_min"] or lam_a < th["lam_a_min"]:
            return False
        if lam_t < th["lam_t_min"]:
            return False
        if odd < th["odd_min"] or odd > th["odd_max"]:
            return False
        if edge < th["edge_min_quality"]:
            return False

    return True
