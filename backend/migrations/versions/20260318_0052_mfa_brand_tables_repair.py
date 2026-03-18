"""mfa and brand settings tables repair

Revision ID: 20260318_0052
Revises: 20260318_0051
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260318_0052"
down_revision = "20260318_0051"
branch_labels = None
depends_on = None


REPAIR_TABLES = [
    "auth_mfa_challenges",
    "user_mfa_preferences",
    "brand_settings",
]


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    from pathlib import Path
    import sys

    backend_root = Path(__file__).resolve().parents[2]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from models import AuthMfaChallenge, BrandSetting, UserMfaPreference

    bind = op.get_bind()
    table_map = {
        "auth_mfa_challenges": AuthMfaChallenge.__table__,
        "user_mfa_preferences": UserMfaPreference.__table__,
        "brand_settings": BrandSetting.__table__,
    }

    for table_name in REPAIR_TABLES:
        if _table_exists(bind, table_name):
            continue
        table_map[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    # Repair migration intentionally non-destructive on downgrade.
    pass

