from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from warehouse_erp.catalog.infrastructure import models  # noqa: F401
from warehouse_erp.config import load_settings
from warehouse_erp.configuration.infrastructure import models as configuration_models  # noqa: F401
from warehouse_erp.database import Base
from warehouse_erp.identity.infrastructure import models as identity_models  # noqa: F401
from warehouse_erp.inventory.infrastructure import models as inventory_models  # noqa: F401
from warehouse_erp.settings.infrastructure import models as settings_models  # noqa: F401
from warehouse_erp.warehouse.infrastructure import models as warehouse_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", load_settings().database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
