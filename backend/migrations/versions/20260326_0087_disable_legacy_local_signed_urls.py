"""disable legacy local signed urls in manifests

Revision ID: 20260326_0087
Revises: 20260326_0086
Create Date: 2026-03-26
"""

from alembic import op


revision = "20260326_0087"
down_revision = "20260326_0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE commercial_export_manifests
        SET signed_download_url = NULL,
            downloadable_state = 'not_ready'
        WHERE signed_download_url LIKE '/api/admin/commercial/exports/local/%'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE commercial_export_manifests
        SET signed_download_url = '/api/admin/commercial/exports/local/' || id,
            downloadable_state = 'ready'
        WHERE signed_download_url IS NULL
          AND artifact_ref LIKE '/tmp/commercial_exports/%'
        """
    )
