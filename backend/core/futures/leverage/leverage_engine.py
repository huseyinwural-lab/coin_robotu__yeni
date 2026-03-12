from core.futures.leverage.confidence_scaler import ConfidenceScaler
from core.futures.leverage.funding_scaler import FundingScaler
from core.futures.leverage.leverage_decision_model import LeverageDecision
from core.futures.leverage.liquidation_scaler import LiquidationScaler
from core.futures.leverage.microstructure_scaler import MicrostructureScaler
from core.futures.leverage.portfolio_leverage_guard import PortfolioLeverageGuard


class LeverageEngine:
    def __init__(self):
        self.confidence_scaler = ConfidenceScaler()
        self.microstructure_scaler = MicrostructureScaler()
        self.liquidation_scaler = LiquidationScaler()
        self.funding_scaler = FundingScaler()
        self.portfolio_guard = PortfolioLeverageGuard()

    def evaluate(
        self,
        *,
        symbol: str,
        strategy: str,
        side: str,
        base_leverage: float,
        confidence: float,
        microstructure_risk_score: float,
        execution_suitability: dict,
        spread_state: str,
        depth_state: str,
        distance_to_liquidation: float,
        funding_bias: dict,
        portfolio_leverage: float,
    ) -> dict:
        base = max(1.0, min(5.0, float(base_leverage or 1.0)))

        confidence_result = self.confidence_scaler.evaluate(confidence)
        microstructure_result = self.microstructure_scaler.evaluate(
            microstructure_risk_score=microstructure_risk_score,
            execution_suitability=execution_suitability,
            spread_state=spread_state,
            depth_state=depth_state,
        )
        liquidation_result = self.liquidation_scaler.evaluate(distance_to_liquidation)
        funding_result = self.funding_scaler.evaluate(side=side, funding_bias=funding_bias)

        preliminary = (
            base
            * confidence_result["confidence_leverage_multiplier"]
            * microstructure_result["liquidity_adjusted_leverage"]
            * liquidation_result["liquidation_adjustment"]
            * funding_result["funding_adjustment_factor"]
        )

        portfolio_guard = self.portfolio_guard.evaluate(
            portfolio_leverage=portfolio_leverage,
            proposed_leverage=preliminary,
        )
        final_leverage = min(max(1.0, preliminary * portfolio_guard["portfolio_adjustment_factor"]), 5.0)

        position_size_ratio = min(
            1.0,
            microstructure_result["size_clamp_ratio"] * liquidation_result["liquidation_size_clamp_ratio"],
        )
        if final_leverage <= 1.2:
            position_size_ratio = min(position_size_ratio, 0.65)

        decision = LeverageDecision(
            symbol=symbol,
            strategy=strategy,
            side=side,
            base_leverage=round(base, 4),
            confidence_adjustment=confidence_result["confidence_leverage_multiplier"],
            microstructure_adjustment=microstructure_result["liquidity_adjusted_leverage"],
            liquidation_adjustment=liquidation_result["liquidation_adjustment"],
            funding_adjustment=funding_result["funding_adjustment_factor"],
            final_leverage=round(final_leverage, 4),
            position_size_ratio=round(position_size_ratio, 4),
        )
        return {
            "decision": decision.to_dict(),
            "decision_trace_extension": {
                "leverage_decision": "dynamic",
                "confidence_multiplier": confidence_result["confidence_leverage_multiplier"],
                "microstructure_multiplier": microstructure_result["liquidity_adjusted_leverage"],
                "liquidation_multiplier": liquidation_result["liquidation_adjustment"],
                "funding_multiplier": funding_result["funding_adjustment_factor"],
                "portfolio_multiplier": portfolio_guard["portfolio_adjustment_factor"],
                "final_leverage": round(final_leverage, 4),
                "position_size_ratio": round(position_size_ratio, 4),
            },
            "inputs": {
                "confidence": confidence_result["confidence"],
                "microstructure_risk_score": round(float(microstructure_risk_score or 0.0), 4),
                "distance_to_liquidation": liquidation_result["distance_to_liquidation"],
                "funding_bias": funding_result["funding_direction"],
                "funding_pressure": funding_result["funding_pressure"],
                "portfolio_leverage": round(float(portfolio_leverage or 0.0), 4),
                "spread_state": spread_state,
                "depth_state": depth_state,
            },
        }
