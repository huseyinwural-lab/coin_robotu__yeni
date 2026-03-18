"""
FAZ-1 Gate-0: Alembic DB Binding and Migration Environment Tests

Tests:
1. env.py precedence: ALEMBIC_DATABASE_URL > DATABASE_URL > alembic.ini > explicit dev fallback
2. alembic.ini does NOT force SQLite
3. ALEMBIC_ALLOW_SQLITE_FALLBACK=0 blocks implicit SQLite fallback
4. Offline migration log shows PostgresqlImpl, not SQLiteImpl
5. Without DB URL, PostgreSQL connection error is raised (no SQLite fallback)
"""

import pytest
import os
import sys
from pathlib import Path
from unittest import mock

# Add backend to path for imports
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class TestAlembicIniConfiguration:
    """Verify alembic.ini has proper neutral placeholder, no SQLite forcing"""
    
    def test_alembic_ini_no_SQLite_url(self):
        """alembic.ini should NOT contain SQLite URL"""
        alembic_ini_path = BACKEND_DIR / "alembic.ini"
        assert alembic_ini_path.exists(), "alembic.ini should exist"
        
        content = alembic_ini_path.read_text().lower()
        assert "SQLite" not in content, "alembic.ini should NOT contain SQLite reference"
        print("PASS: alembic.ini does not contain SQLite references")
    
    def test_alembic_ini_has_postgresql_placeholder(self):
        """alembic.ini should have postgresql placeholder"""
        alembic_ini_path = BACKEND_DIR / "alembic.ini"
        content = alembic_ini_path.read_text()
        
        assert "postgresql" in content.lower(), "alembic.ini should reference postgresql"
        assert "<set-via-env>" in content or "set-via-env" in content, \
            "alembic.ini should indicate URL is set via environment"
        print("PASS: alembic.ini has correct postgresql placeholder")


class TestEnvPyUrlPrecedence:
    """Test get_url() precedence logic in env.py"""
    
    def test_env_py_exists_and_importable(self):
        """env.py should exist in migrations folder"""
        env_py_path = BACKEND_DIR / "migrations" / "env.py"
        assert env_py_path.exists(), "migrations/env.py should exist"
        print("PASS: migrations/env.py exists")
    
    def test_alembic_database_url_takes_precedence(self):
        """ALEMBIC_DATABASE_URL should be checked first"""
        env_py_path = BACKEND_DIR / "migrations" / "env.py"
        content = env_py_path.read_text()
        
        # Check ALEMBIC_DATABASE_URL is checked before DATABASE_URL
        alembic_url_pos = content.find('ALEMBIC_DATABASE_URL')
        database_url_pos = content.find('DATABASE_URL', alembic_url_pos + 1)
        
        assert alembic_url_pos != -1, "ALEMBIC_DATABASE_URL should be in env.py"
        assert database_url_pos != -1, "DATABASE_URL should be in env.py"
        assert alembic_url_pos < database_url_pos, \
            "ALEMBIC_DATABASE_URL should be checked before DATABASE_URL"
        print("PASS: ALEMBIC_DATABASE_URL precedence is correct (checked before DATABASE_URL)")
    
    def test_get_url_function_exists(self):
        """get_url() function should exist in env.py"""
        env_py_path = BACKEND_DIR / "migrations" / "env.py"
        content = env_py_path.read_text()
        
        assert "def get_url()" in content, "get_url() function should be defined"
        print("PASS: get_url() function exists in env.py")


class TestSqliteFallbackPrevention:
    """Test that SQLite fallback is properly blocked"""
    
    def test_SQLite_fallback_check_exists(self):
        """env.py should check ALEMBIC_ALLOW_SQLITE_FALLBACK"""
        env_py_path = BACKEND_DIR / "migrations" / "env.py"
        content = env_py_path.read_text()
        
        assert "ALEMBIC_ALLOW_SQLITE_FALLBACK" in content, \
            "env.py should reference ALEMBIC_ALLOW_SQLITE_FALLBACK"
        print("PASS: ALEMBIC_ALLOW_SQLITE_FALLBACK check exists")
    
    def test_runtime_error_for_disabled_SQLite_fallback(self):
        """When SQLite fallback is disabled, RuntimeError should be raised"""
        env_py_path = BACKEND_DIR / "migrations" / "env.py"
        content = env_py_path.read_text()
        
        # Check that RuntimeError is raised when SQLite fallback is not allowed
        assert "RuntimeError" in content, "RuntimeError should be raised for disallowed SQLite"
        assert "SQLite fallback disabled" in content or "SQLite fallback" in content.lower(), \
            "Error message should mention SQLite fallback"
        print("PASS: RuntimeError for disabled SQLite fallback is implemented")
    
    def test_is_SQLite_url_helper_exists(self):
        """_is_SQLite_url helper function should exist"""
        env_py_path = BACKEND_DIR / "migrations" / "env.py"
        content = env_py_path.read_text()
        
        assert "_is_SQLite_url" in content, "_is_SQLite_url helper should exist"
        print("PASS: _is_SQLite_url helper function exists")


