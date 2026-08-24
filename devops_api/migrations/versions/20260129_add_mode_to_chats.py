# revision identifiers, used by Alembic.
revision = '20260129_add_mode_to_chats'
down_revision = '75627f80f53d_add_last_synced_at_column_to_instances'
branch_labels = None
depends_on = None
"""
Add mode column to chats table
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('chats', sa.Column('mode', sa.String(), nullable=False, server_default='free'))


def downgrade():
    op.drop_column('chats', 'mode')
