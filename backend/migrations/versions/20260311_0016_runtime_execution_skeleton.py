"""runtime execution skeleton tables

Revision ID: 20260311_0016
Revises: 20260311_0015
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0016"
down_revision = "20260311_0015"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "execution_intents"):
        op.create_table(
            "execution_intents",
            sa.Column("intent_id", sa.String(), nullable=False),
            sa.Column("strategy_id", sa.String(), nullable=False),
            sa.Column("strategy_version_id", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("side", sa.String(length=20), nullable=False),
            sa.Column("order_type", sa.String(length=20), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("price_reference", sa.JSON(), nullable=False),
            sa.Column("decision_hash", sa.String(length=128), nullable=False),
            sa.Column("context_hash", sa.String(length=128), nullable=False),
            sa.Column("intent_hash", sa.String(length=128), nullable=False),
            sa.Column("correlation_id", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["strategy_id"], ["strategy_definitions.strategy_id"]),
            sa.ForeignKeyConstraint(["strategy_version_id"], ["strategy_versions.version_id"]),
            sa.PrimaryKeyConstraint("intent_id"),
            sa.UniqueConstraint("intent_hash"),
        )
        op.create_index("ix_execution_intents_strategy_id", "execution_intents", ["strategy_id"], unique=False)
        op.create_index("ix_execution_intents_strategy_version_id", "execution_intents", ["strategy_version_id"], unique=False)
        op.create_index("ix_execution_intents_decision_hash", "execution_intents", ["decision_hash"], unique=False)
        op.create_index("ix_execution_intents_context_hash", "execution_intents", ["context_hash"], unique=False)
        op.create_index("ix_execution_intents_intent_hash", "execution_intents", ["intent_hash"], unique=True)
        op.create_index("ix_execution_intents_correlation_id", "execution_intents", ["correlation_id"], unique=False)

    if not _table_exists(bind, "execution_intent_events"):
        op.create_table(
            "execution_intent_events",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("intent_id", sa.String(), nullable=False),
            sa.Column("event_type", sa.String(length=60), nullable=False),
            sa.Column("event_status", sa.String(length=20), nullable=False),
            sa.Column("external_order_id", sa.String(length=80), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["intent_id"], ["execution_intents.intent_id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_execution_intent_events_intent_id", "execution_intent_events", ["intent_id"], unique=False)
        op.create_index("ix_execution_intent_events_event_type", "execution_intent_events", ["event_type"], unique=False)

    if not _table_exists(bind, "decision_trace_hot"):
        op.create_table(
            "decision_trace_hot",
            sa.Column("trace_id", sa.String(), nullable=False),
            sa.Column("correlation_id", sa.String(length=120), nullable=False),
            sa.Column("strategy_version_id", sa.String(), nullable=False),
            sa.Column("context_hash", sa.String(length=128), nullable=False),
            sa.Column("decision_hash", sa.String(length=128), nullable=False),
            sa.Column("intent_hash", sa.String(length=128), nullable=True),
            sa.Column("context_payload", sa.JSON(), nullable=False),
            sa.Column("decision_payload", sa.JSON(), nullable=False),
            sa.Column("intent_payload", sa.JSON(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["strategy_version_id"], ["strategy_versions.version_id"]),
            sa.PrimaryKeyConstraint("trace_id"),
        )
        op.create_index("ix_decision_trace_hot_correlation_id", "decision_trace_hot", ["correlation_id"], unique=False)
        op.create_index("ix_decision_trace_hot_strategy_version_id", "decision_trace_hot", ["strategy_version_id"], unique=False)
        op.create_index("ix_decision_trace_hot_context_hash", "decision_trace_hot", ["context_hash"], unique=False)
        op.create_index("ix_decision_trace_hot_decision_hash", "decision_trace_hot", ["decision_hash"], unique=False)

    if not _table_exists(bind, "decision_trace_cold"):
        op.create_table(
            "decision_trace_cold",
            sa.Column("archive_id", sa.String(), nullable=False),
            sa.Column("correlation_id", sa.String(length=120), nullable=False),
            sa.Column("strategy_version_id", sa.String(), nullable=False),
            sa.Column("context_hash", sa.String(length=128), nullable=False),
            sa.Column("decision_hash", sa.String(length=128), nullable=False),
            sa.Column("intent_hash", sa.String(length=128), nullable=True),
            sa.Column("artifact_id", sa.String(length=80), nullable=True),
            sa.Column("lifecycle_summary", sa.JSON(), nullable=False),
            sa.Column("terminal_state", sa.String(length=30), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["strategy_version_id"], ["strategy_versions.version_id"]),
            sa.PrimaryKeyConstraint("archive_id"),
        )
        op.create_index("ix_decision_trace_cold_correlation_id", "decision_trace_cold", ["correlation_id"], unique=False)
        op.create_index("ix_decision_trace_cold_strategy_version_id", "decision_trace_cold", ["strategy_version_id"], unique=False)
        op.create_index("ix_decision_trace_cold_context_hash", "decision_trace_cold", ["context_hash"], unique=False)
        op.create_index("ix_decision_trace_cold_decision_hash", "decision_trace_cold", ["decision_hash"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "decision_trace_cold"):
        op.drop_index("ix_decision_trace_cold_decision_hash", table_name="decision_trace_cold")
        op.drop_index("ix_decision_trace_cold_context_hash", table_name="decision_trace_cold")
        op.drop_index("ix_decision_trace_cold_strategy_version_id", table_name="decision_trace_cold")
        op.drop_index("ix_decision_trace_cold_correlation_id", table_name="decision_trace_cold")
        op.drop_table("decision_trace_cold")

    if _table_exists(bind, "decision_trace_hot"):
        op.drop_index("ix_decision_trace_hot_decision_hash", table_name="decision_trace_hot")
        op.drop_index("ix_decision_trace_hot_context_hash", table_name="decision_trace_hot")
        op.drop_index("ix_decision_trace_hot_strategy_version_id", table_name="decision_trace_hot")
        op.drop_index("ix_decision_trace_hot_correlation_id", table_name="decision_trace_hot")
        op.drop_table("decision_trace_hot")

    if _table_exists(bind, "execution_intent_events"):
        op.drop_index("ix_execution_intent_events_event_type", table_name="execution_intent_events")
        op.drop_index("ix_execution_intent_events_intent_id", table_name="execution_intent_events")
        op.drop_table("execution_intent_events")

    if _table_exists(bind, "execution_intents"):
        op.drop_index("ix_execution_intents_correlation_id", table_name="execution_intents")
        op.drop_index("ix_execution_intents_intent_hash", table_name="execution_intents")
        op.drop_index("ix_execution_intents_context_hash", table_name="execution_intents")
        op.drop_index("ix_execution_intents_decision_hash", table_name="execution_intents")
        op.drop_index("ix_execution_intents_strategy_version_id", table_name="execution_intents")
        op.drop_index("ix_execution_intents_strategy_id", table_name="execution_intents")
        op.drop_table("execution_intents")
