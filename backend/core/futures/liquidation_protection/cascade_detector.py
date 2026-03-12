from dataclasses import asdict, dataclass


CASCADE_NONE = "NONE"
CASCADE_WARNING = "CASCADE_WARNING"
CASCADE_CONFIRMED = "CASCADE_CONFIRMED"


@dataclass
class CascadeResult:
    cascade_state: str
    cascade_score: int
    risk_symbols: list[str]


class CascadeDetector:
    def evaluate(self, portfolio_snapshot: dict) -> CascadeResult:
        positions = portfolio_snapshot.get("positions", [])
        positions_at_risk = int(portfolio_snapshot.get("positions_at_risk") or 0)
        volatility_spike = bool(portfolio_snapshot.get("volatility_spike"))
        spread_widening = bool(portfolio_snapshot.get("spread_widening"))
        reject_rate = float(portfolio_snapshot.get("reject_rate") or 0.0)
        slippage_spike = bool(portfolio_snapshot.get("slippage_spike"))
        correlated_cluster_risk = bool(portfolio_snapshot.get("correlated_cluster_risk"))

        score = 0
        if positions_at_risk >= 2:
            score += 30
        if volatility_spike:
            score += 20
        if spread_widening:
            score += 15
        if reject_rate >= 0.25:
            score += 15
        if slippage_spike:
            score += 10
        if correlated_cluster_risk:
            score += 10

        if score >= 70:
            state = CASCADE_CONFIRMED
        elif score >= 40:
            state = CASCADE_WARNING
        else:
            state = CASCADE_NONE

        risk_symbols = [
            item.get("symbol")
            for item in positions
            if item.get("symbol") and float(item.get("distance_to_liquidation") or 100) <= 15
        ]
        return CascadeResult(cascade_state=state, cascade_score=score, risk_symbols=risk_symbols)


def detect_liquidation_cascade(
    *,
    positions_at_risk: int,
    volatility_spike: bool,
    spread_widening: bool,
    reject_rate: float,
    slippage_spike: bool,
    correlated_cluster_risk: bool,
) -> dict:
    detector = CascadeDetector()
    result = detector.evaluate(
        {
            "positions_at_risk": positions_at_risk,
            "volatility_spike": volatility_spike,
            "spread_widening": spread_widening,
            "reject_rate": reject_rate,
            "slippage_spike": slippage_spike,
            "correlated_cluster_risk": correlated_cluster_risk,
            "positions": [],
        }
    )
    payload = asdict(result)
    payload["cascade_status"] = payload["cascade_state"]
    return payload
