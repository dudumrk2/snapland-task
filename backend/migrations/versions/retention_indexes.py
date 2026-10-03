"""add_retention_indexes

Revision ID: retention_indexes
Revises: phase4_gist_index
Create Date: 2026-10-04 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'retention_indexes'
down_revision: Union[str, None] = 'phase4_gist_index'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Partial index on soft-deleted areas for retention cleanup query
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_areas_deleted_at
        ON areas (deleted_at)
        WHERE deleted_at IS NOT NULL;
    """)

    # Index on audit_logs.created_at for retention cleanup query
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at
        ON audit_logs (created_at);
    """)

    # Index on sessions.expires_at for retention cleanup query
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sessions_expires_at
        ON sessions (expires_at);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_areas_deleted_at;")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_sessions_expires_at;")
