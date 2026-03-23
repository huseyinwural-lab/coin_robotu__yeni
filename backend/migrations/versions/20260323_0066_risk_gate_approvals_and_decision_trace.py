"""risk gate approvals and decision trace

Revision ID: 20260323_0066
Revises: ae34519584d9
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260323_0066"
down_revision = "ae34519584d9"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    bind = op.get_bind()
    if not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "risk_orchestrator_approval_requests"):
        op.create_table(
            "risk_orchestrator_approval_requests",
            sa.Column("approval_id", sa.String(length=120), nullable=False),
            sa.Column("request_key", sa.String(length=160), nullable=False),
            sa.Column("flow_type", sa.String(length=30), nullable=False, server_default="apply"),
            sa.Column("simulation_id", sa.String(length=120), nullable=False),
            sa.Column("classification", sa.String(length=20), nullable=False, server_default="SAFE"),
            sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("state", sa.String(length=30), nullable=False, server_default="pending_approval"),
            sa.Column("requested_by", sa.String(), nullable=False),
            sa.Column("requested_role", sa.String(length=40), nullable=False, server_default="admin"),
            sa.Column("reason_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("override_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("second_approver_id", sa.String(), nullable=True),
            sa.Column("second_approver_note", sa.Text(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("context_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("final_decision_trace_id", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["second_approver_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("approval_id"),
        )
        _create_index_if_missing(
            "risk_orchestrator_approval_requests",
            "ix_risk_orchestrator_approval_requests_request_key",
            ["request_key"],
            unique=True,
        )
        _create_index_if_missing("risk_orchestrator_approval_requests", "ix_risk_orchestrator_approval_requests_flow_type", ["flow_type"])
        _create_index_if_missing("risk_orchestrator_approval_requests", "ix_risk_orchestrator_approval_requests_simulation_id", ["simulation_id"])
        _create_index_if_missing("risk_orchestrator_approval_requests", "ix_risk_orchestrator_approval_requests_classification", ["classification"])
        _create_index_if_missing("risk_orchestrator_approval_requests", "ix_risk_orchestrator_approval_requests_state", ["state"])
        _create_index_if_missing("risk_orchestrator_approval_requests", "ix_risk_orchestrator_approval_requests_requested_by", ["requested_by"])
        _create_index_if_missing("risk_orchestrator_approval_requests", "ix_risk_orchestrator_approval_requests_second_approver_id", ["second_approver_id"])
        _create_index_if_missing("risk_orchestrator_approval_requests", "ix_risk_orchestrator_approval_requests_expires_at", ["expires_at"])
        _create_index_if_missing(
            "risk_orchestrator_approval_requests",
            "ix_risk_orchestrator_approval_requests_final_decision_trace_id",
            ["final_decision_trace_id"],
        )
        _create_index_if_missing("risk_orchestrator_approval_requests", "ix_risk_orchestrator_approval_requests_created_at", ["created_at"])

    if not _table_exists(bind, "risk_orchestrator_decision_traces"):
        op.create_table(
            "risk_orchestrator_decision_traces",
            sa.Column("trace_id", sa.String(length=120), nullable=False),
            sa.Column("flow_type", sa.String(length=30), nullable=False, server_default="apply"),
            sa.Column("simulation_id", sa.String(length=120), nullable=False),
            sa.Column("classification", sa.String(length=20), nullable=False, server_default="SAFE"),
            sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("rule_path", sa.String(length=120), nullable=False, server_default="SAFE_DIRECT_APPLY"),
            sa.Column("decision_state", sa.String(length=30), nullable=False, server_default="applied"),
            sa.Column("requested_by", sa.String(), nullable=False),
            sa.Column("approver_id", sa.String(), nullable=True),
            sa.Column("request_key", sa.String(length=160), nullable=False),
            sa.Column("reason_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("approval_note", sa.Text(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["approver_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("trace_id"),
        )
        _create_index_if_missing("risk_orchestrator_decision_traces", "ix_risk_orchestrator_decision_traces_flow_type", ["flow_type"])
        _create_index_if_missing("risk_orchestrator_decision_traces", "ix_risk_orchestrator_decision_traces_simulation_id", ["simulation_id"])
        _create_index_if_missing("risk_orchestrator_decision_traces", "ix_risk_orchestrator_decision_traces_classification", ["classification"])
        _create_index_if_missing("risk_orchestrator_decision_traces", "ix_risk_orchestrator_decision_traces_decision_state", ["decision_state"])
        _create_index_if_missing("risk_orchestrator_decision_traces", "ix_risk_orchestrator_decision_traces_requested_by", ["requested_by"])
        _create_index_if_missing("risk_orchestrator_decision_traces", "ix_risk_orchestrator_decision_traces_approver_id", ["approver_id"])
        _create_index_if_missing("risk_orchestrator_decision_traces", "ix_risk_orchestrator_decision_traces_request_key", ["request_key"])
        _create_index_if_missing("risk_orchestrator_decision_traces", "ix_risk_orchestrator_decision_traces_created_at", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "risk_orchestrator_decision_traces"):
        op.drop_table("risk_orchestrator_decision_traces")
    if _table_exists(bind, "risk_orchestrator_approval_requests"):
        op.drop_table("risk_orchestrator_approval_requests")
