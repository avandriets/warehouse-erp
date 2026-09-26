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
