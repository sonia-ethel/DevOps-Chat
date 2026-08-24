"""add generation_status fields to intents

Revision ID: 67ff5cc46a80
Revises: 0001_add_intent_config_fields
Create Date: 2025-09-16 21:44:10.320912
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '67ff5cc46a80'
down_revision: Union[str, Sequence[str], None] = '0001_add_intent_config_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ENUM_NAME = "generationstatus"
ENUM_VALUES = ("pending", "generating", "generated", "failed")


def upgrade() -> None:
    # 1) Créer l'ENUM PostgreSQL si besoin
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{ENUM_NAME}') THEN
                CREATE TYPE {ENUM_NAME} AS ENUM {ENUM_VALUES};
            END IF;
        END$$;
        """
    )

    # 2) Ajouter les colonnes sur 'intents'
    op.add_column(
        "intents",
        sa.Column(
            "generation_status",
            sa.Enum(*ENUM_VALUES, name=ENUM_NAME, create_type=False),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("intents", sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("intents", sa.Column("generation_error", sa.Text(), nullable=True))
    op.add_column("intents", sa.Column("execution_id", sa.Integer(), nullable=True))
    op.add_column("intents", sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("intents", sa.Column("generation_batch_id", sa.String(), nullable=True))

    # 3) Index complémentaires
    op.create_index("ix_intents_session_status", "intents", ["session_id", "generation_status"], unique=False)
    op.create_index("ix_intents_type", "intents", ["intent_type"], unique=False)

    # 4) (optionnel) contrainte FK si vous reliez execution_id -> executions.id plus tard
    #    op.create_foreign_key("intents_execution_id_fkey", "intents", "executions", ["execution_id"], ["id"])

    # 5) retirer le server_default pour de futures insertions explicites
    with op.batch_alter_table("intents") as batch_op:
        batch_op.alter_column("generation_status", server_default=None)


def downgrade() -> None:
    # 1) Drop indexes
    op.drop_index("ix_intents_type", table_name="intents")
    op.drop_index("ix_intents_session_status", table_name="intents")

    # 2) Drop columns
    op.drop_column("intents", "generation_batch_id")
    op.drop_column("intents", "executed_at")
    op.drop_column("intents", "execution_id")
    op.drop_column("intents", "generation_error")
    op.drop_column("intents", "generated_at")
    op.drop_column("intents", "generation_status")

    # 3) Drop ENUM si plus utilisé (safe-ish)
    op.execute(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_type WHERE typname = '{ENUM_NAME}') THEN DROP TYPE {ENUM_NAME}; END IF; END$$;")
