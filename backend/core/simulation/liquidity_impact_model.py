def estimate_liquidity_impact(
    *,
    order_size: float,
    market_depth: float,
    spread_width_bps: float,
    liquidity_tier: str,
) -> dict:
    depth = max(float(market_depth or 0.0), 1.0)
    size = max(float(order_size or 0.0), 0.0)
    spread = max(float(spread_width_bps or 0.0), 0.0)

    tier = str(liquidity_tier or "MEDIUM").upper()
    tier_multiplier = {"HIGH": 0.8, "MEDIUM": 1.0, "LOW": 1.25}.get(tier, 1.0)

    impact_ratio = (size / depth) * tier_multiplier
    impact_score = min(100.0, max(0.0, impact_ratio * 120 + spread * 0.15))
    return {
        "impact_ratio": round(impact_ratio, 6),
        "impact_score": round(impact_score, 2),
        "liquidity_tier": tier,
    }
