"""Verify migration and rollback against populated legacy policy data."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from alembic.config import Config
from sqlalchemy import JSON, MetaData, Table, create_engine, inspect, select

from alembic import command


def test_warehouse_policy_migration_preserves_expiry_and_archives_legacy(
    migration_database_url: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_DATABASE_URL", migration_database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "20260929_0007")
    engine = create_engine(migration_database_url)
    metadata = MetaData()
    names = (
        "identity_users",
        "warehouses",
        "catalog_categories",
        "catalog_units",
        "catalog_products",
        "settings_definitions",
        "settings_values",
    )
    tables = {name: Table(name, metadata, autoload_with=engine) for name in names}
    tables["catalog_products"].c.attributes.type = JSON()
    tables["settings_values"].c.value.type = JSON()
    actor_id, warehouse_id, category_id, unit_id, product_id, override_id = (
        str(uuid4()) for _ in range(6)
    )
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            tables["identity_users"]
            .insert()
            .values(
                id=actor_id,
                auth0_subject="auth0|legacy",
                email="legacy@example.test",
                display_name="Legacy",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            tables["warehouses"]
            .insert()
            .values(
                id=warehouse_id,
                code="MAIN",
                name="Main",
                active=True,
                created_at=now,
                updated_at=now,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        connection.execute(
            tables["catalog_categories"]
            .insert()
            .values(
                id=category_id,
                code="GOODS",
                name="Goods",
                active=True,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            tables["catalog_units"]
            .insert()
            .values(
                id=unit_id,
                code="PCS",
                name="Pieces",
                symbol="pcs",
                dimension="COUNT",
                precision=0,
                active=True,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            tables["catalog_products"]
            .insert()
            .values(
                id=product_id,
                code="EXPIRY",
                name="Expiry",
                category_id=category_id,
                storage_unit_id=unit_id,
                attributes={},
                tracking_mode="BATCH",
                issue_strategy="FEFO",
                negative_stock_allowed=True,
                expiry_required=True,
                mrp_tracking_enabled=True,
                quality_tracking_enabled=False,
                active=True,
                created_at=now,
                updated_at=now,
            )
        )
        definition_id = connection.execute(
            select(tables["settings_definitions"].c.id).where(
                tables["settings_definitions"].c.key == "inventory.default_issue_strategy"
            )
        ).scalar_one()
        connection.execute(
            tables["settings_values"]
            .insert()
            .values(
                id=override_id,
                definition_id=definition_id,
                scope_type="PRODUCT",
                scope_id=product_id,
                scope_key=product_id,
                value="FEFO",
                version=2,
                updated_at=now,
                updated_by=actor_id,
            )
        )
    command.upgrade(config, "head")
    metadata = MetaData()
    products = Table("catalog_products", metadata, autoload_with=engine)
    warehouses = Table("warehouses", metadata, autoload_with=engine)
    archive = Table("inventory_policy_legacy", metadata, autoload_with=engine)
    definitions = Table("settings_definitions", metadata, autoload_with=engine)
    values = Table("settings_values", metadata, autoload_with=engine)
    archive.c.payload.type = JSON()
    values.c.value.type = JSON()
    with engine.connect() as connection:
        product = connection.execute(select(products).where(products.c.id == product_id)).one()
        assert product.batch_expiry_required
        warehouse = connection.execute(
            select(warehouses).where(warehouses.c.id == warehouse_id)
        ).one()
        assert (warehouse.tracking_mode, warehouse.issue_strategy) == ("NONE", "MANUAL")
        archived = connection.execute(
            select(archive.c.payload).where(
                archive.c.kind == "PRODUCT",
                archive.c.id == product_id,
            )
        ).scalar_one()
        if isinstance(archived, str):
            archived = json.loads(archived)
        assert archived["tracking_mode"] == "BATCH"
        assert archived["issue_strategy"] == "FEFO"
        assert archived["mrp_tracking_enabled"]
        assert (
            connection.execute(
                select(definitions.c.id).where(
                    definitions.c.key == "inventory.default_issue_strategy"
                )
            ).first()
            is None
        )
        assert (
            connection.execute(
                select(values.c.value).where(
                    values.c.scope_type == "PRODUCT",
                    values.c.scope_id == product_id,
                )
            ).scalar_one()
            is True
        )
    assert "tracking_mode" not in products.c
    assert "expiry_required" not in products.c
    command.downgrade(config, "20260929_0007")
    metadata = MetaData()
    products = Table("catalog_products", metadata, autoload_with=engine)
    values = Table("settings_values", metadata, autoload_with=engine)
    values.c.value.type = JSON()
    with engine.connect() as connection:
        product = connection.execute(select(products).where(products.c.id == product_id)).one()
        assert (product.tracking_mode, product.issue_strategy) == ("BATCH", "FEFO")
        assert product.expiry_required and product.negative_stock_allowed
        assert product.mrp_tracking_enabled
        restored = connection.execute(select(values).where(values.c.id == override_id)).one()
        assert restored.value == "FEFO" and restored.version == 2
        assert connection.execute(
            select(values.c.id).where(
                values.c.scope_type == "PRODUCT",
                values.c.scope_id == product_id,
            )
        ).scalars().all() == [override_id]
    assert "inventory_policy_legacy" not in inspect(engine).get_table_names()
    engine.dispose()
