from core.simulation.liquidity_impact_model import estimate_liquidity_impact
from core.simulation.slippage_simulator import simulate_expected_slippage


def run_capital_scaling_simulation(
    *,
    trades: list[dict],
    capital_levels: list[float],
    market_depth: float,
    spread_bps: float,
    liquidity_tier: str,
) -> dict:
    reports: list[dict] = []
    base_capital = min(capital_levels) if capital_levels else 1_000_000.0

    for capital in sorted(capital_levels):
        scale_factor = capital / max(base_capital, 1.0)
        pnl_total = 0.0
        slippage_total = 0.0
        execution_quality_total = 0.0
        liquidity_stress_total = 0.0

        for trade in trades:
            base_order_size = float(trade.get("order_size") or 0.0)
            scaled_order_size = base_order_size * scale_factor

            impact = estimate_liquidity_impact(
                order_size=scaled_order_size,
                market_depth=market_depth,
                spread_width_bps=spread_bps,
                liquidity_tier=liquidity_tier,
            )
            slippage = simulate_expected_slippage(
                order_size=scaled_order_size,
                volatility_regime=str(trade.get("volatility_regime") or "NORMAL"),
                spread_bps=spread_bps,
                liquidity_score=max(0.0, 1 - impact["impact_ratio"]),
                impact_score=impact["impact_score"],
            )

            expected_pnl = float(trade.get("expected_pnl") or 0.0) * scale_factor
            pnl_total += expected_pnl - slippage["expected_slippage_bps"] * 0.0001 * scaled_order_size
            slippage_total += slippage["expected_slippage_bps"]
            execution_quality_total += max(0.0, 1 - impact["impact_score"] / 100)
            liquidity_stress_total += min(1.0, impact["impact_ratio"])

        trade_count = max(len(trades), 1)
        reports.append(
            {
                "capital_level": capital,
                "pnl": round(pnl_total, 4),
                "slippage": round(slippage_total / trade_count, 4),
                "execution_quality": round(execution_quality_total / trade_count, 4),
                "liquidity_stress": round(liquidity_stress_total / trade_count, 4),
            }
        )

    return {
        "capital_levels": sorted(capital_levels),
        "scaling_performance_report": reports,
    }
