# Settings module

This module owns database-backed setting definitions, typed values, scope resolution, and
read-only typed snapshots consumed by future business workflows. It does not own catalog or
warehouse master data.

## Model and resolution

`SettingsCategory` groups `SettingDefinition` records. A definition has a stable unique key,
type (`BOOLEAN`, `INTEGER`, `DECIMAL`, `STRING`, `ENUM`), default, optional enum options, and an
explicit list of allowed scopes. Definitions are intentionally immutable through the API: changing
a key or type after values exist requires a controlled migration. Decimal values are stored as
strings to avoid binary floating-point errors.

`SettingValue` is a versioned override for one definition and one target. Resolution order is:

```text
PRODUCT → CATEGORY → WAREHOUSE → COMPANY → GLOBAL override → definition default
```

When a product is supplied, its category is derived from the catalog. An explicitly supplied
category must match it. Product, category, and warehouse targets must exist. `COMPANY` is reserved
for the future company module; its UUID is currently accepted without a foreign-key check.
Category inheritance is currently exact-category only (not ancestor-category traversal).

Writes require `settings.manage`, reads require `settings.read`. New overrides omit
`expected_version`; updates must pass the version returned by the previous read. A stale version
returns `409`. Every override stores `updated_by` and `updated_at`.

The first built-in definitions are `inventory.default_issue_strategy` (enum
`MANUAL`/`FIFO`/`FEFO`) and `inventory.negative_stock_allowed` (boolean). Internal consumers use
`SettingsService.resolve_inventory_defaults(context)`, which returns one typed immutable
`InventoryDefaults` snapshot. This snapshot is cached in-process for 15 seconds and invalidated
after changes made by the same process. Other workers can retain a value until TTL expiry.
Future document posting must resolve the snapshot once per transaction and retain that snapshot
for the entire posting operation. Product-specific `ProductInventoryPolicy` still has its own
explicit fields; these settings are not yet applied to product creation or stock posting.

## API

The router is mounted at `/api/settings`:

- `POST/GET /categories`;
- `POST/GET /definitions`, `GET /definitions/{key}`;
- `PUT/GET /definitions/{key}/values`;
- `GET /resolve/{key}?product_id=...&warehouse_id=...`;
- `GET /inventory-defaults?product_id=...&warehouse_id=...`.

Example override:

```json
{
  "scope_type": "WAREHOUSE",
  "scope_id": "<warehouse UUID>",
  "value": "FIFO"
}
```

If that override already exists, add `"expected_version": 1` (or the current version). The
response includes the new version and audit identity.
