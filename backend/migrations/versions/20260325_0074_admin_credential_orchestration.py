"""admin credential orchestration layer tables

Revision ID: 20260325_0074
Revises: 20260324_0073
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260325_0074"
down_revision = "20260324_0073"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "admin_exchange_credentials"):
        op.create_table(
            "admin_exchange_credentials",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("scope_type", sa.String(length=20), nullable=False, server_default="global"),
            sa.Column("scope_id", sa.String(length=120), nullable=True),
            sa.Column("exchange", sa.String(length=40), nullable=False, server_default="binance"),
            sa.Column("market_type", sa.String(length=20), nullable=False, server_default="spot"),
            sa.Column("purpose", sa.String(length=40), nullable=False, server_default="market_data"),
            sa.Column("environment", sa.String(length=20), nullable=False, server_default="live"),
            sa.Column("api_key_encrypted", sa.Text(), nullable=False, server_default=""),
            sa.Column("api_secret_encrypted", sa.Text(), nullable=False, server_default=""),
            sa.Column("passphrase_encrypted", sa.Text(), nullable=True),
            sa.Column("base_url_override", sa.Text(), nullable=True),
            sa.Column("ip_binding_note", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("approval_status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("approved_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("last_probe_status", sa.String(length=40), nullable=True),
            sa.Column("last_probe_message", sa.Text(), nullable=True),
            sa.Column("last_probe_meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        for name, cols in [
            ("ix_admin_exchange_credentials_scope_type", ["scope_type"]),
            ("ix_admin_exchange_credentials_scope_id", ["scope_id"]),
            ("ix_admin_exchange_credentials_exchange", ["exchange"]),
            ("ix_admin_exchange_credentials_market_type", ["market_type"]),
            ("ix_admin_exchange_credentials_purpose", ["purpose"]),
            ("ix_admin_exchange_credentials_environment", ["environment"]),
            ("ix_admin_exchange_credentials_is_active", ["is_active"]),
            ("ix_admin_exchange_credentials_is_default", ["is_default"]),
            ("ix_admin_exchange_credentials_approval_status", ["approval_status"]),
        ]:
            op.create_index(name, "admin_exchange_credentials", cols)

    if not _has_table(bind, "credential_assignment_rules"):
        op.create_table(
            "credential_assignment_rules",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("exchange", sa.String(length=40), nullable=False, server_default="binance"),
            sa.Column("market_type", sa.String(length=20), nullable=False, server_default="spot"),
            sa.Column("environment", sa.String(length=20), nullable=False, server_default="live"),
            sa.Column("tenant_id", sa.String(length=120), nullable=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("preferred_source", sa.String(length=30), nullable=False, server_default="user"),
            sa.Column("fallback_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        for name, cols in [
            ("ix_credential_assignment_rules_exchange", ["exchange"]),
            ("ix_credential_assignment_rules_market_type", ["market_type"]),
            ("ix_credential_assignment_rules_environment", ["environment"]),
            ("ix_credential_assignment_rules_tenant_id", ["tenant_id"]),
            ("ix_credential_assignment_rules_user_id", ["user_id"]),
        ]:
            op.create_index(name, "credential_assignment_rules", cols)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "credential_assignment_rules"):
        op.drop_table("credential_assignment_rules")
    if _has_table(bind, "admin_exchange_credentials"):
        op.drop_table("admin_exchange_credentials")
