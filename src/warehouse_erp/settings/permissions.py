from enum import StrEnum

from warehouse_erp.shared.authorization import PermissionDefinition


class SettingsPermission(StrEnum):
    READ = "settings.read"
    MANAGE = "settings.manage"


PERMISSIONS = (
    PermissionDefinition(SettingsPermission.READ, "View settings and resolved values"),
    PermissionDefinition(SettingsPermission.MANAGE, "Manage settings and scoped values"),
)
