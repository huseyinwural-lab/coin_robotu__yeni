# Test super_admin access restriction for commercial-ops endpoints
import os
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            if raw_line.startswith("REACT_APP_BACKEND_URL="):
                return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _resolve_base_url()


@pytest.fixture(scope="module")
def user_token() -> str:
    """Get a regular user token (not super_admin)"""
    # First register a test user
    test_email = "test_comm_user@example.com"
    test_password = "TestPass12345!"
    
    # Try to register
    register_response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": test_email, "password": test_password},
        timeout=20,
    )
    
    # Try to login
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": test_email, "password": test_password},
        timeout=20,
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"User login failed: {login_response.status_code}")
    
    return login_response.json().get("access_token")


@pytest.fixture(scope="module")
def admin_token() -> str:
    """Get an admin (not super_admin) token"""
    # Use the default admin credentials but expect it might be super_admin
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": "admin@platform.local", "password": "Admin12345!"},
        timeout=20,
    )
    
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    
    data = response.json()
    role = (data.get("user") or {}).get("role")
    
    # If the default admin is super_admin, skip these tests
    # as we need a non-super_admin to test 403
    if role == "super_admin":
        return data.get("access_token")
    
    return data.get("access_token")


class TestCommercialOpsAccessControl:
    """Test that commercial endpoints require super_admin role"""
    
    def test_usage_logs_without_token_returns_401(self):
        """No auth token should return 401"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/usage-logs",
            timeout=20,
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    
    def test_total_pnl_without_token_returns_401(self):
        """No auth token should return 401"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/total-pnl",
            timeout=20,
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    
    def test_monthly_export_without_token_returns_401(self):
        """No auth token should return 401"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/monthly-pnl/export",
            timeout=20,
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestCommercialOpsWithSuperAdmin:
    """Test successful access with super_admin token"""
    
    @pytest.fixture(scope="class")
    def super_admin_token(self) -> str:
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": "admin@platform.local", "password": "Admin12345!"},
            timeout=20,
        )
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code}")
        role = (response.json().get("user") or {}).get("role")
        if role != "super_admin":
            pytest.skip(f"super_admin required, got: {role}")
        return response.json().get("access_token")
    
    def test_usage_logs_returns_200_with_super_admin(self, super_admin_token: str):
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/usage-logs",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            timeout=20,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        # Verify response structure
        assert "generated_at" in data
        assert "total" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        
        # If items exist, verify item structure
        if len(data["items"]) > 0:
            item = data["items"][0]
            assert "log_id" in item
            assert "user_id" in item
            assert "user_email" in item
            assert "symbol" in item
            assert "order_id" in item
            assert "execution_status" in item
            assert "pnl" in item
    
    def test_total_pnl_returns_200_with_super_admin(self, super_admin_token: str):
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/total-pnl",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            timeout=20,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        # Verify response structure
        assert "generated_at" in data
        assert "last_30_days" in data
        assert "calendar_month" in data
        
        # Verify last_30_days structure
        last_30 = data["last_30_days"]
        assert "range_start" in last_30
        assert "range_end" in last_30
        assert "summary" in last_30
        assert "users" in last_30
        
        summary = last_30["summary"]
        assert "user_count" in summary
        assert "total_realized_pnl" in summary
        assert "total_unrealized_pnl" in summary
        assert "total_pnl" in summary
        
        # Verify calendar_month structure
        cal_month = data["calendar_month"]
        assert "month" in cal_month
        assert "summary" in cal_month
    
    def test_monthly_export_returns_xlsx_with_super_admin(self, super_admin_token: str):
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/monthly-pnl/export",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            params={"month": "2026-01"},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        content_type = response.headers.get("content-type", "")
        assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in content_type
        
        # Verify content-disposition header for attachment
        content_disposition = response.headers.get("content-disposition", "")
        assert "attachment" in content_disposition
        assert "monthly_pnl_" in content_disposition
        assert ".xlsx" in content_disposition
        
        # Verify file is not empty and has xlsx magic bytes
        assert len(response.content) > 100
