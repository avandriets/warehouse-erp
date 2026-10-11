from enum import StrEnum

from warehouse_erp.shared.authorization import PermissionDefinition


class ConfigurationPermission(StrEnum):
    IMPORT = "reference_data.import"
    EXPORT = "reference_data.export"


PERMISSIONS = (
    PermissionDefinition(ConfigurationPermission.IMPORT, "Import reference directory records"),
    PermissionDefinition(ConfigurationPermission.EXPORT, "Export reference directory records"),
)
