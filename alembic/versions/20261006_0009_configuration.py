"""Reference directories and editable enterprise/accounting/user settings.

Revision ID: 20261006_0009
Revises: 20261002_0008
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20261006_0009"
down_revision = "20261002_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "configuration_guard",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
    )
    op.create_table(
        "configuration_currencies",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("display_decimal_places", sa.Integer(), nullable=False),
        sa.Column("rounding_decimal_places", sa.Integer(), nullable=False),
        sa.Column("rounding_mode", sa.Text(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.UniqueConstraint("code", name="uq_configuration_currencies_code"),
    )
    op.create_index(
        "ix_configuration_currencies_name", "configuration_currencies", ["active", "name", "id"]
    )
    op.create_table(
        "configuration_vat_rates",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("treatment", sa.String(32), nullable=False),
        sa.Column("rate", sa.Numeric(7, 4), nullable=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.UniqueConstraint("code", name="uq_configuration_vat_rates_code"),
    )
    op.create_index(
        "ix_configuration_vat_rates_name", "configuration_vat_rates", ["active", "name", "id"]
    )
    op.create_table(
        "configuration_storage_analytics",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("value_type", sa.String(32), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.UniqueConstraint("code", name="uq_configuration_storage_analytics_code"),
    )
    op.create_index(
        "ix_configuration_storage_analytics_name",
        "configuration_storage_analytics",
        ["active", "name", "id"],
    )
    op.create_table(
        "configuration_storage_analytic_values",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "definition_id",
            sa.String(36),
            sa.ForeignKey("configuration_storage_analytics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "definition_id", "code", name="uq_configuration_storage_analytic_values_code"
        ),
    )
    op.create_index(
        "ix_analytic_values_definition",
        "configuration_storage_analytic_values",
        ["definition_id", "active"],
    )
    op.create_index(
        "ix_configuration_storage_analytic_values_name",
        "configuration_storage_analytic_values",
        ["active", "name", "id"],
    )
    op.create_table(
        "configuration_counterparties",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("tax_identifier", sa.String(255), nullable=True),
        sa.Column("registration_identifier", sa.String(255), nullable=True),
        sa.Column("legal_address", sa.Text(), nullable=True),
        sa.Column("postal_address", sa.Text(), nullable=True),
        sa.Column("contact_details", sa.Text(), nullable=True),
        sa.Column("payment_details", sa.Text(), nullable=True),
        sa.Column("is_supplier", sa.Boolean(), nullable=False),
        sa.Column("is_customer", sa.Boolean(), nullable=False),
        sa.Column("is_other_recipient", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.UniqueConstraint("code", name="uq_configuration_counterparties_code"),
    )
    op.create_index(
        "ix_configuration_counterparties_name",
        "configuration_counterparties",
        ["active", "name", "id"],
    )
    op.create_index(
        "ix_counterparty_registration_identifier",
        "configuration_counterparties",
        ["registration_identifier"],
    )
    op.create_index(
        "ix_counterparty_tax_identifier", "configuration_counterparties", ["tax_identifier"]
    )
    op.create_table(
        "configuration_price_types",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("price_entry_mode", sa.String(32), nullable=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.UniqueConstraint("code", name="uq_configuration_price_types_code"),
    )
    op.create_index(
        "ix_configuration_price_types_name", "configuration_price_types", ["active", "name", "id"]
    )
    op.create_table(
        "configuration_adjustment_reasons",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.UniqueConstraint("code", name="uq_configuration_adjustment_reasons_code"),
    )
    op.create_index(
        "ix_configuration_adjustment_reasons_name",
        "configuration_adjustment_reasons",
        ["active", "name", "id"],
    )
    op.create_table(
        "configuration_enterprise",
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("tax_identifier", sa.String(255), nullable=True),
        sa.Column("tax_identifier_label", sa.Text(), nullable=False),
        sa.Column("registration_identifier", sa.String(255), nullable=True),
        sa.Column("registration_identifier_label", sa.Text(), nullable=False),
        sa.Column("legal_address", sa.Text(), nullable=True),
        sa.Column("postal_address", sa.Text(), nullable=True),
        sa.Column("contact_details", sa.Text(), nullable=True),
        sa.Column("payment_details", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_table(
        "configuration_accounting",
        sa.Column(
            "currency_id",
            sa.String(36),
            sa.ForeignKey("configuration_currencies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("cost_accounting_enabled", sa.Boolean(), nullable=False),
        sa.Column("cost_valuation_method", sa.String(32), nullable=False),
        sa.Column("changes_locked_through", sa.Date(), nullable=True),
        sa.Column("accounting_timezone", sa.String(255), nullable=False),
        sa.Column("vat_enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "default_vat_rate_id",
            sa.String(36),
            sa.ForeignKey("configuration_vat_rates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("price_entry_mode", sa.String(32), nullable=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_table(
        "configuration_numbering",
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("numeric_width", sa.Integer(), nullable=False),
        sa.Column("reset_annually", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.UniqueConstraint("document_type", name="uq_numbering_document_type"),
    )
    op.create_table(
        "configuration_audit",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("record_id", sa.String(36), nullable=False),
        sa.Column(
            "actor_id",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_configuration_audit_record", "configuration_audit", ["kind", "record_id", "changed_at"]
    )
    op.create_table(
        "configuration_external_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("record_id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("external_id", sa.String(255, collation="utf8mb4_bin"), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "source", "external_id", name="uq_external_mapping_source"),
    )
    op.create_index(
        "ix_external_mapping_record", "configuration_external_mappings", ["kind", "record_id"]
    )
    op.add_column(
        "warehouses",
        sa.Column(
            "address_storage_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "catalog_units",
        sa.Column("display_decimal_places", sa.Integer(), nullable=False, server_default="3"),
    )
    op.execute(sa.text("UPDATE catalog_units SET display_decimal_places = `precision`"))
    op.create_check_constraint(
        "ck_unit_display_decimal_places", "catalog_units", "display_decimal_places BETWEEN 0 AND 9"
    )
    op.add_column("identity_users", sa.Column("default_warehouse_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_user_default_warehouse",
        "identity_users",
        "warehouses",
        ["default_warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "catalog_products", sa.Column("default_vat_rate_id", sa.String(36), nullable=True)
    )
    op.create_foreign_key(
        "fk_product_default_vat",
        "catalog_products",
        "configuration_vat_rates",
        ["default_vat_rate_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    connection = op.get_bind()
    metadata = sa.MetaData()
    guard = sa.Table("configuration_guard", metadata, autoload_with=connection)
    connection.execute(guard.insert().values(id=1))
    from uuid import NAMESPACE_URL, uuid5

    permissions = sa.Table("identity_permissions", metadata, autoload_with=connection)
    role_permissions = sa.Table("identity_role_permissions", metadata, autoload_with=connection)
    roles = sa.Table("identity_roles", metadata, autoload_with=connection)
    admin = connection.execute(
        sa.select(roles.c.id).where(roles.c.code == "ADMIN")
    ).scalar_one_or_none()
    for code, description in (
        ("reference_data.import", "Import reference directory records"),
        ("reference_data.export", "Export reference directory records"),
    ):
        permission_id = str(uuid5(NAMESPACE_URL, f"warehouse-erp/permission/{code}"))
        connection.execute(
            permissions.insert().values(id=permission_id, code=code, description=description)
        )
        if admin is not None:
            connection.execute(
                role_permissions.insert().values(role_id=admin, permission_id=permission_id)
            )
    read_settings_id = connection.execute(
        sa.select(permissions.c.id).where(permissions.c.code == "settings.read")
    ).scalar_one()
    reader_roles = (
        connection.execute(
            sa.select(roles.c.id).where(
                roles.c.code.in_(("WAREHOUSE_OPERATOR", "WAREHOUSE_MANAGER"))
            )
        )
        .scalars()
        .all()
    )
    for reader_role in reader_roles:
        exists = connection.execute(
            sa.select(role_permissions.c.role_id).where(
                role_permissions.c.role_id == reader_role,
                role_permissions.c.permission_id == read_settings_id,
            )
        ).first()
        if exists is None:
            connection.execute(
                role_permissions.insert().values(
                    role_id=reader_role, permission_id=read_settings_id
                )
            )
    timestamp = datetime.now(UTC)
    table = sa.Table("configuration_enterprise", metadata, autoload_with=connection)
    connection.execute(
        table.insert().values(
            **{
                "id": "10474f80-73c7-5358-8c98-ac4a5cc4deea",
                "version": 1,
                "created_by": None,
                "updated_by": None,
                "legal_name": "",
                "display_name": "",
                "tax_identifier": None,
                "tax_identifier_label": "Tax identifier",
                "registration_identifier": None,
                "registration_identifier_label": "Registration identifier",
                "legal_address": None,
                "postal_address": None,
                "contact_details": None,
                "payment_details": None,
                "logo_url": None,
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    table = sa.Table("configuration_accounting", metadata, autoload_with=connection)
    connection.execute(
        table.insert().values(
            **{
                "id": "dd7b5c22-cf3c-558b-b47e-074f5c5fb4dd",
                "version": 1,
                "created_by": None,
                "updated_by": None,
                "currency_id": None,
                "cost_accounting_enabled": False,
                "cost_valuation_method": "MOVING_WEIGHTED_AVERAGE",
                "changes_locked_through": None,
                "accounting_timezone": "UTC",
                "vat_enabled": False,
                "default_vat_rate_id": None,
                "price_entry_mode": "TAX_EXCLUSIVE",
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    table = sa.Table("configuration_numbering", metadata, autoload_with=connection)
    connection.execute(
        table.insert().values(
            **{
                "id": "5d65cb4b-8546-5053-9f2b-cb1ffd1f6e84",
                "version": 1,
                "created_by": None,
                "updated_by": None,
                "document_type": "INITIAL_RECEIPT",
                "prefix": "",
                "numeric_width": 6,
                "reset_annually": True,
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    connection.execute(
        table.insert().values(
            **{
                "id": "3576c339-2935-504c-be73-5fcdb5623dd9",
                "version": 1,
                "created_by": None,
                "updated_by": None,
                "document_type": "GOODS_RECEIPT",
                "prefix": "",
                "numeric_width": 6,
                "reset_annually": True,
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    connection.execute(
        table.insert().values(
            **{
                "id": "fb2c40e2-a142-56c4-8867-773c2bc1e800",
                "version": 1,
                "created_by": None,
                "updated_by": None,
                "document_type": "GOODS_ISSUE",
                "prefix": "",
                "numeric_width": 6,
                "reset_annually": True,
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    connection.execute(
        table.insert().values(
            **{
                "id": "05b26e4c-ac70-508d-9218-e0a31489f80e",
                "version": 1,
                "created_by": None,
                "updated_by": None,
                "document_type": "STOCK_TRANSFER",
                "prefix": "",
                "numeric_width": 6,
                "reset_annually": True,
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    connection.execute(
        table.insert().values(
            **{
                "id": "0e32595e-46e1-5219-bbc6-11c700383aaf",
                "version": 1,
                "created_by": None,
                "updated_by": None,
                "document_type": "STOCK_ADJUSTMENT",
                "prefix": "",
                "numeric_width": 6,
                "reset_annually": True,
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    connection.execute(
        table.insert().values(
            **{
                "id": "7c84a6f4-59fa-5f26-bf3f-f7b6da35d76a",
                "version": 1,
                "created_by": None,
                "updated_by": None,
                "document_type": "INVENTORY_COUNT",
                "prefix": "",
                "numeric_width": 6,
                "reset_annually": True,
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    connection.execute(
        table.insert().values(
            **{
                "id": "0be4117d-d413-5c66-9202-9238541f1c62",
                "version": 1,
                "created_by": None,
                "updated_by": None,
                "document_type": "INBOUND_ORDER",
                "prefix": "",
                "numeric_width": 6,
                "reset_annually": True,
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    connection.execute(
        table.insert().values(
            **{
                "id": "30b7a043-7397-55dc-b996-ae534ff13be3",
                "version": 1,
                "created_by": None,
                "updated_by": None,
                "document_type": "OUTBOUND_ORDER",
                "prefix": "",
                "numeric_width": 6,
                "reset_annually": True,
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    connection.execute(
        table.insert().values(
            **{
                "id": "a37f8e3b-355f-5b9f-a374-aa2602482b15",
                "version": 1,
                "created_by": None,
                "updated_by": None,
                "document_type": "PRICE_SETTING",
                "prefix": "",
                "numeric_width": 6,
                "reset_annually": True,
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
    )


def downgrade():
    connection = op.get_bind()
    metadata = sa.MetaData()
    permissions = sa.Table("identity_permissions", metadata, autoload_with=connection)
    links = sa.Table("identity_role_permissions", metadata, autoload_with=connection)
    codes = ("reference_data.import", "reference_data.export")
    ids = (
        connection.execute(sa.select(permissions.c.id).where(permissions.c.code.in_(codes)))
        .scalars()
        .all()
    )
    connection.execute(links.delete().where(links.c.permission_id.in_(ids)))
    connection.execute(permissions.delete().where(permissions.c.code.in_(codes)))
    op.drop_table("configuration_external_mappings")
    op.drop_constraint("fk_product_default_vat", "catalog_products", type_="foreignkey")
    op.drop_column("catalog_products", "default_vat_rate_id")
    op.drop_constraint("fk_user_default_warehouse", "identity_users", type_="foreignkey")
    op.drop_column("identity_users", "default_warehouse_id")
    op.drop_constraint("ck_unit_display_decimal_places", "catalog_units", type_="check")
    op.drop_column("catalog_units", "display_decimal_places")
    op.drop_column("warehouses", "address_storage_enabled")
    op.drop_table("configuration_audit")
    op.drop_table("configuration_numbering")
    op.drop_table("configuration_accounting")
    op.drop_table("configuration_enterprise")
    op.drop_table("configuration_adjustment_reasons")
    op.drop_table("configuration_price_types")
    op.drop_table("configuration_counterparties")
    op.drop_table("configuration_storage_analytic_values")
    op.drop_table("configuration_storage_analytics")
    op.drop_table("configuration_vat_rates")
    op.drop_table("configuration_currencies")
    op.drop_table("configuration_guard")
