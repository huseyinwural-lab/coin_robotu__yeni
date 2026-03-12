"""Phase-5 Iterasyon-4 testleri

- Lifecycle proof pipeline (blocked/live + fallback replay evidence)
- Execution immutable persistence + correction events
- Replay risk summary endpoint + deterministic JSON export
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))

from db import SessionLocal
from models import ExecutionMetric


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://portfolio-pro-494.preview.emergentagent.com")


@pytest.fixture(scope="module")
def user_context() -> dict:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": "TEST_phase4iter2_pipeline@example.com", "password": "TestPassword123!"},
        timeout=20,
    )
    assert response.status_code == 200
    payload = response.json()
    return {"token": payload["access_token"], "user_id": payload["user"]["id"]}


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class TestLifecycleProofPipeline:
    def test_lifecycle_proof_generates_machine_readable_artifacts(self, user_context):
        response = requests.post(
            f"{BASE_URL}/api/exchange/lifecycle-proof",
            headers=_headers(user_context["token"]),
            timeout=90,
        )
        assert response.status_code == 200
        data = response.json()

        assert data["lifecycle_proof_status"] in {"completed", "fallback_generated", "blocked"}
        assert data["evidence_type"] in {"live_exchange", "blocked"}
        assert Path(data["exchange_evidence_file"]).exists()

        if data["fallback_replay_evidence_file"]:
            fallback_path = Path(data["fallback_replay_evidence_file"])
            assert fallback_path.exists()
            payload = json.loads(fallback_path.read_text(encoding="utf-8"))
            assert payload["evidence_type"] == "fallback_replay"

    def test_execution_order_alias_contract(self, user_context):
        response = requests.post(
            f"{BASE_URL}/api/exchange/execution/order",
            headers=_headers(user_context["token"]),
            params={
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "leverage": 3,
            },
            timeout=40,
        )
        assert response.status_code in {200, 400}
        if response.status_code == 400:
            detail = response.json()["detail"]
            assert "failure_code" in detail
            assert detail.get("exchange") == "binance"
            assert detail.get("market_type") == "futures"
            assert detail.get("environment") == "testnet"


class TestExecutionImmutability:
    def test_execution_update_rejected_with_immutable_rule(self, user_context):
        session = SessionLocal()
        metric = ExecutionMetric(
            user_id=user_context["user_id"],
            symbol="BTCUSDT",
            order_id="immutable-test-order",
            exchange_order_id="immutable-test-exchange-order",
            client_order_id="immutable-test-client-order",
            order_type="MARKET",
            exchange="binance",
            market_type="futures",
            environment="testnet",
            side="BUY",
            quote_qty=10,
            mid_price=50000,
            mid_price_timestamp=datetime.now(timezone.utc).isoformat(),
            price_avg=50010,
            executed_qty=0.0002,
            slippage_pct=0.02,
            execution_time_ms=110,
            status="FILLED",
            final_status="FILLED",
            strategy_type="trend_following",
            volatility_regime="low",
            volatility_pct=0.01,
            execution_quality_score=88,
            submitted_at=datetime.now(timezone.utc),
            ack_at=datetime.now(timezone.utc),
            final_at=datetime.now(timezone.utc),
            validation_snapshot_id="immutable-test-snapshot",
            raw_exchange_status={"status": "FILLED"},
            state_machine_path=["NEW", "FILLED"],
        )
        session.add(metric)
        session.commit()
        session.refresh(metric)

        metric.status = "CANCELED"
        with pytest.raises(Exception):
            session.commit()
        session.rollback()
        session.close()

    def test_correction_event_append_only(self, user_context):
        session = SessionLocal()
        metric = ExecutionMetric(
            user_id=user_context["user_id"],
            symbol="BTCUSDT",
            order_id=f"immutable-correction-{datetime.now(timezone.utc).timestamp()}",
            exchange_order_id="immutable-correction-exchange-order",
            client_order_id="immutable-correction-client-order",
            order_type="MARKET",
            exchange="binance",
            market_type="futures",
            environment="testnet",
            side="BUY",
            quote_qty=10,
            mid_price=50000,
            mid_price_timestamp=datetime.now(timezone.utc).isoformat(),
            price_avg=50000,
            executed_qty=0.0002,
            slippage_pct=0.0,
            execution_time_ms=50,
            status="FILLED",
            final_status="FILLED",
            strategy_type="trend_following",
            volatility_regime="low",
            volatility_pct=0.01,
            execution_quality_score=90,
            submitted_at=datetime.now(timezone.utc),
            ack_at=datetime.now(timezone.utc),
            final_at=datetime.now(timezone.utc),
            validation_snapshot_id="immutable-correction-snapshot",
            raw_exchange_status={"status": "FILLED"},
            state_machine_path=["NEW", "FILLED"],
        )
        session.add(metric)
        session.commit()
        session.refresh(metric)
        execution_id = metric.id
        session.close()

        create_response = requests.post(
            f"{BASE_URL}/api/exchange/execution/{execution_id}/corrections",
            headers=_headers(user_context["token"]),
            json={
                "correction_type": "annotation",
                "reason_code": "ops_review",
                "note": "immutable correction event",
                "patch_payload": {"tag": "reviewed"},
            },
            timeout=20,
        )
        assert create_response.status_code == 201

        list_response = requests.get(
            f"{BASE_URL}/api/exchange/execution/{execution_id}/corrections",
            headers=_headers(user_context["token"]),
            timeout=20,
        )
        assert list_response.status_code == 200
        items = list_response.json()
        assert len(items) >= 1
        assert items[-1]["reason_code"] == "ops_review"


class TestReplayRiskSummary:
    def test_replay_risk_summary_endpoint_and_export(self, user_context):
        run_response = requests.post(
            f"{BASE_URL}/api/backtest/replay/run",
            headers=_headers(user_context["token"]),
            json={
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "strategy_type": "trend_following",
                "limit": 180,
            },
            timeout=80,
        )
        assert run_response.status_code == 201
        run_id = run_response.json()["run_id"]

        summary_response = requests.get(
            f"{BASE_URL}/api/backtest/replay/{run_id}/risk-summary",
            headers=_headers(user_context["token"]),
            timeout=30,
        )
        assert summary_response.status_code == 200
        summary = summary_response.json()
        expected_keys = {
            "schema_version",
            "run_id",
            "strategy_version",
            "max_drawdown",
            "sharpe",
            "win_rate",
            "profit_factor",
            "avg_slippage_bps",
            "volatility_bucket",
            "regime_bucket_distribution",
            "exposure_breach_count",
            "risk_reject_count",
            "evidence_type",
            "export_file",
            "generated_at",
        }
        assert expected_keys.issubset(set(summary.keys()))
        assert summary["run_id"] == run_id

        export_path = Path(summary["export_file"])
        assert export_path.exists()
        exported = json.loads(export_path.read_text(encoding="utf-8"))
        assert exported["run_id"] == run_id
        assert exported["schema_version"] == summary["schema_version"]
