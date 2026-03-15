from services import scanner_runtime


class DummyDb:
    def __init__(self):
        self.rows = []

    def add_all(self, rows):
        self.rows.extend(rows)

    def commit(self):
        return None


class FakeCache:
    def __init__(self):
        self.store = {}

    def set(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


def test_decision_contract_is_normalized(monkeypatch):
    monkeypatch.setattr(
        scanner_runtime,
        "get_full_market_universe",
        lambda db, cache, scanner_mode, selected_symbols, top_n: {
            "spot_symbols": ["BTCUSDT"],
            "futures_symbols": ["ETHUSDT"],
            "combined_universe_size": 2,
        },
    )
    monkeypatch.setattr(
        scanner_runtime,
        "run_user_scanner",
        lambda db, user_id, requested_mode, max_results, symbol_source, selected_symbols, symbol_selection_mode: {
            "run_id": "run-1",
            "items": [
                {
                    "symbol": "BTCUSDT",
                    "final_decision": "NO_TRADE",
                    "confidence": 0.42,
                    "reason_codes": ["risk_gate"],
                    "strategy_code": "trend_v1",
                }
            ],
            "scanner_perf": {"cycle_duration_ms": 123.0, "snapshot_age_avg_sec": 20, "queue_depth": 1},
        },
    )

    db = DummyDb()
    cache = FakeCache()
    payload = scanner_runtime.run_scanner_runtime(db, cache, user_id="u1")

    decision = payload["decisions"][0]
    assert decision["decision"] == "PASS"
    assert set(decision.keys()) == {
        "symbol",
        "decision",
        "confidence",
        "reason",
        "strategy_name",
        "signal_strength",
        "risk_filter_reason",
        "decision_reason",
    }
