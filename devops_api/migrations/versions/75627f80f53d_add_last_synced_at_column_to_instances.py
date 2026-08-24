"""Add last_synced_at column to instances

Revision ID: 75627f80f53d
Revises: 001_add_connection_method
Create Date: 2026-01-25 17:05:43.026138

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '75627f80f53d_add_last_synced_at_column_to_instances'
down_revision = '001_add_connection_method'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('instances', sa.Column('last_synced_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('instances', 'last_synced_at')
