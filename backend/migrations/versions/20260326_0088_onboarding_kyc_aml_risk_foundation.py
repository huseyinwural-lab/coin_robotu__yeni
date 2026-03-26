"""onboarding kyc aml risk foundation and immutable decision logs

Revision ID: 20260326_0088
Revises: 20260326_0087
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_0088"
down_revision = "20260326_0087"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "user_onboarding_profiles"):
        additions = [
            ("kyc_status", sa.String(length=20), "'pending'"),
            ("risk_score", sa.Float(), "0"),
            ("aml_flag", sa.String(length=30), "'clear'"),
            ("aml_reason", sa.Text(), None),
            ("api_key_validity", sa.String(length=20), "'unknown'"),
            ("balance_usd", sa.Float(), "0"),
            ("first_funding_at", sa.DateTime(timezone=True), None),
            ("country_code", sa.String(length=8), None),
            ("region_compliance_status", sa.String(length=20), "'unknown'"),
            ("leverage_permission", sa.Boolean(), "false"),
            ("futures_capability", sa.Boolean(), "false"),
            ("spot_capability", sa.Boolean(), "true"),
            ("trading_eligibility", sa.Boolean(), "false"),
            ("precheck_reasons", sa.JSON(), "'[]'::json"),
        ]
        for name, column_type, default_expr in additions:
            if not _has_column(bind, "user_onboarding_profiles", name):
                column = sa.Column(name, column_type, nullable=True)
                op.add_column("user_onboarding_profiles", column)
                if default_expr is not None:
                    op.execute(
                        sa.text(
                            f"ALTER TABLE user_onboarding_profiles ALTER COLUMN {name} SET DEFAULT {default_expr}"
                        )
                    )

        op.execute(sa.text("UPDATE user_onboarding_profiles SET kyc_status = COALESCE(kyc_status, 'pending')"))
        op.execute(sa.text("UPDATE user_onboarding_profiles SET aml_flag = COALESCE(aml_flag, 'clear')"))
        op.execute(sa.text("UPDATE user_onboarding_profiles SET risk_score = COALESCE(risk_score, 0)"))
        op.execute(sa.text("UPDATE user_onboarding_profiles SET api_key_validity = COALESCE(api_key_validity, 'unknown')"))
        op.execute(sa.text("UPDATE user_onboarding_profiles SET balance_usd = COALESCE(balance_usd, 0)"))
        op.execute(sa.text("UPDATE user_onboarding_profiles SET region_compliance_status = COALESCE(region_compliance_status, 'unknown')"))
        op.execute(sa.text("UPDATE user_onboarding_profiles SET leverage_permission = COALESCE(leverage_permission, false)"))
        op.execute(sa.text("UPDATE user_onboarding_profiles SET futures_capability = COALESCE(futures_capability, false)"))
        op.execute(sa.text("UPDATE user_onboarding_profiles SET spot_capability = COALESCE(spot_capability, true)"))
        op.execute(sa.text("UPDATE user_onboarding_profiles SET trading_eligibility = COALESCE(trading_eligibility, false)"))
        op.execute(sa.text("UPDATE user_onboarding_profiles SET precheck_reasons = COALESCE(precheck_reasons, '[]'::json)"))

        op.create_index("ix_user_onboarding_profiles_kyc_status", "user_onboarding_profiles", ["kyc_status"], unique=False)
        op.create_index("ix_user_onboarding_profiles_aml_flag", "user_onboarding_profiles", ["aml_flag"], unique=False)

    if not _has_table(bind, "user_kyc_documents"):
        op.create_table(
            "user_kyc_documents",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("file_type", sa.String(length=20), nullable=False),
            sa.Column("storage_ref", sa.Text(), nullable=False),
            sa.Column("upload_status", sa.String(length=20), nullable=False, server_default="uploaded"),
            sa.Column("review_status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("uploaded_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reviewed_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_user_kyc_documents_user_id", "user_kyc_documents", ["user_id"], unique=False)
        op.create_index("ix_user_kyc_documents_review_status", "user_kyc_documents", ["review_status"], unique=False)

    if not _has_table(bind, "onboarding_aml_denylist"):
        op.create_table(
            "onboarding_aml_denylist",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("match_key", sa.String(length=255), nullable=False, unique=True),
            sa.Column("match_type", sa.String(length=30), nullable=False, server_default="email"),
            sa.Column("reason", sa.Text(), nullable=False, server_default="aml_internal_denylist"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_onboarding_aml_denylist_match_key", "onboarding_aml_denylist", ["match_key"], unique=True)

    if not _has_table(bind, "user_onboarding_decision_logs"):
        op.create_table(
            "user_onboarding_decision_logs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("decision", sa.String(length=30), nullable=False),
            sa.Column("decision_source", sa.String(length=30), nullable=False, server_default="manual"),
            sa.Column("actor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("actor_role", sa.String(length=30), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("explanation", sa.Text(), nullable=False),
            sa.Column("context_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_user_onboarding_decision_logs_user_id", "user_onboarding_decision_logs", ["user_id"], unique=False)
        op.create_index("ix_user_onboarding_decision_logs_decision", "user_onboarding_decision_logs", ["decision"], unique=False)
        op.create_index("ix_user_onboarding_decision_logs_actor", "user_onboarding_decision_logs", ["actor_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_onboarding_decision_logs_actor", table_name="user_onboarding_decision_logs")
    op.drop_index("ix_user_onboarding_decision_logs_decision", table_name="user_onboarding_decision_logs")
    op.drop_index("ix_user_onboarding_decision_logs_user_id", table_name="user_onboarding_decision_logs")
    op.drop_table("user_onboarding_decision_logs")

    op.drop_index("ix_onboarding_aml_denylist_match_key", table_name="onboarding_aml_denylist")
    op.drop_table("onboarding_aml_denylist")

    op.drop_index("ix_user_kyc_documents_review_status", table_name="user_kyc_documents")
    op.drop_index("ix_user_kyc_documents_user_id", table_name="user_kyc_documents")
    op.drop_table("user_kyc_documents")

    op.drop_index("ix_user_onboarding_profiles_aml_flag", table_name="user_onboarding_profiles")
    op.drop_index("ix_user_onboarding_profiles_kyc_status", table_name="user_onboarding_profiles")

    for column_name in [
        "precheck_reasons",
        "trading_eligibility",
        "spot_capability",
        "futures_capability",
        "leverage_permission",
        "region_compliance_status",
        "country_code",
        "first_funding_at",
        "balance_usd",
        "api_key_validity",
        "aml_reason",
        "aml_flag",
        "risk_score",
        "kyc_status",
    ]:
        op.drop_column("user_onboarding_profiles", column_name)
