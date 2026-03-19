# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.decision.decision_trace_model import build_decision_trace


def test_decision_trace_model_contract_fields():
    trace = build_decision_trace(
        symbol="BTCUSDT",
        strategy="futures_trend_follow_v1",
        side="LONG",
        signal_confidence=0.81,
        regime="TRENDING",
        microstructure_result="PASS",
        risk_result="PASS",
        liquidation_result="PASS",
        adl_result="PASS",
        final_decision="ALLOW",
        reason_code="ALLOW",
        decision_layer="GATE",
    )

    required_fields = {
        "trace_id",
        "timestamp",
        "symbol",
        "strategy",
        "side",
        "signal_confidence",
        "regime",
        "microstructure_result",
        "risk_result",
        "liquidation_result",
        "adl_result",
        "leverage_decision",
        "confidence_multiplier",
        "microstructure_multiplier",
        "liquidation_multiplier",
        "funding_multiplier",
        "final_leverage",
        "position_size_ratio",
        "final_decision",
        "reason_code",
        "decision_layer",
    }
    assert required_fields.issubset(trace.keys())
    assert trace["symbol"] == "BTCUSDT"
    assert trace["strategy"] == "futures_trend_follow_v1"
