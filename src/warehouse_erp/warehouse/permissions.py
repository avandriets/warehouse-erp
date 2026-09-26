from enum import StrEnum

from warehouse_erp.shared.authorization import PermissionDefinition


class WarehousePermission(StrEnum):
    READ = "warehouse.read"
    MANAGE = "warehouse.manage"


PERMISSIONS = (
    PermissionDefinition(WarehousePermission.READ, "View warehouses and locations"),
    PermissionDefinition(WarehousePermission.MANAGE, "Manage warehouses and locations"),
)
