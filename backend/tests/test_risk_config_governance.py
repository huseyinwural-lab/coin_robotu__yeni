from services import risk_engine_service


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def _isolate_paths(monkeypatch, tmp_path):
    config_path = tmp_path / "risk_engine_config.json"
    backup_path = tmp_path / "risk_engine_config_backup.json"
    monkeypatch.setattr(risk_engine_service, "_config_path", lambda: config_path)
    monkeypatch.setattr(risk_engine_service, "_config_backup_path", lambda: backup_path)


def test_patch_rejects_safe_bound_violation(monkeypatch, tmp_path):
    _isolate_paths(monkeypatch, tmp_path)
    cache = FakeCache()
    monkeypatch.setattr(risk_engine_service, "load_risk_config", lambda _cache: {**risk_engine_service.DEFAULT_RISK_CONFIG, "config_version": 2})

    try:
        risk_engine_service.patch_risk_config(cache, {"max_leverage": 25}, changed_by="admin-1")
    except ValueError as exc:
        assert "safe_bounds_violation" in str(exc)
    else:
        raise AssertionError("expected safe bound rejection")


def test_patch_updates_config_version_and_audit_fields(monkeypatch, tmp_path):
    _isolate_paths(monkeypatch, tmp_path)
    cache = FakeCache()
    monkeypatch.setattr(risk_engine_service, "load_risk_config", lambda _cache: {**risk_engine_service.DEFAULT_RISK_CONFIG, "config_version": 2})

    payload = risk_engine_service.patch_risk_config(cache, {"max_risk_per_trade_pct": 2.5}, changed_by="admin-1")
    assert payload["config_version"] == 3
    assert payload["changed_by"] == "admin-1"


def test_rollback_returns_last_known_good(monkeypatch, tmp_path):
    _isolate_paths(monkeypatch, tmp_path)
    cache = FakeCache()
    risk_engine_service.patch_risk_config(cache, {"max_risk_per_trade_pct": 2.8}, changed_by="admin-2")
    risk_engine_service.patch_risk_config(cache, {"max_risk_per_trade_pct": 2.1}, changed_by="admin-3")

    restored = risk_engine_service.rollback_risk_config(cache, changed_by="admin-rollback")
    assert restored["changed_by"] == "admin-rollback"
    assert restored["config_version"] >= 2
