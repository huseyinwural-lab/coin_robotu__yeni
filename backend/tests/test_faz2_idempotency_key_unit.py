# ruff: noqa: E402
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.idempotency_service import build_execution_idempotency_key


ARTIFACT_PATH = Path("/app/artifacts/faz2_idempotency_key_examples.json")


def _base_payload() -> dict:
    return {
        "source_type": "manual",
        "source_ref_id": "sig-001",
        "intent_type": "OPEN_POSITION",
        "market_type": "futures",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 120,
        "size": 0.01,
        "strategy_binding": "trend_alpha",
        "timestamp": "2026-03-19T11:20:31Z",
        "scanner_signal_snapshot": {"signal_id": "evt-77", "timestamp": "2026-03-19T11:20:29Z"},
    }


def test_faz2_deterministic_idempotency_key_generation_examples():
    payload_a = _base_payload()
    payload_b = {
        "side": "   buy  ",
        "symbol": " btcusdt ",
        "order_type": " market ",
        "intent_type": "open_position",
        "market_type": "futures",
        "position_size_value": 120,
        "size": 0.0100000,
        "source_ref_id": "sig-001",
        "source_type": "manual",
        "strategy_binding": " trend_alpha ",
        "timestamp": "2026-03-19T11:20:31+00:00",
        "scanner_signal_snapshot": {"timestamp": "2026-03-19T11:20:29+00:00", "signal_id": "evt-77"},
    }
    payload_c = {**payload_a, "size": 0.02}

    key_a = build_execution_idempotency_key(user_id="user-123", payload=payload_a)
    key_b = build_execution_idempotency_key(user_id="user-123", payload=payload_b)
    key_c = build_execution_idempotency_key(user_id="user-123", payload=payload_c)

    assert key_a == key_b
    assert key_a != key_c

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(
            {
                "same_business_request": {
                    "example_a_key": key_a,
                    "example_b_key": key_b,
                    "equal": key_a == key_b,
                },
                "different_business_request": {
                    "example_c_key": key_c,
                    "different_from_a": key_a != key_c,
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
