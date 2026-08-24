"""add_extra_column_to_messages

Revision ID: cd859b7730f3
Revises: e0378dfde1bd
Create Date: 2026-02-02 13:34:37.938658

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd859b7730f3'
down_revision: Union[str, Sequence[str], None] = 'e0378dfde1bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('messages', sa.Column('extra', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('messages', 'extra')
