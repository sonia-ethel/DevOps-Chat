"""fix ambiguous FK Execution <-> Intent

Revision ID: 22fa1080927e
Revises: 67ff5cc46a80
Create Date: 2025-09-16 23:18:41.201415
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "22fa1080927e"
down_revision: Union[str, Sequence[str], None] = "67ff5cc46a80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: le fix est côté ORM (relationships/foreign_keys)."""
    pass


def downgrade() -> None:
    """No-op."""
    pass
