"""
Migration note: Python-side rename of Chat model's 'mode' attribute to 'chat_mode'.
No database schema change is required, as the DB column remains 'mode'.
This migration is for documentation and codebase consistency only.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260129_rename_mode_to_chat_mode'
down_revision = '20260129_add_mode_to_chats'
branch_labels = None
depends_on = None

def upgrade():
    # No DB change needed; Python-side rename only
    pass

def downgrade():
    # No DB change needed; Python-side rename only
    pass
