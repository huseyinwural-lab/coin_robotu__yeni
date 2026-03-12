from core.strategies.legacy.config import VolatilityBreakoutConfig
from core.strategies.legacy.indicator_utils import clip, rolling_mean, rolling_std


class VolatilityBreakoutV2:
    strategy_type = "volatility_breakout_v2"

    def __init__(self, config: VolatilityBreakoutConfig | None = None):
        self.config = config or VolatilityBreakoutConfig()

    def _bollinger(self, closes: list[float]) -> tuple[float, float, float]:
        mean = rolling_mean(closes, self.config.bb_period)
        std = rolling_std(closes, self.config.bb_period)
        upper = mean + self.config.bb_std * std
        lower = mean - self.config.bb_std * std
        return lower, mean, upper

    def _close_confirm(self, closes: list[float], side: str, level: float) -> bool:
        bars = max(1, self.config.close_confirm_bars)
        if len(closes) < bars:
            return False
        window = closes[-bars:]
        if side == "LONG":
            return all(close > level * (1 + self.config.breakout_buffer) for close in window)
        return all(close < level * (1 - self.config.breakout_buffer) for close in window)

    def generate_signal(self, market_state: dict) -> dict:
        closes = [float(x) for x in market_state.get("closes", []) if float(x) > 0]
        highs = [float(x) for x in market_state.get("highs", []) if float(x) > 0]
        lows = [float(x) for x in market_state.get("lows", []) if float(x) > 0]
        opens = [float(x) for x in market_state.get("opens", []) if float(x) > 0]
        if len(closes) < max(self.config.bb_period + 1, 24):
            return {
                "signal": "NONE",
                "confidence": 0.0,
                "context": {"strategy_type": self.strategy_type, "reason": "INSUFFICIENT_DATA"},
            }

        lower, middle, upper = self._bollinger(closes)
        spread_bps = float(market_state.get("spread_bps", 0.0))
        volatility = float(market_state.get("atr", 0.0))
        volatility_regime = str(market_state.get("volatility_regime", "RANGING")).upper()
        regime_ok = volatility_regime in {"TRENDING", "VOLATILE"}
        liquidity_ok = spread_bps <= self.config.max_spread_bps
        volatility_ok = volatility >= self.config.min_volatility

        candle_high = highs[-1] if highs else closes[-1]
        candle_low = lows[-1] if lows else closes[-1]
        candle_open = opens[-1] if opens else closes[-2]
        candle_body = abs(closes[-1] - candle_open)
        candle_range = max(candle_high - candle_low, 1e-8)
        body_ratio = candle_body / candle_range
        false_breakout_filter_ok = body_ratio >= self.config.min_body_ratio

        long_ready = self._close_confirm(closes, "LONG", upper)
        short_ready = self._close_confirm(closes, "SHORT", lower)

        signal = "NONE"
        if long_ready and regime_ok and liquidity_ok and volatility_ok and false_breakout_filter_ok:
            signal = "LONG"
        elif short_ready and regime_ok and liquidity_ok and volatility_ok and false_breakout_filter_ok:
            signal = "SHORT"

        band_width = (upper - lower) / max(abs(middle), 1e-8)
        confidence = 0.0
        if signal in {"LONG", "SHORT"}:
            confidence = clip(0.38 + min(volatility / max(self.config.min_volatility, 1e-6), 3.0) * 0.2 + min(band_width / 0.02, 3.0) * 0.2 + min(body_ratio / max(self.config.min_body_ratio, 1e-6), 3.0) * 0.18, 0.0, 0.97)

        return {
            "signal": signal,
            "confidence": round(confidence, 4),
            "context": {
                "strategy_type": self.strategy_type,
                "reason": "BOLLINGER_BREAKOUT_CONFIRMED" if signal in {"LONG", "SHORT"} else "BREAKOUT_FILTERED",
                "bollinger": {"lower": round(lower, 6), "middle": round(middle, 6), "upper": round(upper, 6)},
                "close_confirmation_bars": self.config.close_confirm_bars,
                "liquidity_ok": liquidity_ok,
                "regime_ok": regime_ok,
                "false_breakout_filter_ok": false_breakout_filter_ok,
                "volatility_regime": volatility_regime,
                "body_ratio": round(body_ratio, 4),
            },
        }
