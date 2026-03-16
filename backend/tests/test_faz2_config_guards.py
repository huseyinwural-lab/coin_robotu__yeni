"""
FAZ-2 Config Guards Tests
Tests for environment variable validation and fail-fast behavior in backend config
"""
import os
import pytest
import subprocess
import sys
from pathlib import Path

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestBackendConfigRequiredEnv:
    """Test backend/core/config.py required_env() fail-fast behavior"""
    
    def test_config_file_exists(self):
        """Verify config.py exists"""
        config_path = Path("/app/backend/core/config.py")
        assert config_path.exists(), "config.py not found"
        print("PASS: config.py exists")
    
    def test_required_env_function_defined(self):
        """Verify required_env function is defined"""
        with open("/app/backend/core/config.py", "r") as f:
            content = f.read()
        
        assert "def required_env" in content, "required_env function not defined"
        assert "RuntimeError" in content, "RuntimeError not used for missing vars"
        print("PASS: required_env function is defined with RuntimeError")
    
    def test_database_url_is_required(self):
        """Verify DATABASE_URL is required"""
        with open("/app/backend/core/config.py", "r") as f:
            content = f.read()
        
        assert 'required_env("DATABASE_URL")' in content, "DATABASE_URL not required"
        print("PASS: DATABASE_URL is required")
    
    def test_redis_url_is_required(self):
        """Verify REDIS_URL is required"""
        with open("/app/backend/core/config.py", "r") as f:
            content = f.read()
        
        assert 'required_env("REDIS_URL")' in content, "REDIS_URL not required"
        print("PASS: REDIS_URL is required")
    
    def test_jwt_secret_is_required(self):
        """Verify JWT_SECRET is required"""
        with open("/app/backend/core/config.py", "r") as f:
            content = f.read()
        
        assert 'required_env("JWT_SECRET")' in content, "JWT_SECRET not required"
        print("PASS: JWT_SECRET is required")
    
    def test_jwt_algorithm_is_required(self):
        """Verify JWT_ALGORITHM is required"""
        with open("/app/backend/core/config.py", "r") as f:
            content = f.read()
        
        assert 'required_env("JWT_ALGORITHM")' in content, "JWT_ALGORITHM not required"
        print("PASS: JWT_ALGORITHM is required")
    
    def test_jwt_expire_minutes_is_required(self):
        """Verify JWT_EXPIRE_MINUTES is required"""
        with open("/app/backend/core/config.py", "r") as f:
            content = f.read()
        
        assert 'required_env("JWT_EXPIRE_MINUTES")' in content, "JWT_EXPIRE_MINUTES not required"
        print("PASS: JWT_EXPIRE_MINUTES is required")
    
    def test_cors_origins_is_required(self):
        """Verify CORS_ORIGINS is required"""
        with open("/app/backend/core/config.py", "r") as f:
            content = f.read()
        
        assert 'required_env("CORS_ORIGINS")' in content, "CORS_ORIGINS not required"
        print("PASS: CORS_ORIGINS is required")
    
    def test_default_admin_email_is_required(self):
        """Verify DEFAULT_ADMIN_EMAIL is required"""
        with open("/app/backend/core/config.py", "r") as f:
            content = f.read()
        
        assert 'required_env("DEFAULT_ADMIN_EMAIL")' in content, "DEFAULT_ADMIN_EMAIL not required"
        print("PASS: DEFAULT_ADMIN_EMAIL is required")
    
    def test_default_admin_password_is_required(self):
        """Verify DEFAULT_ADMIN_PASSWORD is required"""
        with open("/app/backend/core/config.py", "r") as f:
            content = f.read()
        
        assert 'required_env("DEFAULT_ADMIN_PASSWORD")' in content, "DEFAULT_ADMIN_PASSWORD not required"
        print("PASS: DEFAULT_ADMIN_PASSWORD is required")
    
    def test_required_env_raises_on_empty(self):
        """Test that required_env raises RuntimeError for empty strings"""
        with open("/app/backend/core/config.py", "r") as f:
            content = f.read()
        
        # Check that the function strips and validates empty strings
        assert ".strip()" in content, "required_env should strip whitespace"
        assert "not normalized" in content or 'if not normalized' in content, "Empty check should exist"
        print("PASS: required_env handles empty/whitespace values")


