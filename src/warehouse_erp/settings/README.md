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

Writes require `settings.manage`, reads require `settings.read`. Warehouse-scoped overrides
also require `warehouse.manage` for that warehouse; Product/Category overrides require
`catalog.edit`. New overrides omit
`expected_version`; updates must pass the version returned by the previous read. A stale version
returns `409`. Every override stores `updated_by` and `updated_at`.

The built-in definition is `inventory.negative_stock_allowed` (boolean), with the scope
precedence above. The old `inventory.default_issue_strategy` is retired; generic definitions
cannot recreate it or the explicit tracking/allocation/expiry policy keys.

`SettingsService.resolve_inventory_defaults(context)` returns a typed immutable snapshot:
warehouse `tracking_mode`, effective `issue_strategy` (null without a BATCH warehouse),
Product `batch_expiry_required` (null without a Product), negative-stock allowance, and
resolution time. A supplied Product requiring expiry is rejected with a NONE warehouse.
Explicit Warehouse/Product fields are read before any cached snapshot is reused, so changes
are visible immediately. Scoped negative-stock values are cached for up to 15 seconds, with
invalidation after changes made by this process. Other workers may retain these values until
TTL expiry. Future posting must obtain a transactionally consistent policy snapshot and enforce
all posting/stock locks; this read endpoint does not implement posting or check batch expiry data.

## API

The router is mounted at `/api/settings`:

- `POST/GET /categories`;
- `POST/GET /definitions`, `GET /definitions/{key}`;
- `PUT/GET /definitions/{key}/values`;
- `GET /resolve/{key}?product_id=...&warehouse_id=...`;
- `GET /inventory-defaults?product_id=...&warehouse_id=...`.

Example override for `inventory.negative_stock_allowed`:

```json
{
  "scope_type": "WAREHOUSE",
  "scope_id": "<warehouse UUID>",
  "value": true
}
```

If that override already exists, add `"expected_version": 1` (or the current version). The
response includes the new version and audit identity.

Enterprise/accounting sections, numbering and the new reference directories have explicit APIs;
see [configuration](../configuration/README.md). They share the same database across clients.
