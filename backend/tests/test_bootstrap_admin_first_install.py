
from services import bootstrap


class _QueryMock:
    def __init__(self, value: int):
        self.value = value

    def count(self):
        return self.value


class _DbMock:
    def __init__(self, users_count: int):
        self.users_count = users_count
        self.added = []
        self.committed = 0

    def query(self, model):
        _ = model
        return _QueryMock(self.users_count)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed += 1

    def refresh(self, obj):
        _ = obj


def test_bootstrap_admin_created_only_when_users_empty(monkeypatch):
    monkeypatch.setattr(bootstrap.settings, "default_admin_email", "admin@platform.local")
    monkeypatch.setattr(bootstrap.settings, "default_admin_password", "Admin12345!")
    monkeypatch.setattr(bootstrap, "create_audit_log", lambda *args, **kwargs: None)

    empty_db = _DbMock(users_count=0)
    bootstrap._seed_admin(empty_db)

    assert len(empty_db.added) == 1
    assert empty_db.added[0].email == "admin@platform.local"

    non_empty_db = _DbMock(users_count=3)
    bootstrap._seed_admin(non_empty_db)

    assert len(non_empty_db.added) == 0
