"""merge chat_mode and plan branches

Revision ID: e0378dfde1bd
Revises: 20260129_rename_mode_to_chat_mode, 397172036b25
Create Date: 2026-01-29 18:49:46.042445

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0378dfde1bd'
down_revision: Union[str, Sequence[str], None] = ('20260129_rename_mode_to_chat_mode', '397172036b25')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
