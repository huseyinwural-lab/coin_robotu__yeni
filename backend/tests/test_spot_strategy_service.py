import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.pipeline.spot_strategy_service import evaluate_spot_pullback_candidate


def _build_bullish_pullback_candles() -> list[dict]:
    candles: list[dict] = []
    price = 100.0
    for _ in range(220):
        open_price = price
        price = price * 1.002
        close_price = price
        candles.append(
            {
                "open": open_price,
                "high": close_price * 1.006,
                "low": open_price * 0.994,
                "close": close_price,
                "volume": 6000,
            }
        )

    for _ in range(13):
        open_price = price
        price = price * 0.996
        close_price = price
        candles.append(
            {
                "open": open_price,
                "high": open_price * 1.007,
                "low": close_price * 0.992,
                "close": close_price,
                "volume": 8000,
            }
        )

    final_open = price * 0.999
    final_close = price * 1.0003
    candles.append(
        {
            "open": final_open,
            "high": final_close * 1.008,
            "low": final_open * 0.992,
            "close": final_close,
            "volume": 22000,
        }
    )
    return candles


def _build_supportive_btc_candles() -> list[dict]:
    candles: list[dict] = []
    price = 30000.0
    for _ in range(260):
        open_price = price
        price = price * 1.001
        close_price = price
        candles.append(
            {
                "open": open_price,
                "high": close_price * 1.004,
                "low": open_price * 0.996,
                "close": close_price,
                "volume": 15000,
            }
        )
    return candles


def test_spot_pullback_candidate_can_generate_long_signal():
    candidate = evaluate_spot_pullback_candidate(
        symbol="TESTUSDT",
        candles=_build_bullish_pullback_candles(),
        btc_candles=_build_supportive_btc_candles(),
    )

    assert candidate["signal"] == "long"
    assert candidate["direction"] == "long"
    assert candidate["reason_codes"] == ["spot_pullback_ready"]
    assert candidate["take_profit"] > candidate["entry"] > candidate["stop"]