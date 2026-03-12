import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.portfolio.strategy_registry import build_strategy_registry


def test_strategy_registry_contains_phase56_strategies():
    registry = build_strategy_registry()
    assert set(registry.keys()) == {"trend_follow_v1", "mean_reversion_v1", "breakout_v1"}


def test_strategy_registry_returns_signal_contract_like_payload():
    registry = build_strategy_registry()
    sample_state = {
        "symbol": "BTCUSDT",
        "latest_price": 100,
        "trend_strength": 0.008,
        "trend_direction": "LONG",
        "volatility_regime": "TRENDING",
        "spread_state": "NORMAL",
        "funding_alignment": True,
        "atr": 0.02,
        "atr_baseline": 0.015,
        "volatility_compression": 0.8,
        "range_persistence": 0.7,
        "range_mean": 99,
        "range_high": 101,
        "range_low": 96,
        "volume_spike_ratio": 1.25,
        "microstructure_suitable": True,
        "funding_bias": {"funding_rate": 0.0, "bias_direction": "NEUTRAL"},
    }
    for strategy in registry.values():
        payload = strategy.generate_signal(sample_state)
        assert "signal" in payload
        assert "confidence" in payload
        assert "context" in payload
