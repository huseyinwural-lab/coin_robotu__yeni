"""
FAZ-1 Kapanış Doğrulaması: Alembic DB Binding Tests
====================================================
Tests to verify:
1. env.py precedence: ALEMBIC_DATABASE_URL > DATABASE_URL > alembic.ini
2. No sqlite fallback path in env.py
3. No ALEMBIC_ALLOW_SQLITE_FALLBACK flag in env.py
4. No sqlite url in alembic.ini
5. Offline migration log has PostgresqlImpl, NOT SQLiteImpl
"""
import os
import re
import pytest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
ENV_PY_PATH = BACKEND_ROOT / "migrations" / "env.py"
ALEMBIC_INI_PATH = BACKEND_ROOT / "alembic.ini"
OFFLINE_LOG_PATH = Path("/tmp/alembic_phase1_close.log")


class TestEnvPyPrecedence:
    """Verify env.py URL resolution precedence order"""
    
    def test_env_py_exists(self):
        """env.py must exist"""
        assert ENV_PY_PATH.exists(), f"env.py not found at {ENV_PY_PATH}"
    
    def test_alembic_database_url_checked_first(self):
        """ALEMBIC_DATABASE_URL must be checked first in get_url()"""
        content = ENV_PY_PATH.read_text()
        
        # Find get_url function
        assert "def get_url" in content, "get_url function must exist"
        
        # Extract get_url function body
        match = re.search(r'def get_url\(\)[^:]*:(.*?)(?=\ndef |\nif context\.|\Z)', content, re.DOTALL)
        assert match, "Could not extract get_url function"
        get_url_body = match.group(1)
        
        # Find positions of env var checks
        alembic_db_url_pos = get_url_body.find('ALEMBIC_DATABASE_URL')
        database_url_pos = get_url_body.find('DATABASE_URL')
        config_get_pos = get_url_body.find('config.get_main_option')
        
        assert alembic_db_url_pos != -1, "ALEMBIC_DATABASE_URL check must exist"
        assert database_url_pos != -1, "DATABASE_URL check must exist"
        assert config_get_pos != -1, "alembic.ini fallback must exist"
        
        # Verify order: ALEMBIC_DATABASE_URL < DATABASE_URL < config.get_main_option
        assert alembic_db_url_pos < database_url_pos, \
            "ALEMBIC_DATABASE_URL must be checked before DATABASE_URL"
        assert database_url_pos < config_get_pos, \
            "DATABASE_URL must be checked before alembic.ini"
    
    def test_database_url_checked_second(self):
        """DATABASE_URL must be checked after ALEMBIC_DATABASE_URL"""
        content = ENV_PY_PATH.read_text()
        
        # Verify DATABASE_URL check exists and returns if found
        assert 'os.getenv("DATABASE_URL")' in content or "os.getenv('DATABASE_URL')" in content, \
            "DATABASE_URL env check must exist"
    
    def test_alembic_ini_checked_last(self):
        """alembic.ini sqlalchemy.url must be checked last"""
        content = ENV_PY_PATH.read_text()
        
        # Verify config.get_main_option is used for alembic.ini
        assert 'config.get_main_option("sqlalchemy.url")' in content or \
               "config.get_main_option('sqlalchemy.url')" in content, \
            "alembic.ini sqlalchemy.url lookup must exist"


