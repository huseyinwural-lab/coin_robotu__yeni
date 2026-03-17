"""missing domain tables repair

Revision ID: 20260317_0049
Revises: 20260317_0048
Create Date: 2026-03-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20260317_0049"
down_revision = "20260317_0048"
branch_labels = None
depends_on = None


REPAIR_TABLES = [
    "execution_events",
    "external_provider_credentials",
    "position_ledger_events",
    "symbol_selection_watchlists",
    "user_learning_simulation_suggestions",
    "user_onboarding_profiles",
    "user_scanner_symbol_selections",
]


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    from pathlib import Path
    import sys

    backend_root = Path(__file__).resolve().parents[2]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from models import (
        ExecutionEvent,
        ExternalProviderCredential,
        PositionLedgerEvent,
        SymbolSelectionWatchlist,
        UserLearningSimulationSuggestion,
        UserOnboardingProfile,
        UserScannerSymbolSelection,
    )

    bind = op.get_bind()
    table_map = {
        "execution_events": ExecutionEvent.__table__,
        "external_provider_credentials": ExternalProviderCredential.__table__,
        "position_ledger_events": PositionLedgerEvent.__table__,
        "symbol_selection_watchlists": SymbolSelectionWatchlist.__table__,
        "user_learning_simulation_suggestions": UserLearningSimulationSuggestion.__table__,
        "user_onboarding_profiles": UserOnboardingProfile.__table__,
        "user_scanner_symbol_selections": UserScannerSymbolSelection.__table__,
    }

    for table_name in REPAIR_TABLES:
        if _table_exists(bind, table_name):
            continue
        table_map[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    # Repair migration intentionally non-destructive on downgrade.
    pass
