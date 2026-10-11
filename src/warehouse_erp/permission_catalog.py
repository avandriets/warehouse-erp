from collections import Counter

from warehouse_erp.catalog.permissions import PERMISSIONS as CATALOG_PERMISSIONS
from warehouse_erp.catalog.permissions import CatalogPermission
from warehouse_erp.configuration.permissions import PERMISSIONS as CONFIGURATION_PERMISSIONS
from warehouse_erp.identity.permissions import PERMISSIONS as IDENTITY_PERMISSIONS
from warehouse_erp.inventory.permissions import PERMISSIONS as INVENTORY_PERMISSIONS
from warehouse_erp.inventory.permissions import InventoryPermission
from warehouse_erp.settings.permissions import PERMISSIONS as SETTINGS_PERMISSIONS
from warehouse_erp.settings.permissions import SettingsPermission
from warehouse_erp.shared.authorization import PermissionDefinition, RoleDefinition
from warehouse_erp.warehouse.permissions import PERMISSIONS as WAREHOUSE_PERMISSIONS
from warehouse_erp.warehouse.permissions import WarehousePermission

PERMISSIONS: tuple[PermissionDefinition, ...] = (
    *IDENTITY_PERMISSIONS,
    *CATALOG_PERMISSIONS,
    *INVENTORY_PERMISSIONS,
    *SETTINGS_PERMISSIONS,
    *WAREHOUSE_PERMISSIONS,
    *CONFIGURATION_PERMISSIONS,
)

SYSTEM_ROLES: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        code="WAREHOUSE_OPERATOR",
        name="Warehouse operator",
        description="Creates and edits warehouse documents without posting them.",
        permission_codes=frozenset(
            {
                CatalogPermission.READ,
                WarehousePermission.READ,
                SettingsPermission.READ,
                InventoryPermission.READ,
                InventoryPermission.CREATE_DOCUMENT,
                InventoryPermission.EDIT_DOCUMENT,
            }
        ),
    ),
    RoleDefinition(
        code="WAREHOUSE_MANAGER",
        name="Warehouse manager",
        description="Posts warehouse documents and manages stock control operations.",
        permission_codes=frozenset(
            {
                CatalogPermission.READ,
                WarehousePermission.READ,
                SettingsPermission.READ,
                InventoryPermission.READ,
                InventoryPermission.CREATE_DOCUMENT,
                InventoryPermission.EDIT_DOCUMENT,
                InventoryPermission.POST_DOCUMENT,
                InventoryPermission.REVERSE_DOCUMENT,
                InventoryPermission.ADJUST,
                WarehousePermission.MANAGE,
            }
        ),
    ),
    RoleDefinition(
        code="ADMIN",
        name="Administrator",
        description="Full access to all Warehouse ERP permissions.",
        permission_codes=frozenset(definition.code for definition in PERMISSIONS),
    ),
)


def validate_catalog() -> None:
    counts = Counter(str(definition.code) for definition in PERMISSIONS)
    duplicates = sorted(code for code, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate permission codes: {', '.join(duplicates)}")

    known_codes = set(counts)
    for role in SYSTEM_ROLES:
        unknown_codes = set(role.permission_codes) - known_codes
        if unknown_codes:
            raise ValueError(
                f"Role {role.code} references unknown permissions: "
                f"{', '.join(sorted(unknown_codes))}"
            )


validate_catalog()
