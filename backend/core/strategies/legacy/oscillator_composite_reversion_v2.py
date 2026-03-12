from core.strategies.legacy.config import OscillatorCompositeConfig
from core.strategies.legacy.indicator_utils import cci, clip, momentum_pct, normalize_01, rsi, stochastic_k, williams_r


class OscillatorCompositeReversionV2:
    strategy_type = "oscillator_composite_reversion_v2"

    def __init__(self, config: OscillatorCompositeConfig | None = None):
        self.config = config or OscillatorCompositeConfig()

    def generate_signal(self, market_state: dict) -> dict:
        closes = [float(x) for x in market_state.get("closes", []) if float(x) > 0]
        highs = [float(x) for x in market_state.get("highs", []) if float(x) > 0]
        lows = [float(x) for x in market_state.get("lows", []) if float(x) > 0]
        if min(len(closes), len(highs), len(lows)) < 35:
            return {
                "signal": "NONE",
                "confidence": 0.0,
                "context": {"strategy_type": self.strategy_type, "reason": "INSUFFICIENT_DATA"},
            }

        controlled_entry_mode = bool(market_state.get("controlled_entry_mode", False))
        if not controlled_entry_mode:
            return {
                "signal": "NONE",
                "confidence": 0.0,
                "context": {
                    "strategy_type": self.strategy_type,
                    "reason": "CONTROLLED_ENTRY_REQUIRED",
                    "controlled_entry_mode": False,
                },
            }

        volatility_regime = str(market_state.get("volatility_regime", "RANGING")).upper()
        compression = float(market_state.get("volatility_compression", 0.0))
        regime_ok = volatility_regime in {"RANGING", "NORMAL"} and compression >= self.config.min_regime_compression

        rsi_raw = rsi(closes, period=14)
        stoch_raw = stochastic_k(closes, highs, lows, period=14)
        cci_raw = cci(closes, highs, lows, period=14)
        willr_raw = williams_r(closes, highs, lows, period=14)
        mom_raw = momentum_pct(closes, lookback=10) * 100

        normalized = {
            "rsi": normalize_01(rsi_raw, 0, 100),
            "stochastic": normalize_01(stoch_raw, 0, 100),
            "cci": normalize_01(cci_raw, -200, 200),
            "williams_r": normalize_01(willr_raw, -100, 0),
            "momentum": normalize_01(mom_raw, -5, 5),
        }
        composite = sum(normalized.values()) / len(normalized)

        signal = "NONE"
        if regime_ok and composite <= self.config.long_threshold:
            signal = "LONG"
        elif regime_ok and composite >= self.config.short_threshold:
            signal = "SHORT"

        confidence = 0.0
        if signal == "LONG":
            confidence = clip(0.35 + (self.config.long_threshold - composite) * 1.1, 0.0, 0.94)
        elif signal == "SHORT":
            confidence = clip(0.35 + (composite - self.config.short_threshold) * 1.1, 0.0, 0.94)

        return {
            "signal": signal,
            "confidence": round(confidence, 4),
            "context": {
                "strategy_type": self.strategy_type,
                "reason": "OSCILLATOR_COMPOSITE_REVERSION" if signal in {"LONG", "SHORT"} else "REVERSION_FILTERED",
                "controlled_entry_mode": True,
                "regime_ok": regime_ok,
                "volatility_regime": volatility_regime,
                "volatility_compression": round(compression, 6),
                "composite_score": round(composite, 6),
                "normalized_oscillators": {key: round(value, 6) for key, value in normalized.items()},
                "thresholds": {
                    "long_threshold": self.config.long_threshold,
                    "short_threshold": self.config.short_threshold,
                },
            },
        }
