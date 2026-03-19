# ruff: noqa: E402
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from server import fastapi_app


ARTIFACT_DIR = REPO_ROOT / "artifacts"
HEALTH_SAMPLE = ARTIFACT_DIR / "faz5_health_response.json"
READY_HEALTHY_SAMPLE = ARTIFACT_DIR / "faz5_ready_healthy_response.json"
READY_NOT_READY_SAMPLE = ARTIFACT_DIR / "faz5_ready_not_ready_response.json"
METRICS_SAMPLE = ARTIFACT_DIR / "faz5_metrics_output.txt"
FILE_LOG_SAMPLE = ARTIFACT_DIR / "faz5_file_log_sample.log"
MASKING_PROOF = ARTIFACT_DIR / "faz5_secret_masking_proof.json"
FAKE_ERROR_LOG = ARTIFACT_DIR / "faz5_fake_error_test.log"
ALERT_PAYLOAD_LOG = ARTIFACT_DIR / "faz5_alert_payload_sample.json"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(fastapi_app) as test_client:
        yield test_client


def _admin_token(client: TestClient) -> str:
    admin_email = (
        os.environ.get("TEST_ADMIN_EMAIL")
        or os.environ.get("ADMIN_BOOTSTRAP_EMAIL")
        or "admin@platform.local"
    )
    admin_password = (
        os.environ.get("TEST_ADMIN_PASSWORD")
        or os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
        or "Admin12345!"
    )
    response = client.post(
        "/api/auth/login/admin",
        json={"email": admin_email, "password": admin_password},
    )
    assert response.status_code == 200, response.text
    token = response.json().get("access_token")
    assert token
    return token


def test_phase5_logging_and_masking_and_health_ready_metrics(client: TestClient):
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    token = _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    probe_payload = {
        "sendgrid_api_key": os.environ.get("SENDGRID_API_KEY", ""),
        "alert_from": os.environ.get("FROM_EMAIL", "phase5-observability@example.com"),
        "alert_to": os.environ.get("TO_EMAIL", "huseyinwural@gmail.com"),
        "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
    }
    config_response = client.post("/api/admin/system-alerts/config", json=probe_payload, headers=headers)
    assert config_response.status_code == 200, config_response.text
    config_payload = config_response.json()

    health = client.get("/api/health")
    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload.get("status") == "ok"
    assert health_payload.get("service") == "backend-api"

    ready = client.get("/api/ready")
    assert ready.status_code == 200
    ready_payload = ready.json()
    assert ready_payload.get("status") == "ready"
    assert "checks" in ready_payload

    # Critical endpoint metrics coverage
    client.post("/api/auth/login/admin", json={"email": "bad@example.com", "password": "bad"})
    client.post("/api/user/execution/intent/submit", json={})
    client.post("/api/admin/kill-switch", json={"trading_enabled": True}, headers=headers)

    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200
    metrics_text = metrics.text
    assert "observability_error_rate_ratio" in metrics_text
    assert "observability_latency_ms_p95" in metrics_text
    assert "observability_queue_size" in metrics_text
    assert "endpoint=\"auth_login\"" in metrics_text
    assert "endpoint=\"execution_intent_submit\"" in metrics_text
    assert "endpoint=\"admin_kill_switch\"" in metrics_text

    log_path = Path(
        os.environ.get("OBSERVABILITY_LOG_FILE")
        or (REPO_ROOT / "backend" / "logs" / "backend_observability.log")
    )
    assert log_path.exists(), f"Missing log file: {log_path}"
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "Log file is empty"
    last_line = lines[-1]
    parsed_log = json.loads(last_line)
    for key in ["timestamp", "level", "service", "component", "event_name"]:
        assert key in parsed_log

    masked = (config_payload.get("config") or {}).get("masked") or {}

    HEALTH_SAMPLE.write_text(json.dumps(health_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    READY_HEALTHY_SAMPLE.write_text(json.dumps(ready_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    METRICS_SAMPLE.write_text(metrics_text, encoding="utf-8")
    FILE_LOG_SAMPLE.write_text(last_line + "\n", encoding="utf-8")
    MASKING_PROOF.write_text(json.dumps(masked, indent=2, ensure_ascii=False), encoding="utf-8")

    assert "sendgrid_api_key" in masked
    if probe_payload["sendgrid_api_key"]:
        assert probe_payload["sendgrid_api_key"] not in json.dumps(masked, ensure_ascii=False)


def test_phase5_fake_error_queue_pressure_ready_fail_end_to_end(client: TestClient):
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    token = _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    fake_error = client.post("/api/ops-alerts/simulate/fake-error", headers=headers)
    assert fake_error.status_code == 200, fake_error.text
    fake_error_payload = fake_error.json()
    assert fake_error_payload.get("alert_id")

    queue_pressure = client.post("/api/ops-alerts/simulate/queue-pressure", params={"queue_size": 45}, headers=headers)
    assert queue_pressure.status_code == 200, queue_pressure.text
    queue_payload = queue_pressure.json()
    assert queue_payload.get("queue_size") == 45
    assert isinstance(queue_payload.get("alert_ids"), list)

    ready_fail = client.post("/api/ops-alerts/simulate/ready-fail", params={"duration_seconds": 90}, headers=headers)
    assert ready_fail.status_code == 200, ready_fail.text
    ready_fail_payload = ready_fail.json()
    assert ready_fail_payload.get("alert_id")

    not_ready = client.get("/api/ready")
    assert not_ready.status_code == 503, not_ready.text
    not_ready_payload = not_ready.json()
    assert not_ready_payload.get("status") == "not_ready"

    alert_sample = {
        "fake_error": fake_error_payload,
        "queue_pressure": queue_payload,
        "ready_fail": ready_fail_payload,
        "ready_after_fail": not_ready_payload,
    }

    FAKE_ERROR_LOG.write_text(json.dumps(alert_sample, indent=2, ensure_ascii=False), encoding="utf-8")
    ALERT_PAYLOAD_LOG.write_text(json.dumps(fake_error_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    READY_NOT_READY_SAMPLE.write_text(json.dumps(not_ready_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    delivery_status = fake_error_payload.get("delivery_status") or {}
    email_status = ((delivery_status.get("email") or {}).get("status") or "").upper()
    telegram_status = (
        ((delivery_status.get("telegram") or {}).get("status") or "").upper()
        or ((delivery_status.get("slack") or {}).get("status") or "").upper()
    )
    acceptable = {"SENT", "SENT_TEST_SINK", "RATE_LIMITED", "CHANNEL_DISABLED", "CONFIG_MISSING"}
    assert email_status in acceptable
    assert telegram_status in acceptable