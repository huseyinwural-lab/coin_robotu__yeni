"""approval orchestration columns

Revision ID: 20260323_0067
Revises: 20260323_0066
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260323_0067"
down_revision = "20260323_0066"
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


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    bind = op.get_bind()
    if not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    bind = op.get_bind()
    if _index_exists(bind, table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    bind = op.get_bind()
    table_name = "risk_orchestrator_approval_requests"
    if not _table_exists(bind, table_name):
        return

    column_specs = [
        ("priority", sa.Column("priority", sa.String(length=20), nullable=False, server_default="SAFE")),
        ("assigned_to", sa.Column("assigned_to", sa.String(), nullable=True)),
        ("assigned_at", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True)),
        ("auto_assigned", sa.Column("auto_assigned", sa.Boolean(), nullable=False, server_default=sa.text("false"))),
        ("warning_escalated_at", sa.Column("warning_escalated_at", sa.DateTime(timezone=True), nullable=True)),
        ("critical_escalated_at", sa.Column("critical_escalated_at", sa.DateTime(timezone=True), nullable=True)),
        ("expired_at", sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True)),
        ("escalation_count", sa.Column("escalation_count", sa.Integer(), nullable=False, server_default="0")),
        ("force_applied", sa.Column("force_applied", sa.Boolean(), nullable=False, server_default=sa.text("false"))),
        ("last_activity_at", sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))),
    ]

    for column_name, column in column_specs:
        if not _column_exists(bind, table_name, column_name):
            op.add_column(table_name, column)

    if _column_exists(bind, table_name, "state"):
        op.execute(
            """
            UPDATE risk_orchestrator_approval_requests
            SET state = CASE
                WHEN state = 'pending_approval' THEN 'pending'
                WHEN state = 'timeout' THEN 'expired'
                ELSE state
            END
            """
        )

    _create_index_if_missing(table_name, "ix_risk_orchestrator_approval_requests_priority", ["priority"])
    _create_index_if_missing(table_name, "ix_risk_orchestrator_approval_requests_assigned_to", ["assigned_to"])
    _create_index_if_missing(table_name, "ix_risk_orchestrator_approval_requests_last_activity_at", ["last_activity_at"])


def downgrade() -> None:
    bind = op.get_bind()
    table_name = "risk_orchestrator_approval_requests"
    if not _table_exists(bind, table_name):
        return

    _drop_index_if_exists(table_name, "ix_risk_orchestrator_approval_requests_last_activity_at")
    _drop_index_if_exists(table_name, "ix_risk_orchestrator_approval_requests_assigned_to")
    _drop_index_if_exists(table_name, "ix_risk_orchestrator_approval_requests_priority")

    for column_name in [
        "last_activity_at",
        "force_applied",
        "escalation_count",
        "expired_at",
        "critical_escalated_at",
        "warning_escalated_at",
        "auto_assigned",
        "assigned_at",
        "assigned_to",
        "priority",
    ]:
        if _column_exists(bind, table_name, column_name):
            op.drop_column(table_name, column_name)
