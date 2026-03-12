from core.strategies.components.breakout_confirmation import confirm_breakout
from core.strategies.components.volatility_expansion import detect_volatility_expansion


class FuturesBreakoutV1:
    strategy_type = "breakout_v1"

    def generate_signal(self, market_state: dict) -> dict:
        expansion = detect_volatility_expansion(
            atr_current=float(market_state.get("atr", 0.0)),
            atr_baseline=float(market_state.get("atr_baseline", market_state.get("atr", 0.0))),
            compression_state=float(market_state.get("volatility_compression", 0.0)),
        )
        breakout = confirm_breakout(
            latest_price=float(market_state.get("latest_price", 0.0)),
            range_high=float(market_state.get("range_high", 0.0)),
            range_low=float(market_state.get("range_low", 0.0)),
            volume_spike_ratio=float(market_state.get("volume_spike_ratio", 0.0)),
            microstructure_suitable=bool(market_state.get("microstructure_suitable", True)),
        )

        signal = "NONE"
        confidence = 0.0
        if breakout["confirmed"] and expansion["expansion_state"] in {"EXPANSION_BUILDING", "EXPANSION_CONFIRMED"}:
            signal = breakout["breakout_side"]
            confidence = min(0.96, breakout["confidence"] * 0.65 + expansion["expansion_score"] * 0.35)

        return {
            "signal": signal,
            "confidence": round(confidence, 4),
            "context": {
                "strategy_type": self.strategy_type,
                "expansion_state": expansion["expansion_state"],
                "expansion_score": expansion["expansion_score"],
                "volume_confirmation": breakout["volume_confirmation"],
            },
        }
