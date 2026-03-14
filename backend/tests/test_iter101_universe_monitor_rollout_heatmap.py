"""
Iteration 101 - Universe Monitor + Rollout + Freshness Heatmap Testing

Tests for:
- POST /api/user/scanner/run returns 200 and scanner_perf includes rollout_stage + perf counters
- Indicator cache flow does not break scanner run (cache read/write fallback)
- GET /api/admin/universe-monitor/trends?window=24h|7d|30d returns points
- GET /api/admin/universe-monitor/export.csv returns CSV attachment
- GET /api/admin/universe-monitor/breakdown returns user_breakdown + regime_breakdown
- GET /api/admin/universe-monitor/freshness-heatmap returns items
- GET /api/admin/universe-monitor/rollout/status returns current/recommended stage
- POST /api/admin/universe-monitor/rollout/recommend returns KPI decision
- POST /api/admin/universe-monitor/rollout/approve updates stage
- GET /api/admin/universe-monitor summary includes queue_depth/stale_blocks/dropped/worker_utilization/top slow arrays
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

class TestUniverseMonitorRolloutHeatmap:
    """Backend tests for universe monitor, rollout orchestrator, and freshness heatmap"""

    @pytest.fixture(autouse=True)
    def setup_admin_auth(self):
        """Login as admin and store token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@platform.dev", "password": "Admin12345!"},
        )
        if response.status_code == 200:
            self.admin_token = response.json().get("access_token")
        else:
            pytest.skip("Admin login failed")

    @pytest.fixture
    def admin_headers(self):
        """Admin auth headers"""
        return {"Authorization": f"Bearer {self.admin_token}", "Content-Type": "application/json"}

    @pytest.fixture
    def user_auth(self):
        """Login as test user and return headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "TEST_phase4iter2_pipeline@example.com", "password": "TestPassword123!"},
        )
        if response.status_code == 200:
            token = response.json().get("access_token")
            return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        pytest.skip("User login failed")

    # --- 1. Scanner run with rollout_stage + perf counters ---
    def test_scanner_run_includes_rollout_stage_and_perf_counters(self, user_auth):
        """POST /api/user/scanner/run returns scanner_perf with rollout_stage and perf counters"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_auth,
            json={"max_results": 5},
        )
        assert response.status_code == 200, f"Scanner run failed: {response.text}"
        data = response.json()
        
        # Check scanner_perf block exists
        assert "scanner_perf" in data, "scanner_perf block missing"
        perf = data["scanner_perf"]
        
        # rollout_stage must be present
        assert "rollout_stage" in perf, "rollout_stage missing in scanner_perf"
        assert perf["rollout_stage"] in ["top_volume_subset", "mid_segment", "full_market"], f"Invalid rollout_stage: {perf.get('rollout_stage')}"
        
        # Perf counters present
        assert "cycle_duration_ms" in perf, "cycle_duration_ms missing"
        assert "symbols_evaluated" in perf, "symbols_evaluated missing"
        assert "stale_block_count" in perf, "stale_block_count missing"
        assert "dropped_symbol_count" in perf, "dropped_symbol_count missing"
        
        print(f"Scanner run perf: rollout_stage={perf.get('rollout_stage')}, cycle_duration_ms={perf.get('cycle_duration_ms')}, stale_blocks={perf.get('stale_block_count')}")

    # --- 2. Universe Monitor Summary with queue/stale/dropped/worker fields ---
    def test_universe_monitor_summary_includes_all_fields(self, admin_headers):
        """GET /api/admin/universe-monitor summary includes queue_depth/stale_blocks/dropped/worker_utilization/top slow arrays"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor",
            headers=admin_headers,
            params={"market_type": "spot", "scanner_mode": "ALL_MARKET_SYMBOLS", "top_n": 100},
        )
        assert response.status_code == 200, f"Universe monitor summary failed: {response.text}"
        data = response.json()
        
        # Core fields
        assert "queue_depth" in data, "queue_depth missing"
        assert "stale_blocks" in data, "stale_blocks missing"
        assert "dropped_evaluations" in data, "dropped_evaluations missing"
        assert "worker_utilization" in data, "worker_utilization missing"
        
        # Top slow arrays
        assert "top_slow_strategies" in data, "top_slow_strategies missing"
        assert "top_slow_symbols" in data, "top_slow_symbols missing"
        assert isinstance(data["top_slow_strategies"], list), "top_slow_strategies should be a list"
        assert isinstance(data["top_slow_symbols"], list), "top_slow_symbols should be a list"
        
        # New P0-B fields
        assert "symbols_evaluated_this_cycle" in data, "symbols_evaluated_this_cycle missing"
        assert "average_cycle_latency_ms" in data, "average_cycle_latency_ms missing"
        
        print(f"Universe monitor summary: queue_depth={data.get('queue_depth')}, stale_blocks={data.get('stale_blocks')}, worker_utilization={data.get('worker_utilization')}")

    # --- 3. Trends endpoint ---
    def test_universe_monitor_trends_24h(self, admin_headers):
        """GET /api/admin/universe-monitor/trends?window=24h returns points"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/trends",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200, f"Trends 24h failed: {response.text}"
        data = response.json()
        
        assert "points" in data, "points missing"
        assert isinstance(data["points"], list), "points should be list"
        assert "window" in data, "window missing"
        assert data["window"] == "24h", f"Expected window=24h, got {data.get('window')}"
        
        print(f"Trends 24h: {len(data['points'])} points")

    def test_universe_monitor_trends_7d(self, admin_headers):
        """GET /api/admin/universe-monitor/trends?window=7d returns points"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/trends",
            headers=admin_headers,
            params={"window": "7d"},
        )
        assert response.status_code == 200, f"Trends 7d failed: {response.text}"
        data = response.json()
        
        assert "points" in data, "points missing"
        assert data["window"] == "7d", f"Expected window=7d, got {data.get('window')}"
        
        print(f"Trends 7d: {len(data['points'])} points")

    def test_universe_monitor_trends_30d(self, admin_headers):
        """GET /api/admin/universe-monitor/trends?window=30d returns points"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/trends",
            headers=admin_headers,
            params={"window": "30d"},
        )
        assert response.status_code == 200, f"Trends 30d failed: {response.text}"
        data = response.json()
        
        assert "points" in data, "points missing"
        assert data["window"] == "30d", f"Expected window=30d, got {data.get('window')}"
        
        print(f"Trends 30d: {len(data['points'])} points")

    # --- 4. CSV export ---
    def test_universe_monitor_export_csv(self, admin_headers):
        """GET /api/admin/universe-monitor/export.csv returns CSV attachment"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/export.csv",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200, f"CSV export failed: {response.text}"
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "text/csv" in content_type, f"Expected text/csv, got {content_type}"
        
        # Check content disposition
        content_disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disposition, f"Expected attachment, got {content_disposition}"
        assert "universe_monitor_24h.csv" in content_disposition, f"Expected filename in disposition: {content_disposition}"
        
        # Check CSV has content
        csv_content = response.text
        assert len(csv_content) > 0, "CSV content is empty"
        assert "bucket" in csv_content, "CSV header 'bucket' missing"
        
        print(f"CSV export: {len(csv_content)} bytes, has headers")

    # --- 5. Breakdown endpoint ---
    def test_universe_monitor_breakdown(self, admin_headers):
        """GET /api/admin/universe-monitor/breakdown returns user_breakdown + regime_breakdown"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/breakdown",
            headers=admin_headers,
            params={"window": "7d"},
        )
        assert response.status_code == 200, f"Breakdown failed: {response.text}"
        data = response.json()
        
        assert "user_breakdown" in data, "user_breakdown missing"
        assert "regime_breakdown" in data, "regime_breakdown missing"
        assert isinstance(data["user_breakdown"], list), "user_breakdown should be list"
        assert isinstance(data["regime_breakdown"], list), "regime_breakdown should be list"
        
        print(f"Breakdown: {len(data['user_breakdown'])} users, {len(data['regime_breakdown'])} regimes")

    # --- 6. Freshness heatmap ---
    def test_freshness_heatmap(self, admin_headers):
        """GET /api/admin/universe-monitor/freshness-heatmap returns items"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/freshness-heatmap",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200, f"Freshness heatmap failed: {response.text}"
        data = response.json()
        
        assert "items" in data, "items missing"
        assert isinstance(data["items"], list), "items should be list"
        assert "window" in data, "window missing"
        
        # Check item structure if items exist
        if data["items"]:
            item = data["items"][0]
            assert "symbol" in item, "item.symbol missing"
            assert "timeframe" in item, "item.timeframe missing"
            assert "stale_rate" in item, "item.stale_rate missing"
        
        print(f"Freshness heatmap: {len(data['items'])} items, window={data.get('window')}")

    # --- 7. Rollout status ---
    def test_rollout_status(self, admin_headers):
        """GET /api/admin/universe-monitor/rollout/status returns current/recommended stage"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/rollout/status",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Rollout status failed: {response.text}"
        data = response.json()
        
        assert "current_stage" in data, "current_stage missing"
        assert data["current_stage"] in ["top_volume_subset", "mid_segment", "full_market"], f"Invalid current_stage: {data.get('current_stage')}"
        
        # recommended_stage can be None or a valid stage
        assert "recommended_stage" in data, "recommended_stage missing"
        assert "requires_admin_approval" in data, "requires_admin_approval missing"
        
        print(f"Rollout status: current={data.get('current_stage')}, recommended={data.get('recommended_stage')}, approval_required={data.get('requires_admin_approval')}")

    # --- 8. Rollout recommend ---
    def test_rollout_recommend(self, admin_headers):
        """POST /api/admin/universe-monitor/rollout/recommend returns KPI decision"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/rollout/recommend",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Rollout recommend failed: {response.text}"
        data = response.json()
        
        assert "decision" in data, "decision missing"
        assert data["decision"] in ["hold", "recommend_upgrade"], f"Invalid decision: {data.get('decision')}"
        
        assert "current_stage" in data, "current_stage missing"
        assert "recommended_stage" in data, "recommended_stage missing"
        assert "kpi" in data, "kpi missing"
        
        kpi = data.get("kpi", {})
        assert "healthy" in kpi, "kpi.healthy missing"
        
        print(f"Rollout recommend: decision={data.get('decision')}, current={data.get('current_stage')}, recommended={data.get('recommended_stage')}, kpi.healthy={kpi.get('healthy')}")

    # --- 9. Rollout approve ---
    def test_rollout_approve(self, admin_headers):
        """POST /api/admin/universe-monitor/rollout/approve updates stage"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/rollout/approve",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Rollout approve failed: {response.text}"
        data = response.json()
        
        assert "current_stage" in data, "current_stage missing after approve"
        assert "approved_by" in data, "approved_by missing"
        
        print(f"Rollout approve: current_stage={data.get('current_stage')}, approved_by={data.get('approved_by')}")

    # --- 10. Freshness heatmap different windows ---
    def test_freshness_heatmap_7d(self, admin_headers):
        """GET /api/admin/universe-monitor/freshness-heatmap?window=7d returns items"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/freshness-heatmap",
            headers=admin_headers,
            params={"window": "7d"},
        )
        assert response.status_code == 200, f"Freshness heatmap 7d failed: {response.text}"
        data = response.json()
        
        assert "items" in data, "items missing"
        assert data["window"] == "7d", f"Expected window=7d, got {data.get('window')}"
        
        print(f"Freshness heatmap 7d: {len(data['items'])} items")

    def test_freshness_heatmap_30d(self, admin_headers):
        """GET /api/admin/universe-monitor/freshness-heatmap?window=30d returns items"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/freshness-heatmap",
            headers=admin_headers,
            params={"window": "30d"},
        )
        assert response.status_code == 200, f"Freshness heatmap 30d failed: {response.text}"
        data = response.json()
        
        assert "items" in data, "items missing"
        assert data["window"] == "30d", f"Expected window=30d, got {data.get('window')}"
        
        print(f"Freshness heatmap 30d: {len(data['items'])} items")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
