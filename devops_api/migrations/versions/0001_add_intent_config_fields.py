from alembic import op
import sqlalchemy as sa

revision = "0001_add_intent_config_fields"
down_revision = "0000_baseline"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("intents", sa.Column("configure_domain", sa.String(), nullable=True))
    op.add_column("intents", sa.Column("configure_mode", sa.String(), nullable=True))
    op.create_index(
        "ix_intents_type_domain_mode",
        "intents",
        ["intent_type", "configure_domain", "configure_mode"],
        unique=False,
    )

def downgrade():
    op.drop_index("ix_intents_type_domain_mode", table_name="intents")
    op.drop_column("intents", "configure_mode")
    op.drop_column("intents", "configure_domain")
