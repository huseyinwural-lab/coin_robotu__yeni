"""
RISK-1..RISK-6 API Kontrat Testleri
Risk Engine yeni endpointleri:
- GET/PATCH /api/admin/risk/config
- POST /api/admin/risk/config/reload  
- GET /api/admin/risk/status
- Runtime summary içinde risk_overview
- Scanner runtime içinde risk_engine bloğu
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://market-scanner-v3.preview.emergentagent.com"

ADMIN_CREDENTIALS = {
    "email": "admin@platform.local",
    "password": "Admin12345!"
}


class TestRiskAdminEndpoints:
    """Admin Risk Config Endpoint Tests"""
    
    token = None
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin before each test"""
        if TestRiskAdminEndpoints.token is None:
            response = requests.post(
                f"{BASE_URL}/api/auth/login/admin",
                json=ADMIN_CREDENTIALS,
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                TestRiskAdminEndpoints.token = data.get("access_token") or data.get("token")
            else:
                pytest.skip(f"Admin login failed: {response.status_code}")
    
    def _headers(self):
        return {"Authorization": f"Bearer {TestRiskAdminEndpoints.token}"}
    
    def test_get_risk_config(self):
        """GET /api/admin/risk/config - Risk config alınabilmeli"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk/config",
            headers=self._headers(),
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields
        required_fields = [
            "max_risk_per_trade_pct",
            "max_total_exposure_pct",
            "max_symbol_exposure_pct",
            "max_cluster_exposure_pct",
            "max_leverage",
            "stale_data_threshold_ms",
            "spread_threshold_bps",
            "execution_quality_threshold",
            "max_daily_loss_pct",
            "max_consecutive_losses",
            "symbol_cooldown_minutes",
            "strategy_cooldown_minutes",
            "global_cooldown_minutes",
            "kill_switch_enabled"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Type checks
        assert isinstance(data["max_risk_per_trade_pct"], (int, float))
        assert isinstance(data["max_leverage"], int)
        assert isinstance(data["kill_switch_enabled"], bool)
        print(f"Risk config retrieved successfully with {len(data)} fields")
    
    def test_patch_risk_config(self):
        """PATCH /api/admin/risk/config - Risk config güncellenebilmeli"""
        # First get current config
        current = requests.get(
            f"{BASE_URL}/api/admin/risk/config",
            headers=self._headers(),
            timeout=30
        ).json()
        
        # Update a value
        original_value = current.get("max_risk_per_trade_pct", 2.0)
        new_value = 2.5 if original_value != 2.5 else 2.0
        
        response = requests.patch(
            f"{BASE_URL}/api/admin/risk/config",
            headers=self._headers(),
            json={"max_risk_per_trade_pct": new_value},
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["max_risk_per_trade_pct"] == new_value
        assert "updated_at" in data
        
        # Revert to original
        requests.patch(
            f"{BASE_URL}/api/admin/risk/config",
            headers=self._headers(),
            json={"max_risk_per_trade_pct": original_value},
            timeout=30
        )
        print(f"Risk config patched: max_risk_per_trade_pct {original_value} -> {new_value} -> {original_value}")
    
    def test_reload_risk_config(self):
        """POST /api/admin/risk/config/reload - Config reload edilebilmeli"""
        response = requests.post(
            f"{BASE_URL}/api/admin/risk/config/reload",
            headers=self._headers(),
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "max_risk_per_trade_pct" in data
        assert "updated_at" in data
        print("Risk config reload successful")
    
    def test_get_risk_status(self):
        """GET /api/admin/risk/status - Risk status alınabilmeli"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk/status",
            headers=self._headers(),
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields
        required_fields = [
            "config",
            "total_exposure",
            "symbol_exposure",
            "cluster_exposure",
            "kill_switch_state",
            "generated_at"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Check kill_switch_state structure
        ks = data.get("kill_switch_state", {})
        assert "risk_kill_switch_enabled" in ks
        assert "pipeline_kill_switch_active" in ks
        
        print(f"Risk status: total_exposure={data['total_exposure']}, kill_switch_state={ks}")
    
    def test_kill_switch_config_toggle(self):
        """Kill switch enabled/disabled toggle davranışı"""
        # Get current state
        current = requests.get(
            f"{BASE_URL}/api/admin/risk/config",
            headers=self._headers(),
            timeout=30
        ).json()
        
        original_value = current.get("kill_switch_enabled", False)
        
        # Toggle kill switch
        new_value = not original_value
        response = requests.patch(
            f"{BASE_URL}/api/admin/risk/config",
            headers=self._headers(),
            json={"kill_switch_enabled": new_value},
            timeout=30
        )
        assert response.status_code == 200
        assert response.json()["kill_switch_enabled"] == new_value
        
        # Verify in status
        status_response = requests.get(
            f"{BASE_URL}/api/admin/risk/status",
            headers=self._headers(),
            timeout=30
        )
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["kill_switch_state"]["risk_kill_switch_enabled"] == new_value
        
        # Revert
        requests.patch(
            f"{BASE_URL}/api/admin/risk/config",
            headers=self._headers(),
            json={"kill_switch_enabled": original_value},
            timeout=30
        )
        print(f"Kill switch toggled: {original_value} -> {new_value} -> {original_value}")


class TestRiskEngineRuntimeIntegration:
    """Runtime ve Scanner içinde Risk Engine Bloğu Testleri"""
    
    token = None
    user_id = None
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get user for scanner tests"""
        if TestRiskEngineRuntimeIntegration.token is None:
            response = requests.post(
                f"{BASE_URL}/api/auth/login/admin",
                json=ADMIN_CREDENTIALS,
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                TestRiskEngineRuntimeIntegration.token = data.get("access_token") or data.get("token")
                TestRiskEngineRuntimeIntegration.user_id = data.get("user", {}).get("id")
            else:
                pytest.skip(f"Admin login failed: {response.status_code}")
    
    def _headers(self):
        return {"Authorization": f"Bearer {TestRiskEngineRuntimeIntegration.token}"}
    
    def test_runtime_summary_contains_risk_overview(self):
        """Admin runtime-summary içinde risk_overview alanı olmalı"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-summary",
            headers=self._headers(),
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Check if risk_overview exists in the response
        assert "risk_overview" in data, "risk_overview field missing from runtime-summary"
        
        risk = data["risk_overview"]
        # Verify risk_overview structure matches build_admin_risk_status
        expected_fields = ["config", "total_exposure", "kill_switch_state", "generated_at"]
        for field in expected_fields:
            assert field in risk, f"Missing field in risk_overview: {field}"
        
        print(f"Risk overview found: keys={list(risk.keys())[:10]}")
    
    def test_scanner_runtime_contains_risk_engine_block(self):
        """Scanner runtime response içinde risk_engine bloğu olmalı"""
        # Use admin endpoint to get latest scan
        response = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-latest-scan",
            headers=self._headers(),
            timeout=60
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check for risk_engine block (may be empty if no recent scans)
        if "risk_engine" in data:
            risk_engine = data["risk_engine"]
            # Verify risk_engine contract
            expected_fields = [
                "decision_distribution",
                "veto_count",
                "reduce_size_count"
            ]
            for field in expected_fields:
                assert field in risk_engine, f"Missing field in risk_engine: {field}"
            
            # Verify decision_distribution
            dd = risk_engine.get("decision_distribution", {})
            assert "ALLOW" in dd or "PASS" in dd or "BLOCK" in dd or "REDUCE_SIZE" in dd
            
            print(f"Risk engine block: decision_distribution={dd}, veto={risk_engine.get('veto_count')}, reduce={risk_engine.get('reduce_size_count')}")
        else:
            # No recent scan, check structure is correct
            print(f"No recent scan - risk_engine block not present. Keys: {list(data.keys())[:10]}")
    
    def test_scanner_runtime_risk_action_distribution(self):
        """Risk action distribution: ALLOW/REDUCE_SIZE/PASS/BLOCK"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-latest-scan",
            headers=self._headers(),
            timeout=60
        )
        assert response.status_code == 200
        
        data = response.json()
        
        if "risk_engine" in data:
            risk_engine = data.get("risk_engine", {})
            dd = risk_engine.get("decision_distribution", {})
            
            # All 4 actions should be represented (even if 0)
            valid_actions = {"ALLOW", "REDUCE_SIZE", "PASS", "BLOCK"}
            for action in valid_actions:
                assert action in dd, f"Missing action in distribution: {action}"
                assert isinstance(dd[action], int), f"{action} should be int"
            
            # Verify veto = PASS + BLOCK
            veto_count = risk_engine.get("veto_count", 0)
            expected_veto = dd.get("PASS", 0) + dd.get("BLOCK", 0)
            assert veto_count == expected_veto, f"veto_count mismatch: {veto_count} != {expected_veto}"
            
            # Verify reduce = REDUCE_SIZE
            reduce_count = risk_engine.get("reduce_size_count", 0)
            expected_reduce = dd.get("REDUCE_SIZE", 0)
            assert reduce_count == expected_reduce, f"reduce_size_count mismatch: {reduce_count} != {expected_reduce}"
            
            print(f"Action distribution verified: {dd}")
        else:
            print("No recent scan - skipping action distribution check")
    
    def test_explainability_summary_risk_fields(self):
        """Explainability summary içinde risk fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-latest-scan",
            headers=self._headers(),
            timeout=60
        )
        assert response.status_code == 200
        
        data = response.json()
        expl = data.get("explainability_summary", {})
        
        if expl:
            # Check risk-related fields
            assert "risk_filtered_count" in expl, "Missing risk_filtered_count"
            assert "risk_veto_count" in expl, "Missing risk_veto_count"
            assert "risk_reduce_count" in expl, "Missing risk_reduce_count"
            
            print(f"Explainability risk fields: filtered={expl.get('risk_filtered_count')}, veto={expl.get('risk_veto_count')}, reduce={expl.get('risk_reduce_count')}")
        else:
            print("No recent scan - explainability_summary empty")


class TestExposureLimits:
    """Exposure limit testleri - Portfolio/Symbol/Cluster"""
    
    token = None
    
    @pytest.fixture(autouse=True)
    def setup(self):
        if TestExposureLimits.token is None:
            response = requests.post(
                f"{BASE_URL}/api/auth/login/admin",
                json=ADMIN_CREDENTIALS,
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                TestExposureLimits.token = data.get("access_token") or data.get("token")
            else:
                pytest.skip(f"Admin login failed: {response.status_code}")
    
    def _headers(self):
        return {"Authorization": f"Bearer {TestExposureLimits.token}"}
    
    def test_exposure_limits_in_config(self):
        """Config içinde exposure limit alanları"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk/config",
            headers=self._headers(),
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Portfolio level
        assert "max_total_exposure_pct" in data
        assert data["max_total_exposure_pct"] > 0
        
        # Symbol level
        assert "max_symbol_exposure_pct" in data
        assert data["max_symbol_exposure_pct"] > 0
        
        # Cluster level
        assert "max_cluster_exposure_pct" in data
        assert data["max_cluster_exposure_pct"] > 0
        
        print(f"Exposure limits: total={data['max_total_exposure_pct']}%, symbol={data['max_symbol_exposure_pct']}%, cluster={data['max_cluster_exposure_pct']}%")
    
    def test_exposure_in_status(self):
        """Status içinde exposure breakdown"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk/status",
            headers=self._headers(),
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        
        assert "total_exposure" in data
        assert "symbol_exposure" in data
        assert "cluster_exposure" in data
        
        # symbol_exposure should be a list of dicts
        if data["symbol_exposure"]:
            se = data["symbol_exposure"][0]
            assert "symbol" in se
            assert "exposure_usdt" in se
        
        # cluster_exposure should be a list of dicts
        if data["cluster_exposure"]:
            ce = data["cluster_exposure"][0]
            assert "cluster" in ce
            assert "exposure_usdt" in ce
        
        print(f"Exposure status: total={data['total_exposure']}, symbols={len(data['symbol_exposure'])}, clusters={len(data['cluster_exposure'])}")


class TestCooldownBehavior:
    """Daily loss + Consecutive loss + Cooldown davranışı"""
    
    token = None
    
    @pytest.fixture(autouse=True)
    def setup(self):
        if TestCooldownBehavior.token is None:
            response = requests.post(
                f"{BASE_URL}/api/auth/login/admin",
                json=ADMIN_CREDENTIALS,
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                TestCooldownBehavior.token = data.get("access_token") or data.get("token")
            else:
                pytest.skip(f"Admin login failed: {response.status_code}")
    
    def _headers(self):
        return {"Authorization": f"Bearer {TestCooldownBehavior.token}"}
    
    def test_cooldown_config_fields(self):
        """Cooldown config alanları"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk/config",
            headers=self._headers(),
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Daily loss
        assert "max_daily_loss_pct" in data
        assert data["max_daily_loss_pct"] > 0
        
        # Consecutive losses
        assert "max_consecutive_losses" in data
        assert data["max_consecutive_losses"] > 0
        
        # Cooldown minutes
        assert "symbol_cooldown_minutes" in data
        assert "strategy_cooldown_minutes" in data
        assert "global_cooldown_minutes" in data
        
        print(f"Cooldown config: daily_loss={data['max_daily_loss_pct']}%, consec_loss={data['max_consecutive_losses']}, cooldowns: symbol={data['symbol_cooldown_minutes']}m, strategy={data['strategy_cooldown_minutes']}m, global={data['global_cooldown_minutes']}m")
    
    def test_cooldown_state_in_status(self):
        """Status içinde cooldown state"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk/status",
            headers=self._headers(),
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        
        assert "cooldown_state" in data
        assert "daily_loss" in data
        
        print(f"Cooldown state: {data.get('cooldown_state')}, daily_loss: {data.get('daily_loss')}")


class TestStaleSpreadVeto:
    """Stale data ve Spread veto davranışı"""
    
    token = None
    
    @pytest.fixture(autouse=True)
    def setup(self):
        if TestStaleSpreadVeto.token is None:
            response = requests.post(
                f"{BASE_URL}/api/auth/login/admin",
                json=ADMIN_CREDENTIALS,
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                TestStaleSpreadVeto.token = data.get("access_token") or data.get("token")
            else:
                pytest.skip(f"Admin login failed: {response.status_code}")
    
    def _headers(self):
        return {"Authorization": f"Bearer {TestStaleSpreadVeto.token}"}
    
    def test_stale_spread_config_fields(self):
        """Stale/Spread config alanları"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk/config",
            headers=self._headers(),
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        
        assert "stale_data_threshold_ms" in data
        assert data["stale_data_threshold_ms"] > 0
        
        assert "spread_threshold_bps" in data
        assert data["spread_threshold_bps"] > 0
        
        assert "execution_quality_threshold" in data
        assert data["execution_quality_threshold"] > 0
        
        assert "max_slippage_pct" in data
        assert data["max_slippage_pct"] > 0
        
        print(f"Stale/Spread config: stale={data['stale_data_threshold_ms']}ms, spread={data['spread_threshold_bps']}bps, quality={data['execution_quality_threshold']}, slippage={data['max_slippage_pct']}%")
    
    def test_stale_reject_count_in_status(self):
        """Status içinde stale/spread reject counts"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk/status",
            headers=self._headers(),
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        
        assert "stale_reject_count" in data
        assert "spread_reject_count" in data
        assert "execution_quality_warning" in data
        
        print(f"Reject counts: stale={data['stale_reject_count']}, spread={data['spread_reject_count']}, quality_warn={data['execution_quality_warning']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
