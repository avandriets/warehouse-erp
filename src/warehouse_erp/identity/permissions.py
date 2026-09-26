from enum import StrEnum

from warehouse_erp.shared.authorization import PermissionDefinition


class IdentityPermission(StrEnum):
    MANAGE_USERS = "users.manage"


PERMISSIONS = (
    PermissionDefinition(
        IdentityPermission.MANAGE_USERS,
        "Manage users, roles, and role assignments",
    ),
)
