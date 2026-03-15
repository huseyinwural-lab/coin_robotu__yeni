from services.pipeline.cache_store import set_json
from services.top_volume_fallback import evaluate_top_volume_fallback


class FakeCache:
    def __init__(self):
        self.store = {}

    def set(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


def test_top_volume_fallback_activates_when_metrics_high():
    cache = FakeCache()
    set_json(cache, "scanner:queue:state", {"depth": 99, "worker_utilization": 0.95, "cycle_latency_ms": 5000})
    set_json(
        cache,
        "scanner:runtime:latest:global",
        {
            "runtime_metrics": {
                "scan_latency_ms": 5200,
                "decision_latency_ms": 3200,
                "snapshot_age_ms": 200000,
                "queue_depth": 99,
                "candidate_count": 12,
            }
        },
    )

    payload = evaluate_top_volume_fallback(cache)

    assert payload["active"] is True
    assert payload["reason_code"] in {
        "latency_spike",
        "scan_latency_ms",
        "decision_latency_ms",
        "snapshot_age_ms",
        "queue_depth",
        "pipeline_backpressure",
    }
