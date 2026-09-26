from warehouse_erp.catalog.permissions import CatalogPermission
from warehouse_erp.identity.permissions import IdentityPermission
from warehouse_erp.permission_catalog import PERMISSIONS, SYSTEM_ROLES, validate_catalog
from warehouse_erp.settings.permissions import SettingsPermission
from warehouse_erp.warehouse.permissions import WarehousePermission


def test_permission_catalog_is_valid_and_unique() -> None:
    validate_catalog()

    codes = [str(definition.code) for definition in PERMISSIONS]
    assert len(codes) == len(set(codes))


def test_admin_role_receives_every_registered_permission() -> None:
    admin = next(role for role in SYSTEM_ROLES if role.code == "ADMIN")

    assert admin.permission_codes == frozenset(str(definition.code) for definition in PERMISSIONS)


def test_modules_own_their_permission_constants() -> None:
    assert CatalogPermission.EDIT == "catalog.edit"
    assert IdentityPermission.MANAGE_USERS == "users.manage"
    assert SettingsPermission.MANAGE == "settings.manage"
    assert WarehousePermission.MANAGE == "warehouse.manage"
