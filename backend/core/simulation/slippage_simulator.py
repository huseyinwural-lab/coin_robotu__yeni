def simulate_expected_slippage(
    *,
    order_size: float,
    volatility_regime: str,
    spread_bps: float,
    liquidity_score: float,
    impact_score: float,
) -> dict:
    size = max(float(order_size or 0.0), 0.0)
    spread = max(float(spread_bps or 0.0), 0.0)
    liquidity = max(min(float(liquidity_score or 0.0), 1.0), 0.0)
    impact = max(float(impact_score or 0.0), 0.0)

    regime = str(volatility_regime or "NORMAL").upper()
    regime_multiplier = {"LOW": 0.8, "NORMAL": 1.0, "HIGH": 1.35, "EXTREME": 1.8}.get(regime, 1.0)

    slippage = (spread * 0.6 + size * 0.00002 + impact * 0.08) * regime_multiplier * (1 + (1 - liquidity) * 0.5)
    return {
        "expected_slippage_bps": round(max(slippage, 0.1), 4),
        "volatility_regime": regime,
    }
