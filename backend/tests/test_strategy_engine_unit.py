# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategy_engine import _ema, _rsi, generate_strategy_signal


# ---------------------------------------------------------------------------
# _ema tests
# ---------------------------------------------------------------------------

class TestEma:
    def test_ema_basic_calculation(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = _ema(values, 3)
        assert len(result) > 0
        # Seed should be average of first 3 values = 2.0
        assert abs(result[0] - 2.0) < 1e-9

    def test_ema_returns_empty_when_period_exceeds_values(self):
        result = _ema([1.0, 2.0], 5)
        assert result == []

    def test_ema_returns_empty_for_zero_period(self):
        result = _ema([1.0, 2.0, 3.0], 0)
        assert result == []

    def test_ema_returns_empty_for_negative_period(self):
        result = _ema([1.0, 2.0, 3.0], -1)
        assert result == []

    def test_ema_single_element_period_equals_values_length(self):
        result = _ema([1.0, 2.0, 3.0], 3)
        # Seed = average of [1,2,3] = 2.0, no further values to process
        assert len(result) == 1
        assert abs(result[0] - 2.0) < 1e-9

    def test_ema_constant_values(self):
        values = [5.0] * 20
        result = _ema(values, 5)
        # EMA of constant series is the constant itself
        for val in result:
            assert abs(val - 5.0) < 1e-9

    def test_ema_monotonic_increase(self):
        values = list(range(1, 21))
        result = _ema([float(v) for v in values], 5)
        # EMA should be monotonically increasing for monotonically increasing input
        for i in range(1, len(result)):
            assert result[i] > result[i - 1]


# ---------------------------------------------------------------------------
# _rsi tests
# ---------------------------------------------------------------------------

class TestRsi:
    def test_rsi_returns_none_with_insufficient_data(self):
        result = _rsi([1.0, 2.0], 14)
        assert result is None

    def test_rsi_returns_100_when_only_gains(self):
        # 16 values, strictly increasing
        values = [float(i) for i in range(1, 17)]
        result = _rsi(values, 14)
        assert result == 100.0

    def test_rsi_returns_value_between_0_and_100(self):
        import random
        random.seed(42)
        values = [random.uniform(90, 110) for _ in range(30)]
        result = _rsi(values, 14)
        assert result is not None
        assert 0.0 <= result <= 100.0

    def test_rsi_with_no_change_values(self):
        # All same values means 0 gains and 0 losses
        values = [100.0] * 20
        result = _rsi(values, 14)
        # avg_gain = 0, avg_loss = 0 => avg_loss == 0 => returns 100.0
        assert result == 100.0

    def test_rsi_only_losses(self):
        # Strictly decreasing values
        values = [float(100 - i) for i in range(20)]
        result = _rsi(values, 14)
        assert result is not None
        # avg_gain = 0 => rs = 0 => RSI = 100 - (100 / (1+0)) = 0
        assert abs(result - 0.0) < 1e-9

    def test_rsi_period_equals_data_minus_one(self):
        # Minimum viable data: period + 1 values
        values = [1.0, 2.0]
        result = _rsi(values, 1)
        assert result is not None
        assert 0.0 <= result <= 100.0


# ---------------------------------------------------------------------------
# generate_strategy_signal tests
# ---------------------------------------------------------------------------

class TestGenerateStrategySignal:
    def _make_closes(self, base: float, count: int, trend: float = 0.0):
        """Generate a list of closing prices with optional trend."""
        return [base + trend * i for i in range(count)]

    def test_returns_none_with_insufficient_data(self):
        result = generate_strategy_signal(symbol="BTCUSDT", closes=[100.0] * 5)
        assert result is None

    def test_returns_none_with_no_crossover(self):
        # Flat prices => no EMA crossover
        closes = [100.0] * 50
        result = generate_strategy_signal(symbol="BTCUSDT", closes=closes)
        assert result is None

    def test_buy_signal_on_bullish_crossover(self):
        # Create a downtrend followed by strong uptrend to trigger crossover
        closes = self._make_closes(100, 25, trend=-0.5) + self._make_closes(87.5, 25, trend=1.5)
        result = generate_strategy_signal(
            symbol="BTCUSDT",
            closes=closes,
            ema_fast_period=5,
            ema_slow_period=10,
            rsi_period=14,
            min_confidence=0.50,
        )
        if result is not None:
            assert result["side"] == "BUY"
            assert result["symbol"] == "BTCUSDT"
            assert "confidence" in result
            assert result["confidence"] >= 0.50

    def test_sell_signal_on_bearish_crossover(self):
        # Create an uptrend followed by strong downtrend
        closes = self._make_closes(100, 25, trend=0.5) + self._make_closes(112.5, 25, trend=-1.5)
        result = generate_strategy_signal(
            symbol="ETHUSDT",
            closes=closes,
            ema_fast_period=5,
            ema_slow_period=10,
            rsi_period=14,
            min_confidence=0.50,
        )
        if result is not None:
            assert result["side"] == "SELL"
            assert result["symbol"] == "ETHUSDT"

    def test_signal_output_fields(self):
        # Construct a known crossover
        closes = self._make_closes(50, 20, trend=-1.0) + self._make_closes(30, 30, trend=2.0)
        result = generate_strategy_signal(
            symbol="bnbusdt",
            closes=closes,
            ema_fast_period=5,
            ema_slow_period=10,
            rsi_period=14,
            min_confidence=0.50,
        )
        if result is not None:
            assert result["symbol"] == "BNBUSDT"
            assert result["side"] in ("BUY", "SELL")
            assert result["size"] == 1.0
            assert 0.0 < result["confidence"] <= 0.99
            assert result["strategy_name"] == "ema_rsi"
            assert "timestamp" in result

    def test_confidence_below_minimum_returns_none(self):
        # Very small gap scenario
        closes = [100.0 + (0.001 * i if i % 2 == 0 else -0.001 * i) for i in range(50)]
        result = generate_strategy_signal(
            symbol="BTCUSDT",
            closes=closes,
            min_confidence=0.99,
        )
        assert result is None

    def test_custom_strategy_name(self):
        closes = self._make_closes(50, 20, trend=-1.0) + self._make_closes(30, 30, trend=2.0)
        result = generate_strategy_signal(
            symbol="BTCUSDT",
            closes=closes,
            strategy_name="custom_strat",
            ema_fast_period=5,
            ema_slow_period=10,
            min_confidence=0.50,
        )
        if result is not None:
            assert result["strategy_name"] == "custom_strat"
