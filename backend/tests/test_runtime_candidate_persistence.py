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


def test_runtime_candidate_rows_persisted(monkeypatch):
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
            "run_id": "run-2",
            "items": [
                {"symbol": "BTCUSDT", "final_decision": "LONG", "confidence": 0.9, "reason_codes": ["trend"]},
                {"symbol": "ETHUSDT", "final_decision": "SHORT", "confidence": 0.8, "reason_codes": ["trend"]},
            ],
            "scanner_perf": {"cycle_duration_ms": 180.0, "snapshot_age_avg_sec": 10, "queue_depth": 1},
        },
    )

    db = DummyDb()
    payload = scanner_runtime.run_scanner_runtime(db, FakeCache(), user_id="u2")

    assert payload["persisted_candidate_count"] == 2
    assert len(db.rows) == 2
    assert {row.symbol for row in db.rows} == {"BTCUSDT", "ETHUSDT"}
