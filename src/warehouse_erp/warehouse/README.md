# Warehouse module

This module owns warehouses and the hierarchy of physical locations. It does not store stock
quantities, batches, documents, or movements.

```text
Warehouse MAIN
└── Zone A
    └── Rack A-01
        └── Bin A-01-01
```

`Warehouse.code` is globally unique and stable. `Location.code` is unique within its warehouse
and stable. Locations use an adjacency-list `parent_id`; root locations have no parent. Kinds
(`ZONE`, `AISLE`, `RACK`, `SHELF`, `BIN`, `STAGING`, `OTHER`) describe the location but do not impose a
fixed depth. `allows_stock` marks places intended for stock; actual balance validation belongs to
future inventory posting use cases.

The service rejects cycles, parents from other warehouses, inactive parents, duplicate codes,
creating locations in inactive warehouses, deactivating a location with active children, and
deactivating a warehouse with active locations. Existing records are deactivated rather than
deleted. Moving or deactivating locations that contain stock must also be guarded by the future
inventory module once balances exist. `created_by`, `updated_by`, and timestamps preserve audit
identity for master-data changes.

## Authorization

`warehouse.read` permits viewing a warehouse and its locations. `warehouse.manage` permits
changes. Both can be granted globally or for a specific warehouse. Creating a new warehouse
requires a global `warehouse.manage` grant. The warehouse list filters records to the caller's
scoped `warehouse.read` grants. The system role templates grant `warehouse.read` to warehouse
operators and managers; managers also receive `warehouse.manage`.

## API

- `POST/GET /api/warehouses`;
- `GET/PATCH /api/warehouses/{id}`;
- `POST/GET /api/warehouses/{id}/locations`;
- `GET/PATCH /api/locations/{id}`.

Location lists support `parent_id`, `root_only`, `active`, `limit`, and `offset`. Fetching direct
children uses the indexed `(warehouse_id, parent_id, name)` path; the API does not load the full
tree for every request.


## Inventory policy

Warehouse create/read/update payloads include `tracking_mode` (`NONE` default or `BATCH`)
and `issue_strategy` (`MANUAL` default, `FIFO`, or `FEFO`). NONE uses aggregate stock;
MANUAL is its inactive strategy value. FIFO/FEFO require BATCH. Partial updates validate the
combined resulting policy; explicit nulls and unknown fields are rejected. Switching to NONE
from FIFO/FEFO requires sending `issue_strategy: "MANUAL"` in the same request.

Editing policy fields requires global `settings.manage` in addition to the existing warehouse
management grant. Operational warehouse management alone cannot edit accounting policy.
The admin application edits these fields; the warehouse application displays them read-only.

`WarehouseInventoryPolicy` provides domain checks for expiry-required Products and transfers
between matching tracking modes. Stock posting does not exist yet: enforcement on stock,
expiry-data eligibility, and the first-posting structural lock must be connected when that
workflow is implemented. Do not interpret the current CRUD API as implementing stock posting.

Migration `20261002_0008` starts existing warehouses as NONE/MANUAL because Product policies
cannot be mapped to warehouses without stock data. Before stock posting, configure each
warehouse explicitly. Old Product policies and the retired scoped issue defaults are preserved
in `inventory_policy_legacy` for audit and downgrade, never used for current policy resolution.
Product expiry requirements are retained as `batch_expiry_required`. Legacy negative-stock
opt-ins are copied to Product-scoped settings only where no override already exists; migration
uses the earliest identity user as the required audit actor, with the generated IDs archived.
Downgrade restores old policies and issue defaults and removes migration-created overrides;
it cannot translate subsequently configured Warehouse policies back into Product policies.

Warehouse create, read and update also expose `address_storage_enabled` (default false).
Explicit changes require `settings.manage` alongside warehouse management permission.
The field is persisted independently of the location directory.
