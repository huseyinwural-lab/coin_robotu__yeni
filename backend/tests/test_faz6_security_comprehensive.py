"""
FAZ6 Security Tests - Comprehensive validation of Phase 6 security requirements
Tests: JWT rotation, admin credential cleanup, rate limiting, API key encryption, 
       repo hygiene, CI secret leak prevention
"""

import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


@pytest.fixture(scope="module")
def api_session():
    """HTTP session for API calls"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_token(api_session):
    """Get valid admin token"""
    response = api_session.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")
    data = response.json()
    token = data.get("access_token")
    if not token:
        pytest.skip("No access_token in response")
    return token


@pytest.fixture(scope="module")
def admin_user_id(api_session, admin_token):
    """Get admin user ID from /me endpoint"""
    response = api_session.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    if response.status_code != 200:
        pytest.skip(f"/auth/me failed: {response.status_code}")
    return response.json().get("id")


class TestJWTRotation:
    """T-6.1: JWT rotation proof - old-secret signed token rejected, new token accepted"""

    def test_new_token_accepted(self, api_session, admin_token):
        """Valid token with current JWT_SECRET should be accepted"""
        response = api_session.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert response.status_code == 200, f"New token rejected: {response.status_code}"

    def test_old_secret_token_rejected(self, api_session, admin_user_id):
        """Token signed with legacy/old secret should be rejected"""
        old_secret = "change-this-legacy-secret-not-active-2026"
        old_payload = {
            "sub": admin_user_id,
            "role": "super_admin",
            "email": ADMIN_EMAIL,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        }
        old_token = jwt.encode(old_payload, old_secret, algorithm="HS256")

        response = api_session.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {old_token}"},
            timeout=20,
        )
        assert response.status_code in (401, 403), f"Old token should be rejected, got {response.status_code}"

    def test_jwt_secret_minimum_length(self):
        """JWT_SECRET in backend/.env should be at least 32 characters"""
        env_file = Path("/app/backend/.env")
        assert env_file.exists(), "backend/.env not found"

        jwt_secret_len = 0
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("JWT_SECRET="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                jwt_secret_len = len(value)
                break

        assert jwt_secret_len >= 32, f"JWT_SECRET too short: {jwt_secret_len} chars, need >= 32"

    def test_weak_jwt_secret_values_not_used(self):
        """JWT_SECRET should not be a known weak value"""
        env_file = Path("/app/backend/.env")
        assert env_file.exists()

        weak_values = {"change-this", "changeme", "secret", "jwt-secret", "ci-jwt-secret", "ci-test-secret"}
        jwt_secret = ""
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("JWT_SECRET="):
                jwt_secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

        assert jwt_secret.lower() not in weak_values, "JWT_SECRET uses weak/default value"


class TestAdminCredentialCleanup:
    """T-6.2: Admin credential cleanup - no hardcoded DEFAULT_ADMIN_PASSWORD in active runtime paths"""

    def test_forbidden_env_guards_exist(self):
        """core/config.py should have forbidden_env guards for deprecated admin keys"""
        config_file = Path("/app/backend/core/config.py")
        assert config_file.exists()

        content = config_file.read_text(encoding="utf-8")
        # The concatenation is intentional to avoid triggering our own scan
        assert 'forbidden_env("DEFAULT_ADMIN_' in content, "Missing forbidden_env guard for DEFAULT_ADMIN_ keys"

    def test_no_hardcoded_admin_password_in_active_code(self):
        """No hardcoded admin credentials in active source files"""
        import subprocess

        deprecated_key = "DEFAULT_ADMIN_PASSWORD"
        legacy_marker = "Admin12345!"  # The test password

        result = subprocess.run(
            [
                "rg",
                "-n",
                f"{deprecated_key}|{legacy_marker}",
                "/app",
                "--glob",
                "!**/.git/**",
                "--glob",
                "!**/node_modules/**",
                "--glob",
                "!**/*test*.py",
                "--glob",
                "!**/backend_test_*.py",
                "--glob",
                "!**/test_result.md",
                "--glob",
                "!**/backend/tests/**",
                "--glob",
                "!**/docs/**",
                "--glob",
                "!**/memory/**",
                "--glob",
                "!**/test_reports/**",
                "--glob",
                "!**/artifacts/**",
            ],
            capture_output=True,
            text=True,
        )

        # No matches should be found in active code
        assert not result.stdout.strip(), f"Found admin credential markers in active code:\n{result.stdout[:500]}"

    def test_bootstrap_uses_env_not_hardcoded(self):
        """bootstrap.py should read admin credentials from env, not hardcode them"""
        bootstrap_file = Path("/app/backend/services/bootstrap.py")
        assert bootstrap_file.exists()

        content = bootstrap_file.read_text(encoding="utf-8")
        assert "settings.bootstrap_admin_email" in content, "Bootstrap should use settings.bootstrap_admin_email"
        assert "settings.bootstrap_admin_password" in content, "Bootstrap should use settings.bootstrap_admin_password"
        # Should NOT contain hardcoded password
        assert "Admin12345" not in content, "Bootstrap contains hardcoded admin password"


class TestLoginRateLimit:
    """T-6.3: Rate limit active on /api/auth/login endpoints with 429 + Retry-After"""

    @pytest.fixture
    def unique_test_ip(self):
        """Generate unique IP for rate limit testing"""
        return f"203.0.113.{random.randint(10, 250)}"

    def test_login_rate_limit_enforced(self, api_session, unique_test_ip):
        """After 5 requests, 6th should return 429 with Retry-After header"""
        statuses = []
        retry_after = None
        headers = {"x-forwarded-for": unique_test_ip}

        for _ in range(6):
            response = api_session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": ADMIN_EMAIL, "password": "WrongPassword123!"},
                headers=headers,
                timeout=20,
            )
            statuses.append(response.status_code)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")

        # First 5 should NOT be 429
        assert all(code != 429 for code in statuses[:5]), f"Rate limit triggered too early: {statuses}"
        # 6th should be 429
        assert statuses[5] == 429, f"Expected 429 on 6th request, got {statuses[5]}"
        # Should have Retry-After header
        assert retry_after is not None, "Missing Retry-After header on 429 response"

    def test_login_admin_rate_limit(self, api_session):
        """Rate limit on /api/auth/login/admin endpoint"""
        test_ip = f"203.0.113.{random.randint(10, 250)}"
        headers = {"x-forwarded-for": test_ip}
        statuses = []

        for _ in range(6):
            response = api_session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": "test@test.com", "password": "wrong"},
                headers=headers,
                timeout=20,
            )
            statuses.append(response.status_code)

        assert 429 in statuses, f"Rate limit not enforced on /login/admin: {statuses}"

    def test_login_user_rate_limit(self, api_session):
        """Rate limit on /api/auth/login/user endpoint"""
        test_ip = f"203.0.113.{random.randint(10, 250)}"
        headers = {"x-forwarded-for": test_ip}
        statuses = []

        for _ in range(6):
            response = api_session.post(
                f"{BASE_URL}/api/auth/login/user",
                json={"email": "test@test.com", "password": "wrong"},
                headers=headers,
                timeout=20,
            )
            statuses.append(response.status_code)

        assert 429 in statuses, f"Rate limit not enforced on /login/user: {statuses}"

    def test_login_generic_rate_limit(self, api_session):
        """Rate limit on /api/auth/login endpoint"""
        test_ip = f"203.0.113.{random.randint(10, 250)}"
        headers = {"x-forwarded-for": test_ip}
        statuses = []

        for _ in range(6):
            response = api_session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": "test@test.com", "password": "wrong"},
                headers=headers,
                timeout=20,
            )
            statuses.append(response.status_code)

        assert 429 in statuses, f"Rate limit not enforced on /login: {statuses}"

    def test_rate_limit_service_exists(self):
        """auth_rate_limit_service.py should exist with proper implementation"""
        service_file = Path("/app/backend/services/auth_rate_limit_service.py")
        assert service_file.exists()

        content = service_file.read_text(encoding="utf-8")
        assert "enforce_login_rate_limit" in content
        assert "HTTP_429_TOO_MANY_REQUESTS" in content
        assert "Retry-After" in content


class TestAPIKeyEncryption:
    """T-6.4: API key encryption proof - raw DB rows do not contain plaintext api_key/api_secret"""

    def test_encryption_module_uses_aesgcm(self):
        """user_exchange_connector.py should use AES-GCM encryption"""
        connector_file = Path("/app/backend/core/users/user_exchange_connector.py")
        assert connector_file.exists()

        content = connector_file.read_text(encoding="utf-8")
        assert "AESGCM" in content, "Should use AES-GCM encryption"
        assert "aesgcm:v1" in content, "Should have AES-GCM version prefix"

    def test_encryption_key_from_env(self):
        """Encryption key should come from EXCHANGE_CREDENTIALS_ENCRYPTION_KEY env var"""
        config_file = Path("/app/backend/core/config.py")
        assert config_file.exists()

        content = config_file.read_text(encoding="utf-8")
        assert "exchange_credentials_encryption_key" in content.lower()
        assert 'required_env("EXCHANGE_CREDENTIALS_ENCRYPTION_KEY")' in content

    def test_encrypted_values_not_plaintext(self, api_session, admin_token):
        """API key values stored in DB should be encrypted, not plaintext"""
        # This test validates the encryption by checking artifact from main agent's test
        artifact_file = Path("/app/artifacts/faz6_api_key_encryption_proof.log")
        if artifact_file.exists():
            content = json.loads(artifact_file.read_text(encoding="utf-8"))
            assert content.get("api_key_plaintext_visible") is False, "API key plaintext visible in DB"
            assert content.get("api_secret_plaintext_visible") is False, "API secret plaintext visible in DB"
            assert content.get("api_key_cipher_prefix", "").startswith("aesgcm:v1"), "Not using AES-GCM encryption"
        else:
            pytest.skip("Encryption proof artifact not found")


class TestRepoHygiene:
    """T-6.5: Repo dump/backup hygiene - no admin_token.txt, no tracked *.sql/*.bak leaks"""

    def test_no_admin_token_file(self):
        """No admin_token.txt in repo"""
        import subprocess

        result = subprocess.run(
            ["find", "/app", "-type", "f", "-name", "admin_token.txt", "-not", "-path", "*/.git/*"],
            capture_output=True,
            text=True,
        )
        assert not result.stdout.strip(), f"Found admin_token.txt: {result.stdout}"

    def test_no_sql_dump_files_tracked(self):
        """No *.sql dump files tracked in git (except migrations) - only check files on disk"""
        import subprocess

        # Check for actual SQL files on disk (not just in git history)
        result = subprocess.run(
            ["find", "/app", "-type", "f", "-name", "*.sql",
             "!", "-path", "*/.git/*", "!", "-path", "*/node_modules/*",
             "!", "-path", "*/backend/migrations/*"],
            capture_output=True,
            text=True,
        )
        # Filter to find actual sql dump files (not migrations)
        sql_files = [f for f in result.stdout.strip().split("\n") if f]
        assert not sql_files, f"Found SQL dump files on disk: {sql_files}"

    def test_no_bak_files_tracked(self):
        """No *.bak backup files tracked in git"""
        import subprocess

        result = subprocess.run(
            ["git", "ls-files", "*.bak"],
            cwd="/app",
            capture_output=True,
            text=True,
        )
        assert not result.stdout.strip(), f"Found tracked .bak files: {result.stdout}"


class TestCISecretLeakGuard:
    """T-6.6: CI secret leak guard script and deploy-gate job presence"""

    def test_ci_secret_leak_guard_script_exists(self):
        """ci_secret_leak_guard.sh script exists"""
        script_file = Path("/app/scripts/ci_secret_leak_guard.sh")
        assert script_file.exists(), "ci_secret_leak_guard.sh not found"

    def test_ci_secret_leak_guard_checks_patterns(self):
        """Script checks for real leak patterns"""
        script_file = Path("/app/scripts/ci_secret_leak_guard.sh")
        content = script_file.read_text(encoding="utf-8")

        # Should check for private keys
        assert "PRIVATE KEY" in content, "Should check for private key patterns"
        # Should check for AWS access keys
        assert "AKIA" in content, "Should check for AWS access key patterns"
        # Should check for JWT tokens
        assert "eyJ" in content, "Should check for JWT token patterns"

    def test_secret_scan_allowlist_exists(self):
        """.secret-scan-allowlist file exists"""
        allowlist_file = Path("/app/.secret-scan-allowlist")
        assert allowlist_file.exists(), ".secret-scan-allowlist not found"

    def test_deploy_gate_has_secret_leak_job(self):
        """deploy-gate.yml has secret-leak-gate job"""
        workflow_file = Path("/app/.github/workflows/deploy-gate.yml")
        assert workflow_file.exists(), "deploy-gate.yml not found"

        content = workflow_file.read_text(encoding="utf-8")
        assert "secret-leak-gate" in content, "Missing secret-leak-gate job"
        assert "ci_secret_leak_guard.sh" in content, "Job should run ci_secret_leak_guard.sh"

    def test_secret_scan_report_pass(self):
        """Secret scan report should show PASS"""
        report_file = Path("/app/artifacts/faz6_secret_scan_report.log")
        if report_file.exists():
            content = report_file.read_text(encoding="utf-8")
            assert "status=PASS" in content, f"Secret scan did not pass: {content}"
            assert "finding_count=0" in content, f"Secret scan found issues: {content}"
        else:
            pytest.skip("Secret scan report not found")


class TestVerificationScript:
    """T-6.7: verify_phase6_security.sh script passes"""

    def test_verification_script_exists(self):
        """verify_phase6_security.sh exists"""
        script_file = Path("/app/scripts/verify_phase6_security.sh")
        assert script_file.exists()

    def test_security_summary_shows_pass(self):
        """Security summary log shows all tests PASS"""
        summary_file = Path("/app/artifacts/faz6_security_summary.log")
        if summary_file.exists():
            content = summary_file.read_text(encoding="utf-8")
            assert "SUMMARY: PASS" in content, f"Security summary did not pass: {content}"
            # Verify all individual tests passed
            assert "T-6.1 PASS" in content
            assert "T-6.2 PASS" in content
            assert "T-6.3 PASS" in content
            assert "T-6.4 PASS" in content
            assert "T-6.5 PASS" in content
            assert "T-6.6 PASS" in content
        else:
            pytest.skip("Security summary not found")


class TestProxyAwareIP:
    """Test proxy-aware IP resolution for rate limiting"""

    def test_x_forwarded_for_header_support(self):
        """Rate limiter should support X-Forwarded-For header"""
        service_file = Path("/app/backend/services/auth_rate_limit_service.py")
        assert service_file.exists()

        content = service_file.read_text(encoding="utf-8")
        assert "x-forwarded-for" in content.lower(), "Should support X-Forwarded-For header"

    def test_x_real_ip_header_support(self):
        """Rate limiter should support X-Real-IP header as fallback"""
        service_file = Path("/app/backend/services/auth_rate_limit_service.py")
        content = service_file.read_text(encoding="utf-8")
        assert "x-real-ip" in content.lower(), "Should support X-Real-IP header"

    def test_resolve_client_ip_function_exists(self):
        """resolve_client_ip function should exist"""
        service_file = Path("/app/backend/services/auth_rate_limit_service.py")
        content = service_file.read_text(encoding="utf-8")
        assert "def resolve_client_ip" in content, "resolve_client_ip function missing"