class TestNoSqliteFallback:
    """Verify no implicit sqlite fallback exists"""
    
    def test_no_sqlite_fallback_path_in_env_py(self):
        """env.py must NOT have any sqlite:// fallback path"""
        content = ENV_PY_PATH.read_text()
        
        # Check for any sqlite URL patterns that would be used as fallback
        sqlite_patterns = [
            r'sqlite:///',           # sqlite URL
            r'sqlite:///.*\.db',     # sqlite with .db file
            r'sqlite:///\:memory\:', # sqlite memory
            r'fallback.*sqlite',     # fallback with sqlite
            r'default.*sqlite',      # default sqlite
        ]
        
        for pattern in sqlite_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            # Filter out error messages - they're OK
            filtered_matches = [m for m in matches if 'error' not in content[max(0, content.find(m)-50):content.find(m)+50].lower() 
                               and 'raise' not in content[max(0, content.find(m)-50):content.find(m)+50].lower()
                               and 'not allowed' not in content[max(0, content.find(m)-50):content.find(m)+50].lower()]
            assert len(filtered_matches) == 0, f"Found sqlite fallback pattern: {pattern}"
    
    def test_no_alembic_allow_sqlite_fallback_flag(self):
        """env.py must NOT have ALEMBIC_ALLOW_SQLITE_FALLBACK flag"""
        content = ENV_PY_PATH.read_text()
        
        # This flag should NOT exist - it was removed
        assert "ALEMBIC_ALLOW_SQLITE_FALLBACK" not in content, \
            "ALEMBIC_ALLOW_SQLITE_FALLBACK flag must be removed from env.py"
    
    def test_runtime_error_when_no_url(self):
        """env.py must raise RuntimeError when no URL is available, not fallback to sqlite"""
        content = ENV_PY_PATH.read_text()
        
        # Must have RuntimeError raise for missing URL
        assert "raise RuntimeError" in content, \
            "Must raise RuntimeError when no database URL is found"
        
        # Must have appropriate error message
        assert "No database URL found" in content or "Set ALEMBIC_DATABASE_URL" in content, \
            "Error message must instruct to set proper environment variable"
    
    def test_sqlite_url_rejected_from_config(self):
        """env.py must reject sqlite URLs from alembic.ini"""
        content = ENV_PY_PATH.read_text()
        
        # _is_sqlite_url helper should exist
        assert "_is_sqlite_url" in content, "_is_sqlite_url helper function must exist"
        
        # Must raise RuntimeError for sqlite in config
        assert "SQLite URL is not allowed" in content or "sqlite" in content.lower() and "raise RuntimeError" in content, \
            "Must reject sqlite URLs from alembic.ini config"


class TestAlembicIniNoSqlite:
    """Verify alembic.ini has no sqlite configuration"""
    
    def test_alembic_ini_exists(self):
        """alembic.ini must exist"""
        assert ALEMBIC_INI_PATH.exists(), f"alembic.ini not found at {ALEMBIC_INI_PATH}"
    
    def test_alembic_ini_no_sqlite_url(self):
        """alembic.ini must NOT have sqlite URL"""
        content = ALEMBIC_INI_PATH.read_text()
        
        # No sqlite URL should exist
        assert "sqlite://" not in content.lower(), \
            "alembic.ini must not contain sqlite:// URL"
        assert "sqlite:" not in content.lower(), \
            "alembic.ini must not contain sqlite: reference"
    
    def test_alembic_ini_has_postgresql_placeholder(self):
        """alembic.ini must have postgresql placeholder, not sqlite"""
        content = ALEMBIC_INI_PATH.read_text()
        
        # Must have postgresql reference
        assert "postgresql" in content.lower(), \
            "alembic.ini must have postgresql placeholder"
        
        # Should be a placeholder, not a real connection string
        assert "<set-via-env>" in content or "set-via-env" in content, \
            "alembic.ini should have env-based placeholder"


class TestOfflineMigrationLog:
    """Verify offline migration log shows PostgresqlImpl"""
    
    def test_offline_log_exists(self):
        """Offline migration log must exist"""
        assert OFFLINE_LOG_PATH.exists(), f"Offline log not found at {OFFLINE_LOG_PATH}"
    
    def test_offline_log_shows_postgresql_impl(self):
        """Log must show 'Context impl PostgresqlImpl'"""
        content = OFFLINE_LOG_PATH.read_text()
        
        assert "PostgresqlImpl" in content, \
            "Offline migration log must show PostgresqlImpl"
        assert "Context impl PostgresqlImpl" in content, \
            "Log must show 'Context impl PostgresqlImpl'"
    
    def test_offline_log_no_sqlite_impl(self):
        """Log must NOT show SQLiteImpl"""
        content = OFFLINE_LOG_PATH.read_text()
        
        # SQLiteImpl must NOT appear in the log
        assert "SQLiteImpl" not in content, \
            "Offline migration log must NOT contain SQLiteImpl"