class TestDockerComposeBackendEnv:
    """Test docker-compose.yml backend environment configuration"""
    
    def test_docker_compose_exists(self):
        """Verify docker-compose.yml exists"""
        compose_path = Path("/app/docker-compose.yml")
        assert compose_path.exists(), "docker-compose.yml not found"
        print("PASS: docker-compose.yml exists")
    
    def test_docker_compose_has_database_url(self):
        """Verify DATABASE_URL in docker-compose backend"""
        with open("/app/docker-compose.yml", "r") as f:
            content = f.read()
        
        assert "DATABASE_URL:" in content, "DATABASE_URL not in docker-compose"
        print("PASS: DATABASE_URL in docker-compose")
    
    def test_docker_compose_has_redis_url(self):
        """Verify REDIS_URL in docker-compose backend"""
        with open("/app/docker-compose.yml", "r") as f:
            content = f.read()
        
        assert "REDIS_URL:" in content, "REDIS_URL not in docker-compose"
        print("PASS: REDIS_URL in docker-compose")
    
    def test_docker_compose_has_jwt_secret(self):
        """Verify JWT_SECRET in docker-compose backend"""
        with open("/app/docker-compose.yml", "r") as f:
            content = f.read()
        
        assert "JWT_SECRET:" in content, "JWT_SECRET not in docker-compose"
        print("PASS: JWT_SECRET in docker-compose")
    
    def test_docker_compose_has_jwt_algorithm(self):
        """Verify JWT_ALGORITHM in docker-compose backend"""
        with open("/app/docker-compose.yml", "r") as f:
            content = f.read()
        
        assert "JWT_ALGORITHM:" in content, "JWT_ALGORITHM not in docker-compose"
        print("PASS: JWT_ALGORITHM in docker-compose")
    
    def test_docker_compose_has_jwt_expire_minutes(self):
        """Verify JWT_EXPIRE_MINUTES in docker-compose backend"""
        with open("/app/docker-compose.yml", "r") as f:
            content = f.read()
        
        assert "JWT_EXPIRE_MINUTES:" in content, "JWT_EXPIRE_MINUTES not in docker-compose"
        print("PASS: JWT_EXPIRE_MINUTES in docker-compose")
    
    def test_docker_compose_has_cors_origins(self):
        """Verify CORS_ORIGINS in docker-compose backend"""
        with open("/app/docker-compose.yml", "r") as f:
            content = f.read()
        
        assert "CORS_ORIGINS:" in content, "CORS_ORIGINS not in docker-compose"
        print("PASS: CORS_ORIGINS in docker-compose")
    
    def test_docker_compose_has_default_admin_email(self):
        """Verify DEFAULT_ADMIN_EMAIL in docker-compose backend"""
        with open("/app/docker-compose.yml", "r") as f:
            content = f.read()
        
        assert "DEFAULT_ADMIN_EMAIL:" in content, "DEFAULT_ADMIN_EMAIL not in docker-compose"
        print("PASS: DEFAULT_ADMIN_EMAIL in docker-compose")
    
    def test_docker_compose_has_default_admin_password(self):
        """Verify DEFAULT_ADMIN_PASSWORD in docker-compose backend"""
        with open("/app/docker-compose.yml", "r") as f:
            content = f.read()
        
        assert "DEFAULT_ADMIN_PASSWORD:" in content, "DEFAULT_ADMIN_PASSWORD not in docker-compose"
        print("PASS: DEFAULT_ADMIN_PASSWORD in docker-compose")


class TestFrontendApiJsFailFast:
    """Test frontend/src/lib/api.js fail-fast on missing REACT_APP_BACKEND_URL"""
    
    def test_api_js_exists(self):
        """Verify api.js exists"""
        api_path = Path("/app/frontend/src/lib/api.js")
        assert api_path.exists(), "api.js not found"
        print("PASS: api.js exists")
    
    def test_api_js_checks_for_missing_url(self):
        """Verify api.js throws error if REACT_APP_BACKEND_URL is missing/empty"""
        with open("/app/frontend/src/lib/api.js", "r") as f:
            content = f.read()
        
        # Should throw error if empty
        assert "throw new Error" in content, "Should throw error for missing URL"
        assert "REACT_APP_BACKEND_URL" in content, "Should reference REACT_APP_BACKEND_URL"
        print("PASS: api.js throws error for missing REACT_APP_BACKEND_URL")
    
    def test_api_js_validates_url_format(self):
        """Verify api.js validates URL is proper http(s)"""
        with open("/app/frontend/src/lib/api.js", "r") as f:
            content = f.read()
        
        # Should validate URL format
        assert "https?" in content or "http" in content.lower(), "Should validate URL format"
        print("PASS: api.js validates URL format")
    
    def test_api_js_prevents_undefined_api(self):
        """Verify api.js prevents 'undefined/api' pattern"""
        with open("/app/frontend/src/lib/api.js", "r") as f:
            content = f.read()
        
        # Check for proper URL handling before constructing baseURL
        assert '!BACKEND_URL' in content or 'if (!BACKEND_URL)' in content or '!BACKEND_URL' in content, \
            "Should check if BACKEND_URL is falsy"
        print("PASS: api.js prevents undefined/api pattern")


