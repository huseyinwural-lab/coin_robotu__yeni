from core.strategies.legacy.config import MomentumVolumeBreakoutConfig
from core.strategies.legacy.indicator_utils import clip, momentum_pct, rolling_mean, zscore


class MomentumVolumeBreakoutV3:
    strategy_type = "momentum_volume_breakout_v3"

    def __init__(self, config: MomentumVolumeBreakoutConfig | None = None):
        self.config = config or MomentumVolumeBreakoutConfig()

    def _breakout_levels(self, highs: list[float], lows: list[float]) -> tuple[float, float]:
        lookback = max(5, self.config.breakout_lookback)
        long_level = max(highs[-lookback - 1 : -1]) if len(highs) > lookback else max(highs[:-1])
        short_level = min(lows[-lookback - 1 : -1]) if len(lows) > lookback else min(lows[:-1])
        return long_level, short_level

    def generate_signal(self, market_state: dict) -> dict:
        closes = [float(x) for x in market_state.get("closes", []) if float(x) > 0]
        highs = [float(x) for x in market_state.get("highs", []) if float(x) > 0]
        lows = [float(x) for x in market_state.get("lows", []) if float(x) > 0]
        volumes = [float(x) for x in market_state.get("volumes", []) if float(x) >= 0]

        if min(len(closes), len(highs), len(lows), len(volumes)) < 25:
            return {
                "signal": "NONE",
                "confidence": 0.0,
                "context": {"strategy_type": self.strategy_type, "reason": "INSUFFICIENT_DATA"},
            }

        latest_price = float(closes[-1])
        atr_ratio = max(float(market_state.get("atr", 0.0)), 1e-4)
        current_range = max(highs[-1] - lows[-1], 0.0)
        atr_normalized_range = current_range / max(latest_price * atr_ratio, 1e-8)

        price_momentum = momentum_pct(closes, lookback=8)
        volume_fast = rolling_mean(volumes, 3)
        volume_slow = rolling_mean(volumes, 21)
        volume_momentum = (volume_fast / volume_slow) - 1 if volume_slow > 0 else 0.0
        volume_anomaly = zscore(volumes[-1], volumes[-21:])

        long_level, short_level = self._breakout_levels(highs, lows)
        close_now = closes[-1]
        breakout_long = close_now > (long_level * (1 + self.config.breakout_buffer))
        breakout_short = close_now < (short_level * (1 - self.config.breakout_buffer))

        long_ready = (
            breakout_long
            and price_momentum >= self.config.momentum_threshold
            and volume_momentum >= self.config.volume_momentum_threshold
            and volume_anomaly >= self.config.volume_anomaly_z_threshold
            and atr_normalized_range >= self.config.atr_range_threshold
        )
        short_ready = (
            breakout_short
            and price_momentum <= -self.config.momentum_threshold
            and volume_momentum >= self.config.volume_momentum_threshold
            and volume_anomaly >= self.config.volume_anomaly_z_threshold
            and atr_normalized_range >= self.config.atr_range_threshold
        )

        signal = "NONE"
        momentum_abs = abs(price_momentum)
        confidence = 0.0
        if long_ready and not short_ready:
            signal = "LONG"
        elif short_ready and not long_ready:
            signal = "SHORT"
        elif long_ready and short_ready:
            signal = "LONG" if price_momentum >= 0 else "SHORT"

        if signal in {"LONG", "SHORT"}:
            confidence = clip(
                0.42
                + min(momentum_abs / max(self.config.momentum_threshold, 1e-4), 2.0) * 0.18
                + min(volume_momentum / max(self.config.volume_momentum_threshold, 1e-4), 2.0) * 0.15
                + min(volume_anomaly / max(self.config.volume_anomaly_z_threshold, 0.1), 2.0) * 0.15
                + min(atr_normalized_range / max(self.config.atr_range_threshold, 0.1), 2.0) * 0.1,
                0.0,
                0.98,
            )

        return {
            "signal": signal,
            "confidence": round(confidence, 4),
            "context": {
                "strategy_type": self.strategy_type,
                "reason": "MOMENTUM_VOLUME_BREAKOUT" if signal in {"LONG", "SHORT"} else "BREAKOUT_FILTERED",
                "price_momentum": round(price_momentum, 6),
                "volume_momentum": round(volume_momentum, 6),
                "volume_anomaly_z": round(volume_anomaly, 4),
                "atr_normalized_range": round(atr_normalized_range, 6),
                "long_short_symmetric": True,
                "breakout_levels": {"long_level": round(long_level, 6), "short_level": round(short_level, 6)},
            },
        }
