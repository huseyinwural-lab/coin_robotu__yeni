# ruff: noqa: E402
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.futures_live_readiness_service import _compute_symbol_integrity_metrics


def test_scanner_execution_match_rate_format_and_percentage():
    intents = [
        SimpleNamespace(
            id="a",
            source_type="scanner",
            symbol="ETHUSDT",
            reject_reason_codes=[],
            normalized_order_payload={"symbol": "ETHUSDT", "scanner_signal_snapshot": {"symbol": "ETHUSDT"}},
        ),
        SimpleNamespace(
            id="b",
            source_type="scanner",
            symbol="SOLUSDT",
            reject_reason_codes=[],
            normalized_order_payload={"symbol": "SOLUSDT", "scanner_signal_snapshot": {"symbol": "SOLUSDT"}},
        ),
        SimpleNamespace(
            id="c",
            source_type="scanner",
            symbol="XRPUSDT",
            reject_reason_codes=[],
            normalized_order_payload={"symbol": "XRPUSDT", "scanner_signal_snapshot": {"symbol": "XRPUSDT"}},
        ),
    ]

    metrics = _compute_symbol_integrity_metrics(intents)
    assert metrics["scanner_to_execution_match_rate_pct"] == 100.0
    assert metrics["scanner_to_execution_match_rate"] == "100.0% (3/3)"
