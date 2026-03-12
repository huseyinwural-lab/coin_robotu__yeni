from core.strategies.futures_breakout_v1 import FuturesBreakoutV1
from core.strategies.futures_mean_reversion_v1 import FuturesMeanReversionV1


class FuturesTrendFollowAdapter:
    strategy_type = "trend_follow_v1"

    def generate_signal(self, market_state: dict) -> dict:
        trend_strength = float(market_state.get("trend_strength", 0.0))
        trend_direction = str(market_state.get("trend_direction", "NONE")).upper()
        volatility_regime = str(market_state.get("volatility_regime", "RANGING")).upper()
        spread_state = str(market_state.get("spread_state", "NORMAL")).upper()
        funding_alignment = bool(market_state.get("funding_alignment", False))

        if spread_state == "SHOCK" or volatility_regime != "TRENDING" or trend_strength < 0.0025 or not funding_alignment:
            return {
                "signal": "NONE",
                "confidence": 0.0,
                "context": {
                    "strategy_type": self.strategy_type,
                    "reason": "TREND_FILTERED",
                },
            }

        confidence = min(0.95, 0.44 + trend_strength * 38)
        return {
            "signal": trend_direction if trend_direction in {"LONG", "SHORT"} else "NONE",
            "confidence": round(confidence, 4),
            "context": {
                "strategy_type": self.strategy_type,
                "trend_strength": round(trend_strength, 6),
                "regime": volatility_regime,
            },
        }


def build_strategy_registry() -> dict:
    return {
        "trend_follow_v1": FuturesTrendFollowAdapter(),
        "mean_reversion_v1": FuturesMeanReversionV1(),
        "breakout_v1": FuturesBreakoutV1(),
    }
