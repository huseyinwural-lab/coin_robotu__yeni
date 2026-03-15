from types import SimpleNamespace

from core.security import hash_password, verify_password
from services.admin_profile_service import change_admin_password


class _DbMock:
    def commit(self):
        return None

    def refresh(self, obj):
        _ = obj


def test_admin_password_change_updates_hash():
    old_password = "Admin12345!"
    new_password = "Admin54321!"
    admin = SimpleNamespace(id="a1", password_hash=hash_password(old_password), updated_at=None)

    updated = change_admin_password(_DbMock(), admin, current_password=old_password, new_password=new_password)

    assert verify_password(new_password, updated.password_hash)
