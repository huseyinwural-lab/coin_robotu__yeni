from types import SimpleNamespace

from services.admin_profile_service import update_admin_profile


class _QueryMock:
    def __init__(self, user_row=None, onboarding_row=None):
        self.user_row = user_row
        self.onboarding_row = onboarding_row
        self.model_name = None

    def filter(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def first(self):
        if self.model_name == "User":
            return self.user_row
        return self.onboarding_row


class _DbMock:
    def __init__(self, existing_user=None, existing_onboarding=None):
        self.existing_user = existing_user
        self.existing_onboarding = existing_onboarding
        self.added = []

    def query(self, model):
        query = _QueryMock(user_row=self.existing_user, onboarding_row=self.existing_onboarding)
        query.model_name = model.__name__
        return query

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        return None

    def refresh(self, obj):
        _ = obj


def test_admin_profile_update_changes_email_and_full_name():
    admin = SimpleNamespace(id="u1", email="admin@platform.local", updated_at=None)
    db = _DbMock(existing_user=None, existing_onboarding=SimpleNamespace(user_id="u1", full_name=None))

    updated = update_admin_profile(db, admin, email="new-admin@platform.local", full_name="Platform Admin")

    assert updated.email == "new-admin@platform.local"
    assert db.existing_onboarding.full_name == "Platform Admin"
