"""Move inventory tracking/allocation from products to warehouses.

Legacy product policies and scoped issue defaults are archived, not assigned to
warehouses by guesswork. No stock ledger exists at this revision. Configure each
warehouse explicitly before introducing stock posting.

Revision ID: 20261002_0008
Revises: 20260929_0007
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0008"
down_revision: str | None = "20260929_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_KEY = "inventory.default_issue_strategy"
PRODUCT_COLUMNS = (
    "tracking_mode",
    "issue_strategy",
    "negative_stock_allowed",
    "expiry_required",
    "mrp_tracking_enabled",
    "quality_tracking_enabled",
)
PRODUCT_CHECKS = {
    "ck_product_tracking_mode": "tracking_mode IN ('NONE', 'BATCH')",
    "ck_product_issue_strategy": "issue_strategy IN ('MANUAL', 'FIFO', 'FEFO')",
    "ck_product_expiry_requires_batch": "expiry_required = false OR tracking_mode = 'BATCH'",
    "ck_product_fefo_requires_batch": "issue_strategy != 'FEFO' OR tracking_mode = 'BATCH'",
}
WAREHOUSE_CHECKS = {
    "ck_warehouse_tracking_mode": "tracking_mode IN ('NONE', 'BATCH')",
    "ck_warehouse_issue_strategy": "issue_strategy IN ('MANUAL', 'FIFO', 'FEFO')",
    "ck_warehouse_strategy_requires_batch": "tracking_mode = 'BATCH' OR issue_strategy = 'MANUAL'",
}


def _tables() -> tuple[sa.Table, sa.Table, sa.Table, sa.Table]:
    metadata = sa.MetaData()
    connection = op.get_bind()
    tables = tuple(
        sa.Table(name, metadata, autoload_with=connection)
        for name in (
            "catalog_products",
            "settings_definitions",
            "settings_values",
            "inventory_policy_legacy",
        )
    )
    # MariaDB reflects JSON aliases as LONGTEXT. Restore processors explicitly.
    for column in ("default_value", "allowed_scopes", "options"):
        tables[1].c[column].type = sa.JSON()
    tables[2].c.value.type = sa.JSON()
    tables[3].c.payload.type = sa.JSON()
    return tables


def _archive(archive: sa.Table, kind: str, row: dict) -> None:
    payload = {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in row.items()
        if key != "id"
    }
    op.get_bind().execute(archive.insert().values(kind=kind, id=row["id"], payload=payload))


def upgrade() -> None:
    # MariaDB DDL commits implicitly: validate audit prerequisites before any DDL.
    connection = op.get_bind()
    users = sa.Table("identity_users", sa.MetaData(), autoload_with=connection)
    old_products = sa.Table("catalog_products", sa.MetaData(), autoload_with=connection)
    actor = connection.execute(
        sa.select(users.c.id).order_by(users.c.created_at, users.c.id)
    ).first()
    has_opt_ins = connection.execute(
        sa.select(old_products.c.id).where(old_products.c.negative_stock_allowed.is_(True)).limit(1)
    ).first()
    if actor is None and has_opt_ins:
        raise RuntimeError("An identity user is required to migrate negative-stock opt-ins")
    op.create_table(
        "inventory_policy_legacy",
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    products, definitions, values, archive = _tables()
    connection = op.get_bind()
    legacy_products = (
        connection.execute(sa.select(products.c.id, *(products.c[key] for key in PRODUCT_COLUMNS)))
        .mappings()
        .all()
    )
    for row in legacy_products:
        _archive(archive, "PRODUCT", dict(row))
    legacy_definition = (
        connection.execute(sa.select(definitions).where(definitions.c.key == LEGACY_KEY))
        .mappings()
        .first()
    )
    if legacy_definition:
        _archive(archive, "DEFINITION", dict(legacy_definition))
        for row in (
            connection.execute(
                sa.select(values).where(values.c.definition_id == legacy_definition["id"])
            )
            .mappings()
            .all()
        ):
            _archive(archive, "VALUE", dict(row))
        connection.execute(values.delete().where(values.c.definition_id == legacy_definition["id"]))
        connection.execute(definitions.delete().where(definitions.c.id == legacy_definition["id"]))

    # Preserve explicit legacy opt-ins without overriding existing scoped settings.
    negative_definition = connection.execute(
        sa.select(definitions.c.id).where(definitions.c.key == "inventory.negative_stock_allowed")
    ).scalar_one()
    for row in legacy_products:
        if not row["negative_stock_allowed"]:
            continue
        exists = connection.execute(
            sa.select(values.c.id).where(
                values.c.definition_id == negative_definition,
                values.c.scope_type == "PRODUCT",
                values.c.scope_id == row["id"],
            )
        ).first()
        if exists:
            continue
        if actor is None:
            raise RuntimeError(
                "An identity user is required to migrate legacy negative-stock opt-ins"
            )
        item_id = str(uuid4())
        connection.execute(
            values.insert().values(
                id=item_id,
                definition_id=negative_definition,
                scope_type="PRODUCT",
                scope_id=row["id"],
                scope_key=row["id"],
                value=True,
                version=1,
                updated_at=datetime.now(),
                updated_by=actor[0],
            )
        )
        _archive(archive, "MIGRATED_NEGATIVE", {"id": item_id})

    with op.batch_alter_table("warehouses") as batch:
        batch.add_column(
            sa.Column("tracking_mode", sa.String(16), nullable=False, server_default="NONE")
        )
        batch.add_column(
            sa.Column("issue_strategy", sa.String(16), nullable=False, server_default="MANUAL")
        )
        for name, condition in WAREHOUSE_CHECKS.items():
            batch.create_check_constraint(name, condition)
        batch.alter_column("tracking_mode", existing_type=sa.String(16), server_default=None)
        batch.alter_column("issue_strategy", existing_type=sa.String(16), server_default=None)
    with op.batch_alter_table("catalog_products") as batch:
        for name in PRODUCT_CHECKS:
            batch.drop_constraint(name, type_="check")
        batch.alter_column(
            "expiry_required",
            new_column_name="batch_expiry_required",
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )
        for key in PRODUCT_COLUMNS:
            if key != "expiry_required":
                batch.drop_column(key)


def downgrade() -> None:
    with op.batch_alter_table("catalog_products") as batch:
        batch.alter_column(
            "batch_expiry_required",
            new_column_name="expiry_required",
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )
        batch.add_column(
            sa.Column("tracking_mode", sa.String(16), nullable=False, server_default="NONE")
        )
        batch.add_column(
            sa.Column("issue_strategy", sa.String(16), nullable=False, server_default="MANUAL")
        )
        for key in ("negative_stock_allowed", "mrp_tracking_enabled", "quality_tracking_enabled"):
            batch.add_column(
                sa.Column(key, sa.Boolean(), nullable=False, server_default=sa.false())
            )
    products, definitions, values, archive = _tables()
    connection = op.get_bind()
    for row in connection.execute(sa.select(archive).where(archive.c.kind == "PRODUCT")).mappings():
        payload = dict(row["payload"])
        payload.pop("expiry_required")  # retain current Product expiry requirement
        connection.execute(products.update().where(products.c.id == row["id"]).values(**payload))
    connection.execute(
        products.update().where(products.c.expiry_required.is_(True)).values(tracking_mode="BATCH")
    )
    for kind, table in (("DEFINITION", definitions), ("VALUE", values)):
        for row in connection.execute(sa.select(archive).where(archive.c.kind == kind)).mappings():
            payload = dict(row["payload"])
            for key in ("created_at", "updated_at"):
                if key in payload:
                    payload[key] = datetime.fromisoformat(payload[key])
            connection.execute(table.insert().values(id=row["id"], **payload))
    for row in connection.execute(
        sa.select(archive.c.id).where(archive.c.kind == "MIGRATED_NEGATIVE")
    ):
        connection.execute(values.delete().where(values.c.id == row[0]))
    with op.batch_alter_table("catalog_products") as batch:
        for name, condition in PRODUCT_CHECKS.items():
            batch.create_check_constraint(name, condition)
        for key in PRODUCT_COLUMNS:
            if key != "expiry_required":
                batch.alter_column(
                    key,
                    existing_type=sa.String(16)
                    if key in ("tracking_mode", "issue_strategy")
                    else sa.Boolean(),
                    server_default=None,
                )
    with op.batch_alter_table("warehouses") as batch:
        for name in WAREHOUSE_CHECKS:
            batch.drop_constraint(name, type_="check")
        batch.drop_column("issue_strategy")
        batch.drop_column("tracking_mode")
    op.drop_table("inventory_policy_legacy")
