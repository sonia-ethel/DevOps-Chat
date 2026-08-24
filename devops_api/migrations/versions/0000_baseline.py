from alembic import op
import sqlalchemy as sa

revision = "0000_baseline"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # baseline: ne change rien, crée juste alembic_version si besoin
    pass

def downgrade():
    pass
