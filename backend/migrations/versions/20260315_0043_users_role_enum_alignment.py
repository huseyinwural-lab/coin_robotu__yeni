"""users role enum alignment

Revision ID: 20260315_0043
Revises: 20260315_0042
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260315_0043"
down_revision = "20260315_0042"
branch_labels = None
depends_on = None


ROLE_ENUM = sa.Enum("SUPER_ADMIN", "ADMIN", "OPS", "USER", name="userrole")


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if not _table_exists(bind, "users") or not _column_exists(bind, "users", "role"):
        return

    op.execute(sa.text("UPDATE users SET role = 'USER' WHERE role IS NULL"))
    op.execute(sa.text("UPDATE users SET role = UPPER(role)"))

    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                DO $$
                BEGIN
                  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
                    CREATE TYPE userrole AS ENUM ('SUPER_ADMIN','ADMIN','OPS','USER');
                  END IF;
                END
                $$;
                """
            )
        )
        op.execute(sa.text("ALTER TABLE users ALTER COLUMN role TYPE userrole USING UPPER(role)::userrole"))
        op.execute(sa.text("ALTER TABLE users ALTER COLUMN role SET NOT NULL"))
    else:
        op.alter_column("users", "role", existing_type=sa.String(length=20), existing_nullable=True, nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if not _table_exists(bind, "users") or not _column_exists(bind, "users", "role"):
        return

    if dialect == "postgresql":
        op.execute(sa.text("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(20) USING role::text"))
    op.alter_column("users", "role", existing_type=sa.String(length=20), nullable=True)
