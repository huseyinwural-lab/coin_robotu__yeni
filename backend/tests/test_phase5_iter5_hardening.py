"""Phase-5 Hardening İterasyon-5 testleri

- SHA-256 artefact manifest + verify endpoint
- Hash mismatch tespiti
- Replay completion -> risk_policy_audit_events tekil kaydı
"""

import json
import os
import sys
from pathlib import Path

import pytest
import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))

from db import SessionLocal
from models import RiskPolicyAuditEvent


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://approval-intel-1.preview.emergentagent.com")


@pytest.fixture(scope="module")
def admin_token() -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
        timeout=20,
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def user_token() -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": "TEST_phase4iter2_pipeline@example.com", "password": "TestPassword123!"},
        timeout=20,
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class TestArtifactIntegrity:
    def test_manifest_and_verify_endpoint(self, admin_token, user_token):
        proof_response = requests.post(
            f"{BASE_URL}/api/exchange/lifecycle-proof",
            headers=_headers(user_token),
            timeout=90,
        )
        assert proof_response.status_code == 200
        proof = proof_response.json()
        assert proof["exchange_artifact_id"] is not None
        assert Path(proof["exchange_evidence_file"]).exists()

        manifest_response = requests.get(
            f"{BASE_URL}/api/audit/admin/proofs",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert manifest_response.status_code == 200
        manifest_items = manifest_response.json()
        assert any(item["artifact_id"] == proof["exchange_artifact_id"] for item in manifest_items)

        verify_response = requests.get(
            f"{BASE_URL}/api/audit/artifacts/{proof['exchange_artifact_id']}/verify",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert verify_response.status_code == 200
        verified = verify_response.json()
        assert verified["artifact_id"] == proof["exchange_artifact_id"]
        assert verified["verified"] is True

    def test_modified_artifact_detected(self, admin_token, user_token):
        proof_response = requests.post(
            f"{BASE_URL}/api/exchange/lifecycle-proof",
            headers=_headers(user_token),
            timeout=90,
        )
        assert proof_response.status_code == 200
        proof = proof_response.json()

        artifact_path = Path(proof["exchange_evidence_file"])
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        payload["tamper_test_marker"] = "modified"
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        verify_response = requests.get(
            f"{BASE_URL}/api/audit/artifacts/{proof['exchange_artifact_id']}/verify",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert verify_response.status_code == 200
        verified = verify_response.json()
        assert verified["verified"] is False


class TestReplayRiskAuditFeed:
    def test_replay_completion_writes_single_risk_policy_audit_event(self, user_token):
        run_response = requests.post(
            f"{BASE_URL}/api/backtest/replay/run",
            headers=_headers(user_token),
            json={
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "limit": 150,
            },
            timeout=80,
        )
        assert run_response.status_code == 201
        run_id = run_response.json()["run_id"]

        db = SessionLocal()
        before_count = db.query(RiskPolicyAuditEvent).filter(RiskPolicyAuditEvent.replay_run_id == run_id).count()
        assert before_count == 1

        for _ in range(2):
            summary_response = requests.get(
                f"{BASE_URL}/api/backtest/replay/{run_id}/risk-summary",
                headers=_headers(user_token),
                timeout=30,
            )
            assert summary_response.status_code == 200

        after_count = db.query(RiskPolicyAuditEvent).filter(RiskPolicyAuditEvent.replay_run_id == run_id).count()
        db.close()
        assert after_count == 1
