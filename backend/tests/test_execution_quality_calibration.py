from types import SimpleNamespace

from services.execution_quality_calibration_service import calibrate_execution_quality_thresholds


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)


class FakeDb:
    def __init__(self):
        self.execution_rows = [
            SimpleNamespace(symbol="BTCUSDT", slippage_pct=0.2, execution_time_ms=1200, final_status="FILLED", status="FILLED", created_at=None),
            SimpleNamespace(symbol="ETHUSDT", slippage_pct=1.4, execution_time_ms=6000, final_status="REJECTED", status="REJECTED", created_at=None),
        ]
        self.intent_rows = [
            SimpleNamespace(
                symbol="BTCUSDT",
                normalized_order_payload={"signal_bridge_context": {"snapshot_age_ms": 1000, "orderbook_depth_score": 0.9, "spread": {"spread_bps": 8}}},
                reject_reason_codes=[],
                gate_decision="ALLOW",
                intent_token="t1",
                created_at=None,
            ),
            SimpleNamespace(
                symbol="ETHUSDT",
                normalized_order_payload={"signal_bridge_context": {"snapshot_age_ms": 180000, "orderbook_depth_score": 0.3, "spread": {"spread_bps": 55}}},
                reject_reason_codes=["spread_block"],
                gate_decision="BLOCK",
                intent_token="t2",
                created_at=None,
            ),
        ]
        self.testnet_rows = [SimpleNamespace(status="filled", slippage=0.2, expected_price=100.0, execution_latency=1200, created_at=None)]

    def query(self, model):
        model_name = getattr(model, "__name__", "")
        if model_name == "ExecutionMetric":
            return FakeQuery(self.execution_rows)
        if model_name == "UserExecutionIntent":
            return FakeQuery(self.intent_rows)
        return FakeQuery(self.testnet_rows)


class FakeCache:
    def __init__(self):
        self.store = {}

    def set(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


def test_execution_quality_calibration_returns_thresholds():
    report = calibrate_execution_quality_thresholds(FakeDb(), FakeCache(), sample_size=100)
    assert report["status"] == "calibrated"
    assert set(report["recommended_thresholds"].keys()) == {
        "execution_quality_threshold",
        "spread_threshold_bps",
        "stale_data_threshold_ms",
    }
    assert report["false_allow_rate"] >= 0
