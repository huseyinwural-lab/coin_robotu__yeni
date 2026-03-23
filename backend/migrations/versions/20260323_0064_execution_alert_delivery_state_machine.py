"""execution alert delivery state machine

Revision ID: 20260323_0064
Revises: 20260323_0063
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260323_0064"
down_revision = "20260323_0063"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    if not _column_exists(bind, table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    bind = op.get_bind()
    if not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "system_alerts"):
        _add_column_if_missing("system_alerts", sa.Column("delivery_provider", sa.String(length=40), nullable=True))
        _add_column_if_missing("system_alerts", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
        _add_column_if_missing("system_alerts", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
        _add_column_if_missing("system_alerts", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
        _add_column_if_missing("system_alerts", sa.Column("last_error_code", sa.String(length=80), nullable=True))
        _add_column_if_missing("system_alerts", sa.Column("last_error_message", sa.Text(), nullable=True))
        _create_index_if_missing("system_alerts", "ix_system_alerts_next_retry_at", ["next_retry_at"])
        _create_index_if_missing("system_alerts", "ix_system_alerts_delivery_provider", ["delivery_provider"])

    if not _table_exists(bind, "execution_alert_delivery_attempts"):
        op.create_table(
            "execution_alert_delivery_attempts",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("alert_id", sa.String(), sa.ForeignKey("system_alerts.id"), nullable=False),
            sa.Column("provider", sa.String(length=40), nullable=False, server_default="slack"),
            sa.Column("destination_masked", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("request_timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("request_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("response_code", sa.Integer(), nullable=True),
            sa.Column("response_body_truncated", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
            sa.Column("final_status", sa.String(length=30), nullable=False, server_default="PENDING"),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_code", sa.String(length=80), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    _create_index_if_missing("execution_alert_delivery_attempts", "ix_execution_alert_delivery_attempts_alert_id", ["alert_id"])
    _create_index_if_missing("execution_alert_delivery_attempts", "ix_execution_alert_delivery_attempts_status", ["status"])
    _create_index_if_missing("execution_alert_delivery_attempts", "ix_execution_alert_delivery_attempts_request_timestamp", ["request_timestamp"])
    _create_index_if_missing("execution_alert_delivery_attempts", "ix_execution_alert_delivery_attempts_next_retry_at", ["next_retry_at"])


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "execution_alert_delivery_attempts"):
        op.drop_table("execution_alert_delivery_attempts")

    if _table_exists(bind, "system_alerts"):
        inspector = sa.inspect(bind)
        existing_columns = {column["name"] for column in inspector.get_columns("system_alerts")}
        for index_name in ["ix_system_alerts_next_retry_at", "ix_system_alerts_delivery_provider"]:
            if _index_exists(bind, "system_alerts", index_name):
                op.drop_index(index_name, table_name="system_alerts")
        for column_name in [
            "last_error_message",
            "last_error_code",
            "attempt_count",
            "next_retry_at",
            "last_attempt_at",
            "delivery_provider",
        ]:
            if column_name in existing_columns:
                op.drop_column("system_alerts", column_name)
