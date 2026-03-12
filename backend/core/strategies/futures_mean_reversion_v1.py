from core.strategies.components.deviation_detector import detect_deviation_signal
from core.strategies.components.funding_alignment import evaluate_funding_alignment
from core.strategies.components.range_detector import detect_range_state


class FuturesMeanReversionV1:
    strategy_type = "mean_reversion_v1"

    def generate_signal(self, market_state: dict) -> dict:
        range_result = detect_range_state(
            atr=float(market_state.get("atr", 0.0)),
            volatility_compression=float(market_state.get("volatility_compression", 0.0)),
            range_persistence=float(market_state.get("range_persistence", 0.0)),
        )
        deviation = detect_deviation_signal(
            latest_price=float(market_state.get("latest_price", 0.0)),
            range_mean=float(market_state.get("range_mean", market_state.get("latest_price", 0.0))),
            atr=float(market_state.get("atr", 0.0)),
            range_state=range_result["range_state"],
        )
        funding = evaluate_funding_alignment(
            funding_rate=float((market_state.get("funding_bias") or {}).get("funding_rate", 0.0)),
            funding_bias_direction=str((market_state.get("funding_bias") or {}).get("bias_direction", "NEUTRAL")),
        )

        side = deviation["mean_reversion_signal"]
        signal = "NONE"
        confidence = 0.0
        if side in {"LONG", "SHORT"} and funding["funding_alignment_bias"] in {side, "NEUTRAL"}:
            signal = side
            confidence = min(0.95, deviation["confidence"] * 0.7 + range_result["range_confidence"] * 0.2 + funding["funding_alignment_confidence"] * 0.1)

        return {
            "signal": signal,
            "confidence": round(confidence, 4),
            "context": {
                "strategy_type": self.strategy_type,
                "range_state": range_result["range_state"],
                "range_confidence": range_result["range_confidence"],
                "normalized_distance": deviation["normalized_distance"],
                "funding_alignment_bias": funding["funding_alignment_bias"],
            },
        }
