from enum import StrEnum

from warehouse_erp.shared.authorization import PermissionDefinition


class CatalogPermission(StrEnum):
    READ = "catalog.read"
    CREATE = "catalog.create"
    EDIT = "catalog.edit"


PERMISSIONS = (
    PermissionDefinition(CatalogPermission.READ, "View catalog records"),
    PermissionDefinition(CatalogPermission.CREATE, "Create catalog records"),
    PermissionDefinition(CatalogPermission.EDIT, "Edit and deactivate catalog records"),
)
