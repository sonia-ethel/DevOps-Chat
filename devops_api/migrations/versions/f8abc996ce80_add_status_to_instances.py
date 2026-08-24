from alembic import op
import sqlalchemy as sa

# Alembic identifiers
revision = "f8abc996ce80"
down_revision = "22fa1080927e"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Variante portable (si la colonne n'existe pas déjà)
    # op.add_column("instances", sa.Column("status", sa.String(), nullable=True))

    # Variante idempotente spécifique PostgreSQL (évite les collisions en dev)
    op.execute('ALTER TABLE instances ADD COLUMN IF NOT EXISTS status VARCHAR')

def downgrade() -> None:
    # Portable:
    # op.drop_column("instances", "status")

    # Idempotent PostgreSQL:
    op.execute('ALTER TABLE instances DROP COLUMN IF EXISTS status')
