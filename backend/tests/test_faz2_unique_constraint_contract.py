# ruff: noqa: E402
import sys
from pathlib import Path

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db import SessionLocal


ARTIFACT_PATH = Path("/app/artifacts/faz2_unique_constraint_check.log")


def test_faz2_unique_constraint_contract_and_migration_state():
    db = SessionLocal()
    try:
        alembic_version = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()

        execution_unique = db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.table_constraints
                WHERE table_name = 'execution_intents'
                  AND constraint_name = 'unique_intent'
                  AND constraint_type = 'UNIQUE'
                """
            )
        ).scalar()

        execution_null_count = db.execute(text("SELECT COUNT(*) FROM execution_intents WHERE intent_id IS NULL OR btrim(intent_id) = ''")).scalar()

        user_idempotency_unique = db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.table_constraints
                WHERE table_name = 'user_execution_intents'
                  AND constraint_name = 'unique_user_execution_intent_idempotency_key'
                  AND constraint_type = 'UNIQUE'
                """
            )
        ).scalar()

        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_text(
            "\n".join(
                [
                    "FAZ2_UNIQUE_CONSTRAINT_CHECK_START",
                    f"MIGRATION_VERSION={alembic_version}",
                    f"UNIQUE_INTENT_CONSTRAINT_COUNT={int(execution_unique or 0)}",
                    f"EXECUTION_INTENTS_NULL_INTENT_ID_COUNT={int(execution_null_count or 0)}",
                    f"USER_IDEMPOTENCY_UNIQUE_CONSTRAINT_COUNT={int(user_idempotency_unique or 0)}",
                    "FAZ2_UNIQUE_CONSTRAINT_CHECK_PASS",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        assert int(execution_unique or 0) == 1
        assert int(execution_null_count or 0) == 0
        assert int(user_idempotency_unique or 0) == 1
    finally:
        db.close()
