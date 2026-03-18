import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.explainability_rules_service import (
    build_screener_explain,
    build_trade_explain,
    explain_consistency_ok,
)


def test_screener_and_trade_explain_are_consistent_for_same_signal_context():
    screener_explain = build_screener_explain(
        payload={"rsi": 27.8, "volume_spike": 2.2, "price": 101, "ma50": 97},
        signal="long",
        signal_score=82,
    )
    trade_explain = build_trade_explain(
        validation={
            "valid": True,
            "violations": [],
            "checks": {
                "requested_leverage": 2,
                "leverage_limit": 5,
            },
        },
        execution_mode="mocked",
        signal_score=82,
    )

    assert len(screener_explain) >= 1
    assert len(trade_explain) >= 1
    assert explain_consistency_ok(screener_explain=screener_explain, trade_explain=trade_explain) is True


def test_consistency_rule_detects_explicit_conflict():
    assert explain_consistency_ok(
        screener_explain=["RSI oversold (28)", "Above MA50"],
        trade_explain=["RSI overbought (75)", "Below MA50"],
    ) is False
