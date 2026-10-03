"""add_gist_index

Revision ID: phase4_gist_index
Revises: 
Create Date: 2026-09-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'phase4_gist_index'
down_revision: Union[str, None] = 'fc8ed7ced749'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent creation of the GiST index
    op.execute("""
        CREATE INDEX IF NOT EXISTS areas_geom_gist 
        ON areas USING GIST (geom) 
        WHERE deleted_at IS NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS areas_geom_gist;")