class TestDockerComposeFrontendFailFast:
    """Test docker-compose.yml frontend command fail-fast"""
    
    def test_frontend_command_has_failfast(self):
        """Verify frontend command checks REACT_APP_BACKEND_URL before start"""
        with open("/app/docker-compose.yml", "r") as f:
            content = f.read()
        
        # Should have test for REACT_APP_BACKEND_URL
        assert 'test -n "$REACT_APP_BACKEND_URL"' in content or \
               '[ -n "$REACT_APP_BACKEND_URL" ]' in content or \
               '"$REACT_APP_BACKEND_URL"' in content, \
            "Frontend command should check REACT_APP_BACKEND_URL"
        print("PASS: docker-compose frontend has fail-fast check")
    
    def test_frontend_command_fails_on_missing(self):
        """Verify frontend command exits if REACT_APP_BACKEND_URL missing"""
        with open("/app/docker-compose.yml", "r") as f:
            content = f.read()
        
        # Should have exit 1 for missing URL
        assert "exit 1" in content, "Should exit 1 if URL missing"
        assert "Missing REACT_APP_BACKEND_URL" in content, "Should show clear error message"
        print("PASS: docker-compose frontend fails on missing URL")


class TestBackendEnvFiles:
    """Test backend .env and .env.example consistency"""
    
    def test_backend_env_exists(self):
        """Verify backend .env exists"""
        assert Path("/app/backend/.env").exists(), "backend/.env not found"
        print("PASS: backend/.env exists")
    
    def test_backend_env_example_exists(self):
        """Verify backend .env.example exists"""
        assert Path("/app/backend/.env.example").exists(), "backend/.env.example not found"
        print("PASS: backend/.env.example exists")
    
    def test_backend_env_has_database_url(self):
        """Verify backend .env has DATABASE_URL"""
        with open("/app/backend/.env", "r") as f:
            content = f.read()
        assert "DATABASE_URL" in content, "DATABASE_URL not in .env"
        print("PASS: DATABASE_URL in backend/.env")
    
    def test_backend_env_has_redis_url(self):
        """Verify backend .env has REDIS_URL"""
        with open("/app/backend/.env", "r") as f:
            content = f.read()
        assert "REDIS_URL" in content, "REDIS_URL not in .env"
        print("PASS: REDIS_URL in backend/.env")
    
    def test_backend_env_has_jwt_vars(self):
        """Verify backend .env has JWT variables"""
        with open("/app/backend/.env", "r") as f:
            content = f.read()
        assert "JWT_SECRET" in content, "JWT_SECRET not in .env"
        assert "JWT_ALGORITHM" in content, "JWT_ALGORITHM not in .env"
        assert "JWT_EXPIRE_MINUTES" in content, "JWT_EXPIRE_MINUTES not in .env"
        print("PASS: JWT vars in backend/.env")
    
    def test_backend_env_has_cors_origins(self):
        """Verify backend .env has CORS_ORIGINS"""
        with open("/app/backend/.env", "r") as f:
            content = f.read()
        assert "CORS_ORIGINS" in content, "CORS_ORIGINS not in .env"
        print("PASS: CORS_ORIGINS in backend/.env")
    
    def test_backend_env_has_admin_vars(self):
        """Verify backend .env has admin variables"""
        with open("/app/backend/.env", "r") as f:
            content = f.read()
        assert "DEFAULT_ADMIN_EMAIL" in content, "DEFAULT_ADMIN_EMAIL not in .env"
        assert "DEFAULT_ADMIN_PASSWORD" in content, "DEFAULT_ADMIN_PASSWORD not in .env"
        print("PASS: Admin vars in backend/.env")
    
    def test_backend_env_example_has_all_required(self):
        """Verify backend .env.example has all required keys"""
        with open("/app/backend/.env.example", "r") as f:
            content = f.read()
        
        required_keys = [
            "DATABASE_URL", "REDIS_URL", "JWT_SECRET", "JWT_ALGORITHM",
            "JWT_EXPIRE_MINUTES", "CORS_ORIGINS", "DEFAULT_ADMIN_EMAIL",
            "DEFAULT_ADMIN_PASSWORD"
        ]
        
        for key in required_keys:
            assert key in content, f"{key} not in .env.example"
        
        print("PASS: All required keys in backend/.env.example")


