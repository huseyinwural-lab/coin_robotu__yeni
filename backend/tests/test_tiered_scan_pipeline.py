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


def test_tiered_pipeline_wires_discovery_qualification_and_decision(monkeypatch):
    calls = {}

    monkeypatch.setattr(
        scanner_runtime,
        "evaluate_top_volume_fallback",
        lambda cache: {"active": False, "last_trigger_metric": None},
    )
    monkeypatch.setattr(
        scanner_runtime,
        "get_full_market_universe",
        lambda db, cache, scanner_mode, selected_symbols, top_n: {
            "spot_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "futures_symbols": [],
            "combined_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "combined_universe_size": 3,
            "snapshot_age_ms": 25_000,
        },
    )

    def fake_discovery(cache, symbols, *, max_candidates):
        calls["discovery_cap"] = max_candidates
        return {
            "universe_size": len(symbols),
            "discovery_candidates": [
                {"symbol": "BTCUSDT", "discovery_score": 5.0},
                {"symbol": "ETHUSDT", "discovery_score": 4.5},
            ],
            "discovery_candidate_symbols": ["BTCUSDT", "ETHUSDT"],
        }

    def fake_qualification(cache, discovery_candidates, *, max_candidates, snapshot_age_ms, freshness_bucket):
        calls["qualification_cap"] = max_candidates
        calls["qualification_input_count"] = len(discovery_candidates)
        calls["snapshot_age_ms"] = snapshot_age_ms
        calls["freshness_bucket"] = freshness_bucket
        return {
            "qualified_candidates": [{"symbol": "BTCUSDT", "qualification_score": 6.0}],
            "qualified_candidate_symbols": ["BTCUSDT"],
            "qualified_count": 1,
            "stale_filtered_count": 0,
        }

    def fake_run_user_scanner(
        db,
        user_id,
        requested_mode,
        max_results,
        symbol_source,
        selected_symbols,
        symbol_selection_mode,
    ):
        calls["decision_selected_symbols"] = selected_symbols
        calls["decision_mode"] = symbol_selection_mode
        calls["decision_max_results"] = max_results
        return {
            "run_id": "tiered-run",
            "items": [
                {
                    "symbol": "BTCUSDT",
                    "final_decision": "LONG",
                    "confidence": 0.88,
                    "reason_codes": ["trend"],
                }
            ],
            "scanner_perf": {"cycle_duration_ms": 120.0, "snapshot_age_avg_sec": 12, "queue_depth": 0},
        }

    monkeypatch.setattr(scanner_runtime, "run_discovery_scan", fake_discovery)
    monkeypatch.setattr(scanner_runtime, "run_qualification_scan", fake_qualification)
    monkeypatch.setattr(scanner_runtime, "run_user_scanner", fake_run_user_scanner)

    payload = scanner_runtime.run_scanner_runtime(
        DummyDb(),
        FakeCache(),
        user_id="u-tiered",
        backpressure_policy={
            "discovery_cap": 180,
            "qualification_cap": 100,
            "decision_cap": 30,
            "adjusted_max_results": 120,
        },
    )

    assert calls["discovery_cap"] == 180
    assert calls["qualification_cap"] == 30
    assert calls["qualification_input_count"] == 2
    assert calls["decision_selected_symbols"] == ["BTCUSDT"]
    assert calls["decision_mode"] == "manual_selection"
    assert calls["decision_max_results"] == 30
    assert payload["tiered_scan"]["enabled"] is True
    assert payload["tiered_scan"]["caps"] == {"discovery_cap": 180, "qualification_cap": 100, "decision_cap": 30}
    assert payload["tiered_scan"]["qualification"]["qualified_count"] == 1
