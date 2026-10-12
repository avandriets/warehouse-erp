from datetime import UTC, datetime
from uuid import uuid4

from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, inspect, select

from alembic import command


def test_currency_rate_migration_preserves_currencies_and_downgrades(
    migration_database_url, monkeypatch
):
    monkeypatch.setenv("APP_DATABASE_URL", migration_database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "20261006_0009")
    engine = create_engine(migration_database_url)
    try:
        table = Table("configuration_currencies", MetaData(), autoload_with=engine)
        currency_id = str(uuid4())
        with engine.begin() as connection:
            connection.execute(
                table.insert().values(
                    id=currency_id,
                    code="EUR",
                    name="Euro",
                    active=True,
                    symbol="€",
                    display_decimal_places=2,
                    rounding_decimal_places=2,
                    rounding_mode="HALF_UP",
                    version=1,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
        command.upgrade(config, "20261011_0010")
        names = inspect(engine).get_table_names()
        assert "configuration_currency_rates" in names
        assert "configuration_currency_rate_batches" in names
        with engine.connect() as connection:
            assert connection.scalar(select(table.c.code).where(table.c.id == currency_id)) == "EUR"
        command.downgrade(config, "20261006_0009")
        names = inspect(engine).get_table_names()
        assert "configuration_currency_rates" not in names
        assert "configuration_currency_rate_batches" not in names
        with engine.connect() as connection:
            assert connection.scalar(select(table.c.code).where(table.c.id == currency_id)) == "EUR"
    finally:
        engine.dispose()
