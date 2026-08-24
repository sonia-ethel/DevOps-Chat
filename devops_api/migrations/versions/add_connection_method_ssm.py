"""Add connection_method and ssm_managed to instances

Revision ID: 001_add_connection_method
Revises: 
Create Date: 2026-01-25 04:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_add_connection_method'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ajouter les colonnes sans contrainte pour éviter les erreurs
    op.add_column('instances', sa.Column('connection_method', sa.String(), nullable=True))
    op.add_column('instances', sa.Column('ssm_managed', sa.Boolean(), nullable=True))
    
    # Définir les valeurs par défaut pour les lignes existantes
    op.execute("UPDATE instances SET connection_method = 'ssh' WHERE connection_method IS NULL")
    op.execute("UPDATE instances SET ssm_managed = false WHERE ssm_managed IS NULL")
    
    # Rendre les colonnes NOT NULL
    op.alter_column('instances', 'connection_method', nullable=False)
    op.alter_column('instances', 'ssm_managed', nullable=False)


def downgrade() -> None:
    op.drop_column('instances', 'ssm_managed')
    op.drop_column('instances', 'connection_method')