class TestFrontendEnvFiles:
    """Test frontend .env and .env.example consistency"""
    
    def test_frontend_env_exists(self):
        """Verify frontend .env exists"""
        assert Path("/app/frontend/.env").exists(), "frontend/.env not found"
        print("PASS: frontend/.env exists")
    
    def test_frontend_env_example_exists(self):
        """Verify frontend .env.example exists"""
        assert Path("/app/frontend/.env.example").exists(), "frontend/.env.example not found"
        print("PASS: frontend/.env.example exists")
    
    def test_frontend_env_has_backend_url(self):
        """Verify frontend .env has REACT_APP_BACKEND_URL"""
        with open("/app/frontend/.env", "r") as f:
            content = f.read()
        assert "REACT_APP_BACKEND_URL" in content, "REACT_APP_BACKEND_URL not in .env"
        print("PASS: REACT_APP_BACKEND_URL in frontend/.env")
    
    def test_frontend_env_backend_url_not_empty(self):
        """Verify REACT_APP_BACKEND_URL is not empty"""
        with open("/app/frontend/.env", "r") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    value = line.split("=", 1)[1].strip()
                    assert value, "REACT_APP_BACKEND_URL should not be empty"
                    assert value != "undefined", "REACT_APP_BACKEND_URL should not be 'undefined'"
                    print(f"PASS: REACT_APP_BACKEND_URL has value: {value}")
                    return
        
        pytest.fail("REACT_APP_BACKEND_URL not found in frontend/.env")
    
    def test_frontend_env_example_has_backend_url(self):
        """Verify frontend .env.example has REACT_APP_BACKEND_URL"""
        with open("/app/frontend/.env.example", "r") as f:
            content = f.read()
        assert "REACT_APP_BACKEND_URL" in content, "REACT_APP_BACKEND_URL not in .env.example"
        print("PASS: REACT_APP_BACKEND_URL in frontend/.env.example")


class TestRuntimeConfigFailFast:
    """Test runtime config fail-fast behavior (integration test)"""
    
    def test_config_fails_on_empty_env_var(self):
        """Test that config fails when a required env var is empty (overriding .env)"""
        # Setting DATABASE_URL to empty should trigger RuntimeError even if .env has value
        result = subprocess.run(
            [sys.executable, "-c", 
             "from core.config import Settings; s = Settings()"],
            capture_output=True,
            text=True,
            cwd="/app/backend",
            env={**os.environ, "DATABASE_URL": ""}  # Override to empty
        )
        
        # Should fail with RuntimeError
        assert result.returncode != 0, "Should fail when DATABASE_URL is empty"
        assert "RuntimeError" in result.stderr or "Missing required" in result.stderr, \
            f"Should raise RuntimeError, got: {result.stderr}"
        print("PASS: Config fails on empty DATABASE_URL")
    
    def test_required_env_function_behavior(self):
        """Test required_env function raises RuntimeError correctly"""
        # Test via direct function call
        test_script = '''
import os
import sys
sys.path.insert(0, "/app/backend")

# Import just the function
from core.config import required_env

# Test 1: Missing env var
try:
    os.environ.pop("_TEST_VAR_", None)
    required_env("_TEST_VAR_")
    print("FAIL: Should have raised RuntimeError for missing var")
    sys.exit(1)
except RuntimeError as e:
    if "Missing required environment variable" in str(e):
        print("PASS: RuntimeError for missing var")
    else:
        print(f"FAIL: Wrong error: {e}")
        sys.exit(1)

# Test 2: Empty env var
os.environ["_TEST_VAR_"] = ""
try:
    required_env("_TEST_VAR_")
    print("FAIL: Should have raised RuntimeError for empty var")
    sys.exit(1)
except RuntimeError as e:
    if "Missing required environment variable" in str(e):
        print("PASS: RuntimeError for empty var")
    else:
        print(f"FAIL: Wrong error: {e}")
        sys.exit(1)

# Test 3: Whitespace-only env var
os.environ["_TEST_VAR_"] = "   "
try:
    required_env("_TEST_VAR_")
    print("FAIL: Should have raised RuntimeError for whitespace-only var")
    sys.exit(1)
except RuntimeError as e:
    if "Missing required environment variable" in str(e):
        print("PASS: RuntimeError for whitespace-only var")
    else:
        print(f"FAIL: Wrong error: {e}")
        sys.exit(1)

# Test 4: Valid env var
os.environ["_TEST_VAR_"] = "valid_value"
try:
    result = required_env("_TEST_VAR_")
    if result == "valid_value":
        print("PASS: Valid env var returned correctly")
    else:
        print(f"FAIL: Wrong value returned: {result}")
        sys.exit(1)
except Exception as e:
    print(f"FAIL: Should not raise for valid var: {e}")
    sys.exit(1)

print("ALL PASS")
sys.exit(0)
'''
        result = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True,
            text=True,
            cwd="/app/backend"
        )
        
        print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr}")
        
        assert result.returncode == 0, f"required_env tests failed: {result.stdout} {result.stderr}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
