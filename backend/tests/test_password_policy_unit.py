# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from fastapi import HTTPException

from services.password_policy_service import validate_password_policy


class TestValidatePasswordPolicy:
    def test_valid_password_passes(self):
        # Should not raise
        validate_password_policy("MyP@ssw0rd!")

    def test_too_short_password(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_password_policy("Short1!")
        assert exc_info.value.status_code == 400
        assert "password_min_length" in exc_info.value.detail

    def test_missing_uppercase(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_password_policy("myp@ssw0rd!")
        assert exc_info.value.status_code == 400
        assert "password_requires_uppercase" in exc_info.value.detail

    def test_missing_lowercase(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_password_policy("MYP@SSW0RD!")
        assert exc_info.value.status_code == 400
        assert "password_requires_lowercase" in exc_info.value.detail

    def test_missing_digit(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_password_policy("MyP@ssword!")
        assert exc_info.value.status_code == 400
        assert "password_requires_number" in exc_info.value.detail

    def test_missing_special_character(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_password_policy("MyPassw0rd1")
        assert exc_info.value.status_code == 400
        assert "password_requires_symbol" in exc_info.value.detail

    def test_empty_password(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_password_policy("")
        assert exc_info.value.status_code == 400

    def test_none_password(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_password_policy(None)
        assert exc_info.value.status_code == 400

    def test_custom_minimum_length(self):
        # Should pass with length 6 when minimum is 5
        validate_password_policy("Pa$$1a", minimum_length=5)

    def test_custom_minimum_length_too_short(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_password_policy("Pa$1", minimum_length=5)
        assert "password_min_length" in exc_info.value.detail

    def test_exactly_minimum_length(self):
        # 10 chars, meets all requirements
        validate_password_policy("Abcdefgh1!")

    def test_unicode_special_char(self):
        # Unicode special chars should count as symbols
        validate_password_policy("Abcdefgh1€")
