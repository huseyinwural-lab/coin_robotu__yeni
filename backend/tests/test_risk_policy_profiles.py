from services import risk_engine_service


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def test_policy_profiles_available():
    payload = risk_engine_service.get_policy_profiles()
    assert payload["default_profile"] == "balanced"
    assert set(payload["profiles"].keys()) == {"conservative", "balanced", "aggressive"}


def test_apply_profile_updates_config(cache=None):
    cache = FakeCache()
    payload = risk_engine_service.apply_policy_profile(cache, profile="conservative", changed_by="admin-test")
    assert payload["active_profile"] == "conservative"
    assert payload["max_leverage"] <= 3


def test_user_override_merges_over_global_profile():
    cache = FakeCache()
    risk_engine_service.apply_policy_profile(cache, profile="balanced", changed_by="admin-test")
    risk_engine_service.upsert_policy_overrides(scope="global", key="default", values={"max_leverage": 4})
    risk_engine_service.upsert_policy_overrides(scope="users", key="user-123", values={"max_leverage": 2})

    effective = risk_engine_service.resolve_effective_config_for_user(cache, user_id="user-123")
    assert effective["max_leverage"] == 2
