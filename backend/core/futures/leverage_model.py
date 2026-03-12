def suggest_dynamic_leverage(
    *,
    strategy_score: float,
    volatility_score: float,
    liquidity_score: float,
    funding_score: float,
    base_leverage: float = 2.0,
    max_leverage: float = 5.0,
) -> dict:
    composite = (
        strategy_score * 0.40
        + volatility_score * 0.20
        + liquidity_score * 0.20
        + funding_score * 0.20
    )
    scaled = base_leverage + (composite / 100) * 2.5
    final_leverage = min(max(scaled, 1.0), max_leverage)
    return {
        "final_leverage": round(final_leverage, 4),
        "leverage_score": round(composite, 4),
    }
