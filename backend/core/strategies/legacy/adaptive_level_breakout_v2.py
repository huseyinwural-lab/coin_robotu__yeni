from core.strategies.legacy.config import AdaptiveLevelBreakoutConfig
from core.strategies.legacy.indicator_utils import clip, rolling_mean


WINDOW_MAP = {
    "1m": (90, 60, 12),
    "5m": (150, 90, 14),
    "15m": (210, 120, 18),
    "30m": (250, 150, 24),
    "1h": (320, 180, 30),
    "4h": (420, 240, 36),
}


class AdaptiveLevelBreakoutV2:
    strategy_type = "adaptive_level_breakout_v2"

    def __init__(self, config: AdaptiveLevelBreakoutConfig | None = None):
        self.config = config or AdaptiveLevelBreakoutConfig()

    def _windows(self, timeframe: str) -> tuple[int, int, int]:
        return WINDOW_MAP.get(timeframe.lower(), WINDOW_MAP["15m"])

    def _levels(self, highs: list[float], lows: list[float], long_window: int, short_window: int) -> tuple[float, float]:
        long_level = max(highs[-long_window - 1 : -1]) if len(highs) > long_window else max(highs[:-1])
        short_level = min(lows[-short_window - 1 : -1]) if len(lows) > short_window else min(lows[:-1])
        return long_level, short_level

    def generate_signal(self, market_state: dict) -> dict:
        closes = [float(x) for x in market_state.get("closes", []) if float(x) > 0]
        highs = [float(x) for x in market_state.get("highs", []) if float(x) > 0]
        lows = [float(x) for x in market_state.get("lows", []) if float(x) > 0]
        volumes = [float(x) for x in market_state.get("volumes", []) if float(x) >= 0]
        timeframe = str(market_state.get("timeframe", "15m"))

        if min(len(closes), len(highs), len(lows), len(volumes)) < 40:
            return {
                "signal": "NONE",
                "confidence": 0.0,
                "context": {"strategy_type": self.strategy_type, "reason": "INSUFFICIENT_DATA"},
            }

        long_window, short_window, micro_window = self._windows(timeframe)
        long_level, short_level = self._levels(highs, lows, long_window, short_window)
        close_now = closes[-1]

        volume_ratio = rolling_mean(volumes, 3) / max(rolling_mean(volumes, 20), 1e-8)

        long_break = close_now > long_level * (1 + self.config.breakout_buffer)
        short_break = close_now < short_level * (1 - self.config.breakout_buffer)

        retrace_long = close_now <= long_level * (1 + self.config.breakout_buffer * self.config.false_breakout_retrace_ratio)
        retrace_short = close_now >= short_level * (1 - self.config.breakout_buffer * self.config.false_breakout_retrace_ratio)
        false_breakout_filtered_long = not retrace_long
        false_breakout_filtered_short = not retrace_short

        long_ready = long_break and false_breakout_filtered_long and volume_ratio >= self.config.min_volume_ratio
        short_ready = short_break and false_breakout_filtered_short and volume_ratio >= self.config.min_volume_ratio

        signal = "NONE"
        if long_ready and not short_ready:
            signal = "LONG"
        elif short_ready and not long_ready:
            signal = "SHORT"

        confidence = 0.0
        if signal in {"LONG", "SHORT"}:
            distance = abs((close_now - (long_level if signal == "LONG" else short_level)) / max(close_now, 1e-8))
            confidence = clip(0.36 + min(distance / 0.01, 3.0) * 0.25 + min(volume_ratio, 2.5) * 0.18 + 0.08, 0.0, 0.96)

        sensitivity_tag = {
            "cluster_sensitivity": "HIGH" if timeframe in {"1m", "5m", "15m"} else "MEDIUM",
            "capital_sensitivity": "HIGH" if timeframe in {"1h", "4h"} else "MEDIUM",
        }

        return {
            "signal": signal,
            "confidence": round(confidence, 4),
            "context": {
                "strategy_type": self.strategy_type,
                "reason": "ADAPTIVE_LEVEL_BREAKOUT" if signal in {"LONG", "SHORT"} else "BREAKOUT_FILTERED",
                "timeframe": timeframe,
                "adaptive_windows": {
                    "long_window": long_window,
                    "short_window": short_window,
                    "micro_window": micro_window,
                },
                "levels": {
                    "hhv_long_level": round(long_level, 6),
                    "llv_short_level": round(short_level, 6),
                },
                "false_breakout_filter": {
                    "long": false_breakout_filtered_long,
                    "short": false_breakout_filtered_short,
                },
                "volume_ratio": round(volume_ratio, 6),
                **sensitivity_tag,
            },
        }
