from __future__ import annotations
import os
import importlib
import pkgutil
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Base SQLAlchemy ---
from app.database import Base
target_metadata = Base.metadata

# --- Charge TOUTES les sous-modules de app.models pour peupler Base.metadata ---
try:
    import app.models as models_pkg
    for _, modname, _ in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"{models_pkg.__name__}.{modname}")
except Exception as e:
    print(f"[alembic env] Warning: could not import models: {e}")

# --- URL DB via env ---
db_url = os.getenv("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

def include_object(object, name, type_, reflected, compare_to):
    # Ignore la table interne d'Alembic
    if type_ == "table" and name == "alembic_version":
        return False
    return True

def run_migrations_offline() -> None:
    url = db_url or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    if db_url:
        connectable = create_engine(db_url, poolclass=pool.NullPool)
    else:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
