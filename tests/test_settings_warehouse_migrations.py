from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command


def test_settings_and_warehouse_upgrade_from_existing_catalog(
    migration_database_url: str,
    monkeypatch,
) -> None:
    url = migration_database_url
    monkeypatch.setenv("APP_DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "20260921_0004")
    command.upgrade(config, "head")
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert {
        "settings_categories",
        "settings_definitions",
        "settings_values",
        "warehouses",
        "warehouse_locations",
    } <= tables
    with engine.connect() as connection:
        definitions = (
            connection.execute(text("SELECT `key` FROM settings_definitions ORDER BY `key`"))
            .scalars()
            .all()
        )
        permissions = (
            connection.execute(
                text(
                    "SELECT code FROM identity_permissions "
                    "WHERE code IN ('settings.read', 'warehouse.read') ORDER BY code"
                )
            )
            .scalars()
            .all()
        )
    assert definitions == ["inventory.negative_stock_allowed"]
    assert permissions == ["settings.read", "warehouse.read"]
    engine.dispose()
    command.downgrade(config, "20260921_0004")
