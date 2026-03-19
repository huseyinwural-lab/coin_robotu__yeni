# ruff: noqa: E402
import sys
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import deps
import server
from models import UserRole


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


class _DummyUser:
    id = "latency-contract-admin"
    role = UserRole.ADMIN
    is_active = True
    approval_status = "approved"


def _compute_p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[index]


def _measure_p95(client: TestClient, endpoint: str, repeats: int = 20) -> float:
    latencies_ms: list[float] = []
    for _ in range(repeats):
        started = perf_counter()
        response = client.get(endpoint)
        elapsed_ms = (perf_counter() - started) * 1000
        latencies_ms.append(elapsed_ms)
        assert response.status_code == 200
    return _compute_p95(latencies_ms)


def test_api_latency_budget_p95_by_endpoint(monkeypatch):
    monkeypatch.setattr(server, "verify_database_connection", lambda: None)
    monkeypatch.setattr(server, "engine", _DummyEngine())

    server.fastapi_app.dependency_overrides[deps.require_admin] = lambda: _DummyUser()
    server.fastapi_app.dependency_overrides[deps.get_current_user] = lambda: _DummyUser()

    budgets_ms = {
        "/api/health": 120.0,
        "/api/admin/execution-readiness": 900.0,
        "/api/dashboard/summary": 1100.0,
    }

    try:
        client = TestClient(server.fastapi_app)
        for endpoint, budget_ms in budgets_ms.items():
            p95_ms = _measure_p95(client, endpoint, repeats=20)
            assert p95_ms < budget_ms, f"{endpoint} p95 {p95_ms:.2f}ms > budget {budget_ms}ms"
    finally:
        server.fastapi_app.dependency_overrides.clear()
