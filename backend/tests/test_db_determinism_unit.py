# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest

from core.db_determinism import enforce_postgresql_only


class TestEnforcePostgresqlOnly:
    def test_valid_postgresql_url(self):
        url = "postgresql://user:pass@localhost:5432/mydb"
        result = enforce_postgresql_only(url, "test")
        assert result == url

    def test_valid_postgresql_asyncpg_url(self):
        url = "postgresql+asyncpg://user:pass@localhost:5432/mydb"
        result = enforce_postgresql_only(url, "test")
        assert result == url

    def test_rejects_sqlite_url(self):
        with pytest.raises(AssertionError, match="gömülü db kullanımı yasak"):
            enforce_postgresql_only("sqlite:///test.db", "test")

    def test_rejects_sqlite_memory(self):
        with pytest.raises(AssertionError, match="gömülü db kullanımı yasak"):
            enforce_postgresql_only("sqlite:///:memory:", "test")

    def test_rejects_empty_url(self):
        with pytest.raises(AssertionError, match="zorunlu"):
            enforce_postgresql_only("", "test")

    def test_rejects_none_url(self):
        with pytest.raises(AssertionError, match="zorunlu"):
            enforce_postgresql_only(None, "test")

    def test_rejects_non_postgres_url(self):
        with pytest.raises(AssertionError, match="postgresql zorunlu"):
            enforce_postgresql_only("mysql://user:pass@localhost/db", "test")

    def test_whitespace_only_url(self):
        with pytest.raises(AssertionError, match="zorunlu"):
            enforce_postgresql_only("   ", "test")

    def test_strips_whitespace_from_valid_url(self):
        url = "  postgresql://user:pass@localhost:5432/mydb  "
        result = enforce_postgresql_only(url, "test")
        assert result == url.strip()
