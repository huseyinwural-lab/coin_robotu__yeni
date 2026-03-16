import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.futures_live_readiness_service import _compute_symbol_integrity_metrics


def _intent(
    *,
    intent_id: str,
    source_type: str,
    order_symbol: str,
    scanner_symbol: str | None,
    reject_reason_codes: list[str] | None = None,
):
    payload = {"symbol": order_symbol}
    if scanner_symbol is not None:
        payload["scanner_signal_snapshot"] = {"symbol": scanner_symbol}
    return SimpleNamespace(
        id=intent_id,
        source_type=source_type,
        symbol=order_symbol,
        reject_reason_codes=reject_reason_codes or [],
        normalized_order_payload=payload,
    )


def test_symbol_integrity_failures_counts_mismatch_and_policy_rejects():
    intents = [
        _intent(intent_id="1", source_type="scanner", order_symbol="ETHUSDT", scanner_symbol="ETHUSDT"),
        _intent(intent_id="2", source_type="scanner", order_symbol="SOLUSDT", scanner_symbol="BTCUSDT"),
        _intent(
            intent_id="3",
            source_type="manual",
            order_symbol="XRPUSDT",
            scanner_symbol=None,
            reject_reason_codes=["invalid_quote_asset"],
        ),
    ]

    metrics = _compute_symbol_integrity_metrics(intents)
    assert metrics["symbol_integrity_failures"] == 2
    assert metrics["scanner_to_execution_matches"] == 1
    assert metrics["scanner_to_execution_total"] == 2
