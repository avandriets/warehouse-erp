from enum import StrEnum

from warehouse_erp.shared.authorization import PermissionDefinition


class InventoryPermission(StrEnum):
    READ = "inventory.read"
    CREATE_DOCUMENT = "inventory.document.create"
    EDIT_DOCUMENT = "inventory.document.edit"
    POST_DOCUMENT = "inventory.document.post"
    REVERSE_DOCUMENT = "inventory.document.reverse"
    ADJUST = "inventory.adjust"
    CLOSE_PERIOD = "inventory.period.close"


PERMISSIONS = (
    PermissionDefinition(
        InventoryPermission.READ,
        "View inventory documents, balances, and ledger",
    ),
    PermissionDefinition(
        InventoryPermission.CREATE_DOCUMENT,
        "Create stock-affecting documents",
    ),
    PermissionDefinition(
        InventoryPermission.EDIT_DOCUMENT,
        "Edit draft stock-affecting documents",
    ),
    PermissionDefinition(
        InventoryPermission.POST_DOCUMENT,
        "Post stock-affecting documents",
    ),
    PermissionDefinition(
        InventoryPermission.REVERSE_DOCUMENT,
        "Reverse posted stock-affecting documents",
    ),
    PermissionDefinition(InventoryPermission.ADJUST, "Create and post inventory adjustments"),
    PermissionDefinition(InventoryPermission.CLOSE_PERIOD, "Close inventory accounting periods"),
)
