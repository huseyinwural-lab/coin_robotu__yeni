import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.pipeline.cache_store import set_json
from services.pipeline.spot_dynamic_score_engine import run_dynamic_selection_cycle


class FakeCache:
    def __init__(self):
        self.store = {}

    def set(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


def _build_candles(start: float, drift: float, count: int = 260) -> list[dict]:
    candles: list[dict] = []
    price = start
    for idx in range(count):
        wobble = drift * 0.25 if idx % 5 == 0 else 0.0
        open_price = max(price, 0.1)
        close_price = max(open_price + drift - wobble, 0.1)
        high = max(open_price, close_price) * 1.003
        low = min(open_price, close_price) * 0.997
        candles.append(
            {
                "open": round(open_price, 6),
                "high": round(high, 6),
                "low": round(low, 6),
                "close": round(close_price, 6),
                "volume": 1_200_000 + (idx * 750),
                "end": idx,
            }
        )
        price = close_price
    return candles


def test_dynamic_scanner_runs_without_btc_symbol_dependency():
    cache = FakeCache()
    set_json(cache, "market_data_store:ETHUSDT:15m", _build_candles(start=1000, drift=1.35))
    set_json(cache, "market_data_store:SOLUSDT:15m", _build_candles(start=90, drift=0.18))

    payload = run_dynamic_selection_cycle(
        cache,
        symbols=["ETHUSDT", "SOLUSDT"],
        open_symbols=set(),
        available_slots=2,
        params={
            "min_adjusted_score": 0,
            "active_strategies": [
                "spot_pullback_v1",
                "spot_range_reversion_v1",
                "spot_volatility_breakout_v1",
            ],
        },
    )

    assert payload["symbol_count"] == 2
    assert payload["market_regime"] in {"TRENDING", "RANGING", "VOLATILE"}
    assert payload["market_bias_regime"] in {"supportive", "neutral", "hostile"}
    assert payload["btc_regime"] == payload["market_bias_regime"]
    assert payload["metrics"]["signals_rejected_market_bias"] == 0
    assert payload["metrics"]["signals_rejected_market_stress"] == 0

    for item in payload["ranked"]:
        reason_codes = item.get("reason_codes", [])
        assert "btc_regime_hostile" not in reason_codes
        assert "freeze_guard_active" not in reason_codes


def test_dynamic_scanner_keeps_legacy_alias_fields_without_btc_gate_logic():
    cache = FakeCache()
    set_json(cache, "market_data_store:ADAUSDT:15m", _build_candles(start=0.5, drift=0.0012))

    payload = run_dynamic_selection_cycle(
        cache,
        symbols=["ADAUSDT"],
        open_symbols=set(),
        available_slots=1,
        params={"min_adjusted_score": 0, "active_strategies": ["spot_pullback_v1"]},
    )

    assert "risk_guard" in payload
    assert payload["risk_guard"]["active"] is False
    assert "freeze_guard" in payload
    assert payload["freeze_guard"]["active"] is False
    assert payload["metrics"]["signals_rejected_btc_regime"] == payload["metrics"]["signals_rejected_market_bias"]
    assert payload["metrics"]["signals_rejected_freeze_guard"] == payload["metrics"]["signals_rejected_market_stress"]