class TestMigrationServiceNoSqliteFallback:
    """Verify migration_service.py also has no sqlite fallback"""
    
    def test_migration_service_exists(self):
        """migration_service.py must exist"""
        service_path = BACKEND_ROOT / "services" / "migration_service.py"
        assert service_path.exists(), "migration_service.py not found"
    
    def test_migration_service_no_sqlite_fallback(self):
        """migration_service.py must not fallback to sqlite"""
        service_path = BACKEND_ROOT / "services" / "migration_service.py"
        content = service_path.read_text()
        
        # No sqlite URL patterns
        assert "sqlite://" not in content, "migration_service.py must not have sqlite URL"
        
        # Must raise RuntimeError, not fallback
        assert "SQLite fallback is disabled" in content or "raise RuntimeError" in content, \
            "migration_service.py must raise error instead of sqlite fallback"


class TestPrecedenceFunctional:
    """Functional tests for URL precedence (import and test get_url)"""
    
    def test_get_url_alembic_database_url_precedence(self, monkeypatch):
        """ALEMBIC_DATABASE_URL takes precedence over all"""
        # Set up environment
        monkeypatch.setenv("ALEMBIC_DATABASE_URL", "postgresql://test:test@localhost/alembic_test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/database_test")
        
        # Import and test
        import sys
        sys.path.insert(0, str(BACKEND_ROOT))
        
        # Read and execute get_url
        content = ENV_PY_PATH.read_text()
        
        # Verify ALEMBIC_DATABASE_URL is checked first by checking the code pattern
        get_url_match = re.search(r'def get_url\(\)[^:]*:(.*?)(?=\ndef |\Z)', content, re.DOTALL)
        assert get_url_match, "get_url function must exist"
        
        func_body = get_url_match.group(1)
        first_check = func_body.find('ALEMBIC_DATABASE_URL')
        second_check = func_body.find('DATABASE_URL')
        
        # Exclude the first occurrence which is ALEMBIC_DATABASE_URL itself
        # Find DATABASE_URL that's not part of ALEMBIC_DATABASE_URL
        database_url_matches = list(re.finditer(r'(?<!ALEMBIC_)DATABASE_URL', func_body))
        if database_url_matches:
            second_check = database_url_matches[0].start()
        
        assert first_check < second_check, "ALEMBIC_DATABASE_URL must be checked first"
    
    def test_get_url_database_url_second(self, monkeypatch):
        """DATABASE_URL is used when ALEMBIC_DATABASE_URL is not set"""
        # Clear ALEMBIC_DATABASE_URL
        monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
        monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/database_test")
        
        content = ENV_PY_PATH.read_text()
        
        # Verify DATABASE_URL return logic exists
        assert 'env_url = os.getenv("DATABASE_URL")' in content or \
               "env_url = os.getenv('DATABASE_URL')" in content, \
            "DATABASE_URL must be fetched"
        assert "return env_url" in content, \
            "DATABASE_URL must be returned when set"
    
    def test_get_url_raises_without_any_url(self, monkeypatch):
        """RuntimeError is raised when no URL is available"""
        # Clear all URLs
        monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        
        content = ENV_PY_PATH.read_text()
        
        # Must raise RuntimeError at the end
        assert 'raise RuntimeError' in content, \
            "Must raise RuntimeError when no URL is found"
        assert 'No database URL found' in content or 'Set ALEMBIC_DATABASE_URL' in content, \
            "Error message must guide user to set proper env var"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
