import math


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

    linear_ratio = size / depth
    square_root_impact = math.sqrt(max(linear_ratio, 0.0)) * tier_multiplier
    impact_score = min(100.0, max(0.0, square_root_impact * 120 + spread * 0.15))
    performance_degradation_pct = min(100.0, max(0.0, square_root_impact * 35 + spread * 0.08))
    return {
        "impact_ratio": round(linear_ratio, 6),
        "square_root_impact": round(square_root_impact, 6),
        "impact_score": round(impact_score, 2),
        "performance_degradation_pct": round(performance_degradation_pct, 4),
        "liquidity_tier": tier,
    }