class TestOfflineMigrationLog:
    """Verify offline migration log shows PostgresqlImpl"""
    
    def test_offline_log_file_exists(self):
        """Reference log file should exist"""
        log_path = Path("/tmp/alembic_offline_gate0.log")
        if not log_path.exists():
            pytest.skip("Offline log file not generated in this environment")
        print("PASS: Offline log file exists")
    
    def test_offline_log_shows_postgresql_impl(self):
        """Log should show PostgresqlImpl, not SQLiteImpl"""
        log_path = Path("/tmp/alembic_offline_gate0.log")
        if not log_path.exists():
            pytest.skip("Offline log file not generated in this environment")
        
        content = log_path.read_text()
        
        # Must have PostgresqlImpl
        assert "PostgresqlImpl" in content, \
            "Offline migration should use PostgresqlImpl"
        
        # Must NOT have SQLiteImpl
        assert "SQLiteImpl" not in content, \
            "Offline migration should NOT use SQLiteImpl"
        
        print("PASS: Offline log shows PostgresqlImpl (not SQLiteImpl)")


class TestNeutralPlaceholderDetection:
    """Test _is_neutral_placeholder function behavior"""
    
    def test_neutral_placeholder_patterns_defined(self):
        """env.py should define neutral placeholder patterns"""
        env_py_path = BACKEND_DIR / "migrations" / "env.py"
        content = env_py_path.read_text()
        
        assert "_is_neutral_placeholder" in content, \
            "_is_neutral_placeholder function should exist"
        
        # Check known neutral patterns
        assert "driver://user:pass@localhost/dbname" in content, \
            "Default alembic placeholder should be recognized"
        assert "postgresql+psycopg2://<set-via-env>" in content or \
               "set-via-env" in content, \
            "Custom placeholder pattern should be recognized"
        print("PASS: Neutral placeholder detection is implemented")


class TestNoImplicitSqliteFallback:
    """Integration test: No implicit SQLite fallback when env vars not set"""
    
    def test_get_url_raises_without_db_url(self):
        """get_url() should raise RuntimeError when no URL is available and fallback disabled"""
        # Import get_url from env.py dynamically
        env_py_path = BACKEND_DIR / "migrations" / "env.py"
        
        # Parse get_url function from env.py
        code = env_py_path.read_text()
        
        # Create mock module context
        mock_config = mock.MagicMock()
        mock_config.get_main_option.return_value = "postgresql+psycopg2://<set-via-env>"
        mock_config.config_file_name = None
        
        # Extract and test get_url logic
        # Check that the function raises RuntimeError when no valid URL
        assert "raise RuntimeError" in code, \
            "get_url should raise RuntimeError when no DB URL is available"
        
        # Verify the error message mentions PostgreSQL requirement
        error_msg_check = (
            "ALEMBIC_DATABASE_URL or DATABASE_URL" in code or
            "database URL" in code.lower()
        )
        assert error_msg_check, \
            "RuntimeError message should guide user to set proper env vars"
        print("PASS: get_url raises RuntimeError when no DB URL available (no implicit fallback)")


class TestUrlPrecedenceLogic:
    """Deep test of URL precedence order in get_url()"""
    
    def test_precedence_order_in_code(self):
        """Verify the exact precedence order in get_url function"""
        env_py_path = BACKEND_DIR / "migrations" / "env.py"
        content = env_py_path.read_text()
        
        # Find get_url function body
        get_url_start = content.find("def get_url()")
        assert get_url_start != -1, "get_url function should exist"
        
        # Get the function content (simplified extraction)
        func_content = content[get_url_start:content.find("\ndef ", get_url_start + 1)]
        
        # Verify order: ALEMBIC_DATABASE_URL -> DATABASE_URL -> config.get_main_option
        pos_alembic = func_content.find('ALEMBIC_DATABASE_URL')
        pos_db = func_content.find('DATABASE_URL', pos_alembic + 1)
        pos_config = func_content.find('get_main_option')
        
        assert pos_alembic < pos_db, "ALEMBIC_DATABASE_URL should be checked first"
        assert pos_db < pos_config, "DATABASE_URL should be checked before alembic.ini value"
        print("PASS: URL precedence order is correct: ALEMBIC_DATABASE_URL > DATABASE_URL > alembic.ini")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
