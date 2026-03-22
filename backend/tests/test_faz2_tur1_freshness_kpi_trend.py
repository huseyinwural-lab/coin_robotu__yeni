"""
FAZ-2 TUR-1 Backend Tests: Freshness/SLA + KPI Recommendation + Trend/Analytics
Tests for new endpoints added in admin_universe_monitor.py
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")

# Super Admin credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for super admin"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in auth response")
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestFreshnessSlaEndpoints:
    """Tests for Freshness/SLA endpoints"""

    def test_get_freshness_stale_list(self, auth_headers):
        """GET /api/admin/universe-monitor/freshness/stale-list returns stale entities"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/freshness/stale-list",
            headers=auth_headers,
            params={"limit": 100},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "generated_at" in data, "Missing generated_at field"
        assert "sla_config" in data, "Missing sla_config field"
        assert "count" in data, "Missing count field"
        assert "items" in data, "Missing items field"
        assert isinstance(data["items"], list), "items should be a list"
        
        # Verify reason_if_empty when no stale entities
        if data["count"] == 0:
            assert data.get("reason_if_empty") is not None, "Should have reason_if_empty when count=0"
        
        # If there are stale items, verify structure
        for item in data["items"][:5]:
            assert "entity_type" in item, "Stale item missing entity_type"
            assert "entity_id" in item, "Stale item missing entity_id"
            assert "severity" in item, "Stale item missing severity"
            assert item["severity"] in ["warning", "critical"], f"Invalid severity: {item['severity']}"
            assert "reason" in item, "Stale item missing reason"
            assert "age_sec" in item, "Stale item missing age_sec"
        
        print(f"Stale list: count={data['count']}, reason_if_empty={data.get('reason_if_empty')}")

    def test_get_freshness_sla_config(self, auth_headers):
        """GET /api/admin/universe-monitor/freshness/sla-config returns SLA configuration"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/freshness/sla-config",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "latency_threshold" in data, "Missing latency_threshold"
        assert "stale_threshold_sec" in data, "Missing stale_threshold_sec"
        assert isinstance(data["latency_threshold"], (int, float)), "latency_threshold should be numeric"
        assert isinstance(data["stale_threshold_sec"], int), "stale_threshold_sec should be int"
        
        print(f"SLA Config: latency_threshold={data['latency_threshold']}, stale_threshold_sec={data['stale_threshold_sec']}")

    def test_put_freshness_sla_config(self, auth_headers):
        """PUT /api/admin/universe-monitor/freshness/sla-config updates SLA configuration"""
        payload = {
            "latency_threshold": 1500.0,
            "stale_threshold_sec": 1200,
            "reason": "TEST_faz2_tur1_sla_update_test",
            "confirmation_phrase": "UPDATE SLA CONFIG",
        }
        response = requests.put(
            f"{BASE_URL}/api/admin/universe-monitor/freshness/sla-config",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify action result contract
        assert data.get("status") == "success", f"Expected status=success, got {data.get('status')}"
        assert "trace_id" in data, "Missing trace_id in response"
        assert "message" in data, "Missing message in response"
        assert "state_snapshot" in data, "Missing state_snapshot in response"
        
        # Verify state_snapshot contains sla_config
        snapshot = data.get("state_snapshot", {})
        assert "sla_config" in snapshot, "state_snapshot missing sla_config"
        
        print(f"SLA Update: trace_id={data['trace_id']}, message={data['message']}")

    def test_post_scanner_rescan_stale(self, auth_headers):
        """POST /api/admin/universe-monitor/scanner/rescan-stale queues stale entities for rescan"""
        payload = {
            "limit": 50,
            "reason": "TEST_faz2_tur1_rescan_stale_test",
            "confirmation_phrase": "RESCAN STALE",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/rescan-stale",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify action result contract
        assert data.get("status") == "success", f"Expected status=success, got {data.get('status')}"
        assert "trace_id" in data, "Missing trace_id"
        assert "message" in data, "Missing message"
        assert "state_snapshot" in data, "Missing state_snapshot"
        assert "queue_id" in data, "Missing queue_id in rescan-stale response"
        
        # Verify state_snapshot fields
        snapshot = data.get("state_snapshot", {})
        assert "stale_count" in snapshot, "state_snapshot missing stale_count"
        assert "symbol_rescan_count" in snapshot, "state_snapshot missing symbol_rescan_count"
        assert "queue_id" in snapshot, "state_snapshot missing queue_id"
        
        print(f"Rescan Stale: trace_id={data['trace_id']}, queue_id={data['queue_id']}, stale_count={snapshot.get('stale_count')}")


class TestKpiRecommendationEndpoints:
    """Tests for KPI Recommendation endpoints"""

    def test_post_recommendation_generate(self, auth_headers):
        """POST /api/admin/universe-monitor/recommendation/generate creates recommendations"""
        payload = {
            "reason": "TEST_faz2_tur1_kpi_generate_test",
            "confirmation_phrase": "GENERATE KPI RECOMMENDATION",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/recommendation/generate",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify action result contract
        assert data.get("status") == "success", f"Expected status=success, got {data.get('status')}"
        assert "trace_id" in data, "Missing trace_id"
        assert "message" in data, "Missing message"
        assert "state_snapshot" in data, "Missing state_snapshot"
        assert "items" in data, "Missing items (generated recommendations)"
        
        # Verify generated recommendations have required fields
        for item in data.get("items", []):
            assert "id" in item, "Recommendation missing id"
            assert "metric_source" in item, "Recommendation missing metric_source"
            assert "problem" in item, "Recommendation missing problem"
            assert "recommendation" in item, "Recommendation missing recommendation"
            assert "expected_impact" in item, "Recommendation missing expected_impact"
            assert "confidence_score" in item, "Recommendation missing confidence_score"
            assert "created_at" in item, "Recommendation missing created_at"
            assert isinstance(item["confidence_score"], (int, float)), "confidence_score should be numeric"
        
        print(f"KPI Generate: trace_id={data['trace_id']}, generated_count={len(data.get('items', []))}")
        return data.get("items", [])

    def test_get_recommendation_active(self, auth_headers):
        """GET /api/admin/universe-monitor/recommendation/active returns active recommendations"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/recommendation/active",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "count" in data, "Missing count field"
        assert "items" in data, "Missing items field"
        assert isinstance(data["items"], list), "items should be a list"
        
        print(f"Active Recommendations: count={data['count']}")
        return data.get("items", [])

    def test_get_recommendation_history(self, auth_headers):
        """GET /api/admin/universe-monitor/recommendation/history returns recommendation history"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/recommendation/history",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "count" in data, "Missing count field"
        assert "items" in data, "Missing items field"
        assert isinstance(data["items"], list), "items should be a list"
        
        print(f"Recommendation History: count={data['count']}")

    def test_recommendation_apply_reject_postpone_flow(self, auth_headers):
        """Test apply/reject/postpone flow for recommendations"""
        # First generate recommendations
        gen_response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/recommendation/generate",
            headers=auth_headers,
            json={
                "reason": "TEST_faz2_tur1_decision_flow_test",
                "confirmation_phrase": "GENERATE KPI RECOMMENDATION",
            },
        )
        assert gen_response.status_code == 200
        
        # Get active recommendations
        active_response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/recommendation/active",
            headers=auth_headers,
        )
        assert active_response.status_code == 200
        active_items = active_response.json().get("items", [])
        
        if len(active_items) == 0:
            pytest.skip("No active recommendations to test decision flow")
        
        # Test APPLY on first recommendation
        rec_id = active_items[0]["id"]
        apply_response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/recommendation/apply",
            headers=auth_headers,
            json={
                "recommendation_id": rec_id,
                "reason": "TEST_faz2_tur1_apply_test",
                "confirmation_phrase": "APPLY RECOMMENDATION",
            },
        )
        assert apply_response.status_code == 200, f"Apply failed: {apply_response.text}"
        apply_data = apply_response.json()
        assert apply_data.get("status") == "success"
        assert "trace_id" in apply_data
        print(f"Apply: trace_id={apply_data['trace_id']}, recommendation_id={rec_id}")
        
        # Verify recommendation moved to history
        history_response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/recommendation/history",
            headers=auth_headers,
        )
        assert history_response.status_code == 200
        history_items = history_response.json().get("items", [])
        applied_in_history = [item for item in history_items if item.get("id") == rec_id]
        assert len(applied_in_history) > 0, "Applied recommendation should be in history"
        assert applied_in_history[0].get("status") == "apply", "Status should be 'apply'"
        
        # Generate more recommendations for reject/postpone tests
        requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/recommendation/generate",
            headers=auth_headers,
            json={
                "reason": "TEST_faz2_tur1_more_recs",
                "confirmation_phrase": "GENERATE KPI RECOMMENDATION",
            },
        )
        
        # Get new active recommendations
        active_response2 = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/recommendation/active",
            headers=auth_headers,
        )
        active_items2 = active_response2.json().get("items", [])
        
        if len(active_items2) >= 1:
            # Test REJECT
            rec_id2 = active_items2[0]["id"]
            reject_response = requests.post(
                f"{BASE_URL}/api/admin/universe-monitor/recommendation/reject",
                headers=auth_headers,
                json={
                    "recommendation_id": rec_id2,
                    "reason": "TEST_faz2_tur1_reject_test",
                    "confirmation_phrase": "REJECT RECOMMENDATION",
                },
            )
            assert reject_response.status_code == 200, f"Reject failed: {reject_response.text}"
            print(f"Reject: trace_id={reject_response.json().get('trace_id')}")
        
        if len(active_items2) >= 2:
            # Test POSTPONE
            rec_id3 = active_items2[1]["id"]
            postpone_response = requests.post(
                f"{BASE_URL}/api/admin/universe-monitor/recommendation/postpone",
                headers=auth_headers,
                json={
                    "recommendation_id": rec_id3,
                    "reason": "TEST_faz2_tur1_postpone_test",
                    "confirmation_phrase": "POSTPONE RECOMMENDATION",
                },
            )
            assert postpone_response.status_code == 200, f"Postpone failed: {postpone_response.text}"
            print(f"Postpone: trace_id={postpone_response.json().get('trace_id')}")


class TestTrendMetricsEndpoints:
    """Tests for Trend/Analytics endpoints"""

    def test_get_metrics_history_24h(self, auth_headers):
        """GET /api/admin/universe-monitor/metrics/history?range=24h returns trend data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/metrics/history",
            headers=auth_headers,
            params={"range": "24h"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required response fields
        assert "range" in data, "Missing range field"
        assert data["range"] == "24h", f"Expected range=24h, got {data['range']}"
        assert "generated_at" in data, "Missing generated_at"
        assert "latency_series" in data, "Missing latency_series"
        assert "pnl_series" in data, "Missing pnl_series"
        assert "risk_veto_series" in data, "Missing risk_veto_series"
        assert "overlays" in data, "Missing overlays"
        
        # Verify series are lists
        assert isinstance(data["latency_series"], list), "latency_series should be a list"
        assert isinstance(data["pnl_series"], list), "pnl_series should be a list"
        assert isinstance(data["risk_veto_series"], list), "risk_veto_series should be a list"
        assert isinstance(data["overlays"], list), "overlays should be a list"
        
        # Verify reason_if_empty when no data
        if len(data["latency_series"]) == 0 and len(data["pnl_series"]) == 0:
            # Should have fallback snapshot
            assert data.get("reason_if_empty") is not None or len(data["latency_series"]) > 0, \
                "Should have reason_if_empty or fallback data"
        
        print(f"Metrics History 24h: latency_series={len(data['latency_series'])}, pnl_series={len(data['pnl_series'])}, overlays={len(data['overlays'])}")

    def test_get_metrics_history_all_ranges(self, auth_headers):
        """Test all supported range values: 1h, 24h, 7d, 30d"""
        for range_val in ["1h", "24h", "7d", "30d"]:
            response = requests.get(
                f"{BASE_URL}/api/admin/universe-monitor/metrics/history",
                headers=auth_headers,
                params={"range": range_val},
            )
            assert response.status_code == 200, f"Range {range_val} failed: {response.status_code}"
            data = response.json()
            assert data["range"] == range_val, f"Expected range={range_val}, got {data['range']}"
            print(f"Range {range_val}: OK")

    def test_get_metrics_history_with_symbol_filter(self, auth_headers):
        """GET /api/admin/universe-monitor/metrics/history with symbol drill-down"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/metrics/history",
            headers=auth_headers,
            params={"range": "24h", "symbol": "BTCUSDT"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("symbol") == "BTCUSDT", f"Expected symbol=BTCUSDT, got {data.get('symbol')}"
        print(f"Symbol filter BTCUSDT: latency_series={len(data['latency_series'])}")

    def test_get_metrics_history_with_strategy_filter(self, auth_headers):
        """GET /api/admin/universe-monitor/metrics/history with strategy drill-down"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/metrics/history",
            headers=auth_headers,
            params={"range": "24h", "strategy": "spot_pullback_v1"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("strategy") == "spot_pullback_v1", f"Expected strategy=spot_pullback_v1, got {data.get('strategy')}"
        print(f"Strategy filter spot_pullback_v1: latency_series={len(data['latency_series'])}")

    def test_metrics_history_overlay_structure(self, auth_headers):
        """Verify overlay structure in metrics history response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/metrics/history",
            headers=auth_headers,
            params={"range": "7d"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Overlays should contain rollout/risk override/fallback events
        for overlay in data.get("overlays", [])[:5]:
            assert "ts" in overlay, "Overlay missing ts"
            assert "event" in overlay, "Overlay missing event"
            # Event should be ROLLOUT, OVERRIDE, or FALLBACK related
            event = overlay.get("event", "")
            assert any(keyword in event for keyword in ["ROLLOUT", "OVERRIDE", "FALLBACK"]), \
                f"Unexpected overlay event: {event}"
        
        print(f"Overlays verified: {len(data.get('overlays', []))} events")


class TestActionContractCompliance:
    """Verify all action endpoints follow the standard contract"""

    def test_rescan_stale_action_contract(self, auth_headers):
        """Verify rescan-stale follows action contract: status=success + trace_id + message + state_snapshot + queue_id"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/rescan-stale",
            headers=auth_headers,
            json={
                "limit": 10,
                "reason": "TEST_action_contract_verification",
                "confirmation_phrase": "RESCAN STALE",
            },
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify all required fields per contract
        assert data.get("status") == "success", "Missing or incorrect status"
        assert "trace_id" in data and data["trace_id"], "Missing trace_id"
        assert "message" in data and data["message"], "Missing message"
        assert "state_snapshot" in data and isinstance(data["state_snapshot"], dict), "Missing state_snapshot"
        assert "queue_id" in data and data["queue_id"], "Missing queue_id"
        
        print(f"Action contract verified: trace_id={data['trace_id']}, queue_id={data['queue_id']}")

    def test_sla_update_requires_confirmation_phrase(self, auth_headers):
        """Verify SLA update requires correct confirmation phrase"""
        # Wrong phrase should fail
        response = requests.put(
            f"{BASE_URL}/api/admin/universe-monitor/freshness/sla-config",
            headers=auth_headers,
            json={
                "latency_threshold": 1000,
                "stale_threshold_sec": 600,
                "reason": "TEST_wrong_phrase",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400 for wrong phrase, got {response.status_code}"
        
        # Correct phrase should succeed
        response2 = requests.put(
            f"{BASE_URL}/api/admin/universe-monitor/freshness/sla-config",
            headers=auth_headers,
            json={
                "latency_threshold": 1200,
                "stale_threshold_sec": 900,
                "reason": "TEST_correct_phrase",
                "confirmation_phrase": "UPDATE SLA CONFIG",
            },
        )
        assert response2.status_code == 200, f"Expected 200 for correct phrase, got {response2.status_code}"
        print("Confirmation phrase validation verified")

    def test_recommendation_decision_requires_valid_id(self, auth_headers):
        """Verify recommendation apply/reject/postpone requires valid recommendation_id"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/recommendation/apply",
            headers=auth_headers,
            json={
                "recommendation_id": "nonexistent-id-12345",
                "reason": "TEST_invalid_id",
                "confirmation_phrase": "APPLY RECOMMENDATION",
            },
        )
        assert response.status_code == 404, f"Expected 404 for invalid id, got {response.status_code}"
        print("Invalid recommendation_id returns 404 as expected")


class TestEmptyPanelBehavior:
    """Verify empty panel behavior shows 'No data yet' + reason"""

    def test_stale_list_empty_reason(self, auth_headers):
        """Verify stale-list returns reason_if_empty when no stale entities"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/freshness/stale-list",
            headers=auth_headers,
            params={"limit": 500},
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["count"] == 0:
            assert data.get("reason_if_empty") is not None, "Should have reason_if_empty when count=0"
            print(f"Empty stale list reason: {data['reason_if_empty']}")
        else:
            print(f"Stale list has {data['count']} items, skipping empty check")

    def test_metrics_history_fallback_snapshot(self, auth_headers):
        """Verify metrics/history provides fallback snapshot when no data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/metrics/history",
            headers=auth_headers,
            params={"range": "1h"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Even with no data, should have at least fallback snapshot
        assert len(data["latency_series"]) > 0 or data.get("reason_if_empty") is not None, \
            "Should have fallback data or reason_if_empty"
        print(f"Metrics history: latency_series={len(data['latency_series'])}, reason_if_empty={data.get('reason_if_empty')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
