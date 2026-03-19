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


def _duplicate_examples(bind, *, table_name: str, column_name: str, where_clause: str, limit: int = 10) -> list[tuple[str, int]]:
    rows = bind.execute(
        sa.text(
            f"""
            SELECT {column_name}::text AS key_value, COUNT(*)::int AS duplicate_count
            FROM {table_name}
            WHERE {where_clause}
            GROUP BY {column_name}
            HAVING COUNT(*) > 1
            ORDER BY duplicate_count DESC, key_value ASC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).fetchall()
    return [(str(row[0]), int(row[1])) for row in rows]


def _assert_fail_fast_no_duplicates(bind, *, table_name: str, column_name: str, where_clause: str, policy_name: str) -> None:
    examples = _duplicate_examples(
        bind,
        table_name=table_name,
        column_name=column_name,
        where_clause=where_clause,
        limit=10,
    )
    if not examples:
        return

    duplicate_total = sum(item[1] for item in examples)
    sample_repr = ", ".join(f"{value}:{count}" for value, count in examples)
    raise RuntimeError(
        f"[{policy_name}] duplicate {column_name} detected in {table_name}; "
        f"sample_total={duplicate_total}; sample_values={sample_repr}. "
        "Migration fail-fast policy blocked automatic cleanup."
    )


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "execution_intents"):
        null_or_blank_count = bind.execute(
            sa.text("SELECT COUNT(*) FROM execution_intents WHERE intent_id IS NULL OR btrim(intent_id) = ''")
        ).scalar() or 0
        if int(null_or_blank_count) > 0:
            raise RuntimeError(
                "[faz2_execution_intents] execution_intents.intent_id contains NULL/blank rows. "
                "Fail-fast policy forbids silent normalization."
            )

        _assert_fail_fast_no_duplicates(
            bind,
            table_name="execution_intents",
            column_name="intent_id",
            where_clause="intent_id IS NOT NULL AND btrim(intent_id) <> ''",
            policy_name="faz2_execution_intents",
        )

        if not _has_constraint(bind, "execution_intents", "unique_intent"):
            op.create_unique_constraint("unique_intent", "execution_intents", ["intent_id"])

    if _table_exists(bind, "user_execution_intents"):
        if not _has_column(bind, "user_execution_intents", "intent_id"):
            op.add_column("user_execution_intents", sa.Column("intent_id", sa.String(length=128), nullable=True))

        if not _has_column(bind, "user_execution_intents", "idempotency_key"):
            op.add_column("user_execution_intents", sa.Column("idempotency_key", sa.String(length=128), nullable=True))

        op.execute(
            """
            UPDATE user_execution_intents
            SET intent_id = id
            WHERE intent_id IS NULL OR btrim(intent_id) = ''
            """
        )

        null_or_blank_intent_count = bind.execute(
            sa.text("SELECT COUNT(*) FROM user_execution_intents WHERE intent_id IS NULL OR btrim(intent_id) = ''")
        ).scalar() or 0
        if int(null_or_blank_intent_count) > 0:
            raise RuntimeError(
                "[faz2_user_execution_intents] user_execution_intents.intent_id contains NULL/blank rows. "
                "Fail-fast policy blocked migration."
            )

        _assert_fail_fast_no_duplicates(
            bind,
            table_name="user_execution_intents",
            column_name="intent_id",
            where_clause="intent_id IS NOT NULL AND btrim(intent_id) <> ''",
            policy_name="faz2_user_execution_intents_intent_id",
        )

        _assert_fail_fast_no_duplicates(
            bind,
            table_name="user_execution_intents",
            column_name="idempotency_key",
            where_clause="idempotency_key IS NOT NULL AND btrim(idempotency_key) <> ''",
            policy_name="faz2_user_execution_intents_idempotency_key",
        )

        op.alter_column("user_execution_intents", "intent_id", existing_type=sa.String(length=128), nullable=False)

        if not _has_constraint(bind, "user_execution_intents", "unique_user_execution_intent_intent_id"):
            op.create_unique_constraint(
                "unique_user_execution_intent_intent_id",
                "user_execution_intents",
                ["intent_id"],
            )

        if not _has_constraint(bind, "user_execution_intents", "unique_user_execution_intent_idempotency_key"):
            op.create_unique_constraint(
                "unique_user_execution_intent_idempotency_key",
                "user_execution_intents",
                ["idempotency_key"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "user_execution_intents") and _has_constraint(bind, "user_execution_intents", "unique_user_execution_intent_intent_id"):
        op.drop_constraint("unique_user_execution_intent_intent_id", "user_execution_intents", type_="unique")

    if _table_exists(bind, "user_execution_intents") and _has_constraint(bind, "user_execution_intents", "unique_user_execution_intent_idempotency_key"):
        op.drop_constraint("unique_user_execution_intent_idempotency_key", "user_execution_intents", type_="unique")

    if _table_exists(bind, "user_execution_intents") and _has_column(bind, "user_execution_intents", "intent_id"):
        op.drop_column("user_execution_intents", "intent_id")

    if _table_exists(bind, "user_execution_intents") and _has_column(bind, "user_execution_intents", "idempotency_key"):
        op.drop_column("user_execution_intents", "idempotency_key")

    if _table_exists(bind, "execution_intents") and _has_constraint(bind, "execution_intents", "unique_intent"):
        op.drop_constraint("unique_intent", "execution_intents", type_="unique")
