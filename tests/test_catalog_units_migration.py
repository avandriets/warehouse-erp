"""Exercise the upgrade against a populated MariaDB test catalog."""

from datetime import UTC, datetime
from uuid import uuid4

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command


def test_upgrade_preserves_product_unit_and_barcode(
    migration_database_url: str,
    monkeypatch,
) -> None:
    url = migration_database_url
    monkeypatch.setenv("APP_DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "20260920_0003")
    engine = create_engine(url)
    category_id, unit_id, product_id = (str(uuid4()) for _ in range(3))
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO catalog_categories "
                "(id, code, name, active, created_at, updated_at) "
                "VALUES (:id, 'TOOLS', 'Tools', 1, :now, :now)"
            ),
            {"id": category_id, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO catalog_units "
                "(id, code, name, `precision`, active, created_at, updated_at) "
                "VALUES (:id, 'PCS', 'Pieces', 0, 1, :now, :now)"
            ),
            {"id": unit_id, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO catalog_products "
                "(id, code, name, category_id, unit_id, barcode, attributes, "
                "tracking_mode, issue_strategy, negative_stock_allowed, expiry_required, "
                "mrp_tracking_enabled, quality_tracking_enabled, active, created_at, updated_at) "
                "VALUES (:id, 'BOLT', 'Bolt', :category, :unit, '123456', '{}', "
                "'NONE', 'MANUAL', 0, 0, 0, 0, 1, :now, :now)"
            ),
            {"id": product_id, "category": category_id, "unit": unit_id, "now": now},
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.connect() as connection:
        product = connection.execute(
            text("SELECT storage_unit_id FROM catalog_products WHERE id = :id"), {"id": product_id}
        ).one()
        barcode = connection.execute(
            text("SELECT product_id, value FROM catalog_product_barcodes")
        ).one()
        unit = connection.execute(
            text("SELECT symbol, dimension FROM catalog_units WHERE id = :id"), {"id": unit_id}
        ).one()
    assert product.storage_unit_id == unit_id
    assert tuple(barcode) == (product_id, "123456")
    assert tuple(unit) == ("PCS", "OTHER")
    assert "barcode" not in {
        column["name"] for column in inspect(engine).get_columns("catalog_products")
    }
    engine.dispose()
