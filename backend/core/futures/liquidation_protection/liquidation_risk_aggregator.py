from dataclasses import asdict, dataclass


RISK_LEVEL_SAFE = "SAFE"
RISK_LEVEL_WARNING = "WARNING"
RISK_LEVEL_CRITICAL = "CRITICAL"
RISK_LEVEL_EMERGENCY = "EMERGENCY"


@dataclass
class PositionRiskResult:
    position_risk_score: float
    risk_level: str
    dominant_risk_factor: str


@dataclass
class PortfolioRiskResult:
    positions: list[dict]
    position_risk_score: float
    portfolio_risk_score: float
    risk_level: str
    dominant_risk_factor: str


class LiquidationRiskAggregator:
    def evaluate_position(self, position: dict) -> PositionRiskResult:
        distance = float(position.get("distance_to_liquidation", 0.0))
        margin_ratio = float(position.get("margin_ratio", 0.0))
        funding_score = float(position.get("funding_bias_score", 0.0))
        volatility = float(position.get("volatility_proxy", 0.0))
        execution = float(position.get("execution_risk", 0.0))

        distance_risk = max(0.0, min(100.0, 100 - distance * 5))
        margin_risk = max(0.0, min(100.0, 100 - margin_ratio))
        score = min(
            100.0,
            distance_risk * 0.45
            + margin_risk * 0.25
            + volatility * 0.15
            + funding_score * 0.1
            + execution * 0.05,
        )

        if score >= 75:
            level = RISK_LEVEL_EMERGENCY
        elif score >= 55:
            level = RISK_LEVEL_CRITICAL
        elif score >= 35:
            level = RISK_LEVEL_WARNING
        else:
            level = RISK_LEVEL_SAFE

        factor_scores = {
            "LIQUIDATION_DISTANCE": distance_risk,
            "MARGIN_USAGE": margin_risk,
            "VOLATILITY": volatility,
            "FUNDING": funding_score,
            "EXECUTION": execution,
        }
        dominant_factor = max(factor_scores, key=factor_scores.get)

        return PositionRiskResult(
            position_risk_score=round(score, 4),
            risk_level=level,
            dominant_risk_factor=dominant_factor,
        )

    def evaluate_portfolio(self, positions: list[dict]) -> PortfolioRiskResult:
        if not positions:
            return PortfolioRiskResult(
                positions=[],
                position_risk_score=0.0,
                portfolio_risk_score=0.0,
                risk_level=RISK_LEVEL_SAFE,
                dominant_risk_factor="NONE",
            )

        scored: list[dict] = []
        factor_rollup = {
            "LIQUIDATION_DISTANCE": 0.0,
            "MARGIN_USAGE": 0.0,
            "VOLATILITY": 0.0,
            "FUNDING": 0.0,
            "EXECUTION": 0.0,
        }
        for position in positions:
            risk = self.evaluate_position(position)
            scored_position = {
                **position,
                "position_risk_score": risk.position_risk_score,
                "risk_level": risk.risk_level,
                "dominant_risk_factor": risk.dominant_risk_factor,
            }
            scored.append(scored_position)
            factor_rollup[risk.dominant_risk_factor] += risk.position_risk_score

        portfolio_score = sum(item["position_risk_score"] for item in scored) / len(scored)
        if portfolio_score >= 75:
            level = RISK_LEVEL_EMERGENCY
        elif portfolio_score >= 55:
            level = RISK_LEVEL_CRITICAL
        elif portfolio_score >= 35:
            level = RISK_LEVEL_WARNING
        else:
            level = RISK_LEVEL_SAFE

        return PortfolioRiskResult(
            positions=scored,
            position_risk_score=round(max(item["position_risk_score"] for item in scored), 4),
            portfolio_risk_score=round(portfolio_score, 4),
            risk_level=level,
            dominant_risk_factor=max(factor_rollup, key=factor_rollup.get),
        )


def aggregate_liquidation_risk(positions: list[dict]) -> dict:
    aggregator = LiquidationRiskAggregator()
    result = aggregator.evaluate_portfolio(positions)
    return asdict(result)
