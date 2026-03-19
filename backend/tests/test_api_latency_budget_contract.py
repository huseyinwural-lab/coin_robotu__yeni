# ruff: noqa: E402
import sys
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import server


class _DummyConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        return None


class _DummyEngine:
    def connect(self):
        return _DummyConnection()


def _compute_p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[index]


def test_health_api_latency_budget_p95(monkeypatch):
    monkeypatch.setattr(server, "verify_database_connection", lambda: None)
    monkeypatch.setattr(server, "engine", _DummyEngine())

    client = TestClient(server.fastapi_app)
    latencies_ms: list[float] = []
    for _ in range(25):
        started = perf_counter()
        response = client.get("/api/health")
        elapsed_ms = (perf_counter() - started) * 1000
        latencies_ms.append(elapsed_ms)
        assert response.status_code == 200
        assert response.json().get("status") == "ok"

    p95_ms = _compute_p95(latencies_ms)
    assert p95_ms < 120.0
