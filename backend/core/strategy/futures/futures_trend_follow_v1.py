from core.strategy.futures.strategy_contract import FuturesStrategy, StrategySignal


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class FuturesTrendFollowV1(FuturesStrategy):
    def __init__(self, *, trend_threshold: float = 0.0025):
        self.trend_threshold = trend_threshold

    def generate_signal(self, market_state: dict) -> StrategySignal:
        symbol = str(market_state.get("symbol") or "UNKNOWN").upper()
        trend_strength = float(market_state.get("trend_strength") or 0.0)
        trend_direction = str(market_state.get("trend_direction") or "NONE").upper()
        volatility_regime = str(market_state.get("volatility_regime") or "RANGING").upper()
        spread_state = str(market_state.get("spread_state") or "NORMAL").upper()
        funding_alignment = bool(market_state.get("funding_alignment", False))

        if spread_state == "SHOCK":
            return StrategySignal(symbol=symbol, side="NONE", confidence=0.0, regime=volatility_regime, reason="SPREAD_SHOCK")
        if volatility_regime != "TRENDING":
            return StrategySignal(symbol=symbol, side="NONE", confidence=0.0, regime=volatility_regime, reason="REGIME_NOT_TRENDING")
        if trend_strength <= self.trend_threshold:
            return StrategySignal(symbol=symbol, side="NONE", confidence=0.0, regime=volatility_regime, reason="TREND_STRENGTH_BELOW_THRESHOLD")
        if trend_direction not in {"LONG", "SHORT"}:
            return StrategySignal(symbol=symbol, side="NONE", confidence=0.0, regime=volatility_regime, reason="TREND_DIRECTION_UNCLEAR")
        if not funding_alignment:
            return StrategySignal(symbol=symbol, side="NONE", confidence=0.0, regime=volatility_regime, reason="FUNDING_BIAS_MISALIGNED")

        confidence = _clamp(0.45 + trend_strength * 40)
        return StrategySignal(
            symbol=symbol,
            side=trend_direction,
            confidence=round(confidence, 4),
            regime=volatility_regime,
            reason="TREND_FUNDING_ALIGNED",
        )
