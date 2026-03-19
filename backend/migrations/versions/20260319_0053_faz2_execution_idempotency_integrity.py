"""faz2 execution idempotency integrity

Revision ID: 20260319_0053
Revises: 20260318_0052
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260319_0053"
down_revision = "20260318_0052"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_constraint(bind, table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(bind)
    unique_constraints = inspector.get_unique_constraints(table_name)
    return any(item.get("name") == constraint_name for item in unique_constraints)


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "execution_intents"):
        op.execute("UPDATE execution_intents SET intent_id = md5(random()::text || clock_timestamp()::text) WHERE intent_id IS NULL OR btrim(intent_id) = ''")
        op.execute(
            """
            DELETE FROM execution_intents a
            USING execution_intents b
            WHERE a.ctid < b.ctid
              AND a.intent_id = b.intent_id
            """
        )

        if not _has_constraint(bind, "execution_intents", "unique_intent"):
            op.create_unique_constraint("unique_intent", "execution_intents", ["intent_id"])

    if _table_exists(bind, "user_execution_intents") and not _has_column(bind, "user_execution_intents", "idempotency_key"):
        op.add_column("user_execution_intents", sa.Column("idempotency_key", sa.String(length=128), nullable=True))

    if _table_exists(bind, "user_execution_intents"):
        op.execute(
            """
            WITH duplicate_rows AS (
                SELECT id
                FROM (
                    SELECT
                        id,
                        row_number() OVER (
                            PARTITION BY idempotency_key
                            ORDER BY created_at ASC
                        ) AS row_num
                    FROM user_execution_intents
                    WHERE idempotency_key IS NOT NULL
                      AND btrim(idempotency_key) <> ''
                ) ranked
                WHERE ranked.row_num > 1
            )
            UPDATE user_execution_intents
            SET idempotency_key = NULL
            WHERE id IN (SELECT id FROM duplicate_rows)
            """
        )
        if not _has_constraint(bind, "user_execution_intents", "unique_user_execution_intent_idempotency_key"):
            op.create_unique_constraint(
                "unique_user_execution_intent_idempotency_key",
                "user_execution_intents",
                ["idempotency_key"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "user_execution_intents") and _has_constraint(bind, "user_execution_intents", "unique_user_execution_intent_idempotency_key"):
        op.drop_constraint("unique_user_execution_intent_idempotency_key", "user_execution_intents", type_="unique")

    if _table_exists(bind, "user_execution_intents") and _has_column(bind, "user_execution_intents", "idempotency_key"):
        op.drop_column("user_execution_intents", "idempotency_key")

    if _table_exists(bind, "execution_intents") and _has_constraint(bind, "execution_intents", "unique_intent"):
        op.drop_constraint("unique_intent", "execution_intents", type_="unique")
