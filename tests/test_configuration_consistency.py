from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from conftest import ADMIN_USER_ID

from warehouse_erp.catalog.application.commands import (
    CreateCategory,
    CreateProduct,
    CreateUnit,
    UpdateProduct,
)
from warehouse_erp.catalog.application.service import CatalogService
from warehouse_erp.catalog.domain.entities import UnitDimension
from warehouse_erp.catalog.infrastructure.repositories import SqlAlchemyCatalogUnitOfWork
from warehouse_erp.configuration.application.service import ConfigurationService
from warehouse_erp.configuration.domain.entities import TaxTreatment
from warehouse_erp.configuration.infrastructure.repositories import (
    SqlAlchemyConfigurationUnitOfWork,
)
from warehouse_erp.identity.application.service import IdentityService
from warehouse_erp.identity.domain.entities import AuthenticatedIdentity
from warehouse_erp.identity.infrastructure.repositories import SqlAlchemyIdentityUnitOfWork
from warehouse_erp.settings.application.service import SettingsService
from warehouse_erp.settings.domain.entities import SettingsContext, SettingScope
from warehouse_erp.settings.infrastructure.repositories import SqlAlchemySettingsUnitOfWork
from warehouse_erp.shared.errors import ConflictError, ValidationError


def test_settings_mutations_read_current_versions_after_old_snapshot(session_factory):
    barrier = Barrier(2)

    def edit(name):
        with session_factory() as session:
            service = ConfigurationService(SqlAlchemyConfigurationUnitOfWork(session))
            original = service.section("enterprise")
            barrier.wait(timeout=30)
            try:
                service.update(
                    "enterprise", original.id, {"legal_name": name}, original.version, ADMIN_USER_ID
                )
                return "saved"
            except ConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(edit, ["One", "Two"]))
    assert sorted(outcomes) == ["conflict", "saved"]
    with session_factory() as session:
        saved = ConfigurationService(SqlAlchemyConfigurationUnitOfWork(session)).section(
            "enterprise"
        )
        assert saved.version == 2
        assert saved.legal_name in {"One", "Two"}


def test_cost_and_negative_stock_changes_cannot_race(session_factory):
    barrier = Barrier(2)

    def edit(action):
        with session_factory() as session:
            configuration = ConfigurationService(SqlAlchemyConfigurationUnitOfWork(session))
            # Establish an older REPEATABLE READ snapshot before competing for the guard.
            accounting = configuration.section("accounting")
            barrier.wait(timeout=30)
            try:
                if action == "cost":
                    configuration.update(
                        "accounting",
                        accounting.id,
                        {"cost_accounting_enabled": True},
                        1,
                        ADMIN_USER_ID,
                    )
                else:
                    SettingsService(SqlAlchemySettingsUnitOfWork(session)).set_value(
                        key="inventory.negative_stock_allowed",
                        scope_type=SettingScope.GLOBAL,
                        scope_id=None,
                        value=True,
                        actor_id=ADMIN_USER_ID,
                    )
                return "saved"
            except (ConflictError, ValidationError):
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(edit, ["cost", "negative"]))
    assert sorted(outcomes) == ["rejected", "saved"]
    with session_factory() as session:
        configuration = ConfigurationService(SqlAlchemyConfigurationUnitOfWork(session))
        cost = configuration.section("accounting").cost_accounting_enabled
        negative = (
            SettingsService(SqlAlchemySettingsUnitOfWork(session))
            .resolve("inventory.negative_stock_allowed", SettingsContext())
            .value
        )
        assert not (cost and negative)


def test_product_vat_default_round_trip_and_archive_protection(session_factory):
    with session_factory() as session:
        configuration = ConfigurationService(SqlAlchemyConfigurationUnitOfWork(session))
        vat = configuration.create(
            "vat-rates",
            dict(code="NO_VAT", name="No VAT", treatment=TaxTreatment.NO_VAT),
            ADMIN_USER_ID,
        )
        catalog = CatalogService(SqlAlchemyCatalogUnitOfWork(session))
        category = catalog.create_category(CreateCategory(code="C", name="Category"))
        unit = catalog.create_unit(
            CreateUnit(code="PCS", name="Pieces", symbol="pcs", dimension=UnitDimension.COUNT)
        )
        product = catalog.create_product(
            CreateProduct(
                code="P",
                name="Product",
                category_id=category.id,
                storage_unit_id=unit.id,
                default_vat_rate_id=vat.id,
            )
        )
        assert catalog.get_product(product.id).default_vat_rate_id == vat.id
        try:
            configuration.update("vat-rates", vat.id, {"active": False}, 1, ADMIN_USER_ID)
        except ConflictError:
            session.rollback()
        else:
            raise AssertionError("Selected VAT treatment must not be archived")
        catalog.update_product(
            product.id, UpdateProduct(default_vat_rate_id=None, default_vat_rate_id_set=True)
        )
        assert catalog.get_product(product.id).default_vat_rate_id is None
        configuration.update("vat-rates", vat.id, {"active": False}, 1, ADMIN_USER_ID)


def test_default_warehouse_falls_back_when_access_is_revoked(client, session_factory):
    warehouse = client.post("/api/warehouses", json={"code": "WH", "name": "Warehouse"}).json()
    response = client.patch("/api/identity/me", json={"default_warehouse_id": warehouse["id"]})
    assert response.status_code == 200, response.text
    with session_factory() as session:
        service = IdentityService(SqlAlchemyIdentityUnitOfWork(session))
        current = service.resolve_current_user(AuthenticatedIdentity(subject="auth0|test-user"))
        # No persisted role grants exist for the fixture user; the API actor was overridden.
        assert current.default_warehouse_id is None
        saved = service.uow.identity.get_user(ADMIN_USER_ID)
        assert str(saved.default_warehouse_id) == warehouse["id"]
