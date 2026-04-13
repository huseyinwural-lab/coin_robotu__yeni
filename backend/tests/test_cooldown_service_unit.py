# ruff: noqa: E402
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.cooldown_service import activate_cooldown, cooldown_state


class FakeCache:
    """In-memory cache mimicking Redis get/set interface."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


class TestActivateCooldown:
    def test_activate_creates_active_cooldown(self):
        cache = FakeCache()
        result = activate_cooldown(
            cache, scope="trade", user_id="u1", minutes=10, reason="rate_limit"
        )
        assert result["active"] is True
        assert result["scope"] == "trade"
        assert result["user_id"] == "u1"
        assert result["reason"] == "rate_limit"
        assert result["remaining_seconds"] > 0

    def test_activate_with_zero_minutes(self):
        cache = FakeCache()
        result = activate_cooldown(
            cache, scope="trade", user_id="u1", minutes=0, reason="no_cooldown"
        )
        assert result["active"] is False
        assert result["remaining_seconds"] == 0

    def test_activate_with_negative_minutes(self):
        cache = FakeCache()
        result = activate_cooldown(
            cache, scope="trade", user_id="u1", minutes=-5, reason="invalid"
        )
        assert result["active"] is False
        assert result["remaining_seconds"] == 0

    def test_activate_with_custom_key(self):
        cache = FakeCache()
        result = activate_cooldown(
            cache, scope="order", user_id="u2", minutes=5, key="BTCUSDT"
        )
        assert result["active"] is True
        assert result["key"] == "BTCUSDT"

    def test_activate_stores_in_cache(self):
        cache = FakeCache()
        activate_cooldown(cache, scope="trade", user_id="u1", minutes=10)
        assert len(cache.store) == 1
        stored_key = list(cache.store.keys())[0]
        assert "risk:cooldown:trade:u1" in stored_key


class TestCooldownState:
    def test_state_returns_inactive_when_not_set(self):
        cache = FakeCache()
        result = cooldown_state(cache, scope="trade", user_id="u1")
        assert result["active"] is False
        assert result["remaining_seconds"] == 0

    def test_state_returns_active_for_fresh_cooldown(self):
        cache = FakeCache()
        activate_cooldown(cache, scope="trade", user_id="u1", minutes=10)
        result = cooldown_state(cache, scope="trade", user_id="u1")
        assert result["active"] is True
        assert result["remaining_seconds"] > 0

    def test_state_returns_inactive_for_expired_cooldown(self):
        cache = FakeCache()
        # Manually create an expired cooldown
        now = datetime.now(timezone.utc)
        expired_payload = {
            "active": True,
            "scope": "trade",
            "user_id": "u1",
            "key": None,
            "reason": "test",
            "started_at": (now - timedelta(minutes=20)).isoformat(),
            "expires_at": (now - timedelta(minutes=10)).isoformat(),
            "remaining_seconds": 0,
        }
        cache.set("risk:cooldown:trade:u1", json.dumps(expired_payload))
        result = cooldown_state(cache, scope="trade", user_id="u1")
        assert result["active"] is False
        assert result["remaining_seconds"] == 0

    def test_state_with_custom_key(self):
        cache = FakeCache()
        activate_cooldown(
            cache, scope="order", user_id="u2", minutes=5, key="ETHUSDT"
        )
        result = cooldown_state(cache, scope="order", user_id="u2", key="ETHUSDT")
        assert result["active"] is True

    def test_state_different_keys_independent(self):
        cache = FakeCache()
        activate_cooldown(
            cache, scope="order", user_id="u1", minutes=5, key="BTCUSDT"
        )
        result = cooldown_state(cache, scope="order", user_id="u1", key="ETHUSDT")
        assert result["active"] is False

    def test_state_handles_corrupt_cache_data(self):
        cache = FakeCache()
        cache.set("risk:cooldown:trade:u1", "not-valid-json")
        result = cooldown_state(cache, scope="trade", user_id="u1")
        # Should return default inactive state, not raise
        assert result["active"] is False
