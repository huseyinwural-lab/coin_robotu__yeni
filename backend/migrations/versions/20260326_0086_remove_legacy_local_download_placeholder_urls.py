"""remove legacy local://download placeholder urls

Revision ID: 20260326_0086
Revises: 20260326_0085
Create Date: 2026-03-26
"""

from alembic import op


revision = "20260326_0086"
down_revision = "20260326_0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE commercial_export_manifests
        SET signed_download_url = '/api/admin/commercial/exports/local/' || id
        WHERE signed_download_url LIKE 'local://download/%'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE commercial_export_manifests
        SET signed_download_url = 'local://download/' || id
        WHERE signed_download_url LIKE '/api/admin/commercial/exports/local/%'
        """
    )
