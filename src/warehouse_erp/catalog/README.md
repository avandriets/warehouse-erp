# Product catalog

The catalog module owns the stable master data used by purchasing, warehousing, manufacturing,
sales, and accounting. It describes what can be stocked; it does not own quantities, inventory
movements, prices, bills of materials, or accounting entries.

## Data model

```text
Category (tree) ── Product ── storage Unit
                          ├── ProductInventoryPolicy
                          ├── PackageSet ── Package → Package → storage Unit
                          ├── ProductMeasurement → measured Unit
                          └── ProductBarcode → optional Package
```

- `Category` organizes the catalog and may reference another category through `parent_id`.
- `Product` is the single catalog and inventory-accounting item. There is no separate SKU entity.
- `Unit` defines a unit of measure, dimension, symbol, decimal precision (0–6), optional
  external classifier code, and optional conversion to a root unit of the same dimension.
- `ProductInventoryPolicy` defines how the inventory module must handle the product.

Every stock balance, batch, warehouse document line, future bill of materials line, and accounting
reference must point directly to `Product.id`. Stock balances and movements always use
`Product.storage_unit_id`.

## Units, packages, measurements

The unit directory supports `COUNT`, `MASS`, `VOLUME`, `LENGTH`, `AREA`, and `OTHER` dimensions.
Physical units can reference a root unit through `base_unit_id` and `factor_to_base`:
`1 g = 0.001 kg`. A box has **no** global conversion to pieces: its content depends on the
product/package set. A unit's dimension and conversion base are immutable once defined; old
pre-migration units start with dimension `OTHER` and may be classified once via `PATCH /units/{id}`.
Unit conversions require a common root and reject precision loss. Unit conversion is not the same
as a product-specific weight: `1 piece = 2.5 kg` belongs to `ProductMeasurement`.

`PackageSet` may be `SHARED` (reused by products with the same storage unit) or `INDIVIDUAL`
(assigned to one product). A package has a `COUNT` unit, positive `contains_quantity`, and
**either** `contains_unit_id` (the bottom of the chain) **or** `contains_package_id` (another
package in the same set). Cycles and incompatible product storage units are rejected. Optional
package weight, volume, and dimensions use dimension-checked units. Example:

```text
Product.storage_unit_id = PCS
PACK: 20 PCS
BOX: 10 PACK = 200 PCS
2 BOX → 400 PCS
```

`ProductMeasurement` stores a product-specific ratio such as `1 PCS = 2.5 KG` using
`storage_quantity=1, measured_quantity=2.5`. `REFERENCE_ONLY` is displayed in reports but
cannot be used to enter a document quantity; `DOCUMENT` enables conversion. At most one active
measurement is marked as the report unit. Conversion rejects values exceeding the product storage
unit's precision rather than rounding silently. Conversion inputs support at most 15 integral
and 9 fractional digits, matching `NUMERIC(24, 9)`; outputs must fit the same integral range
and the target unit precision. Arithmetic uses exact ratios before checking representability.
Out-of-range or unrepresentable quantities return `422`.

`ProductBarcode` allows multiple globally unique barcodes per product, each assigned to the
storage unit (`package_id=null`) or a package in the product's set. Entries are deactivated, not
deleted. This replaces the former single barcode field on `Product`; migration `0004` preserves
existing product barcodes. `storage_unit_id` cannot be changed after product creation.
Changing or clearing a product's package set requires first deactivating its package barcodes;
otherwise the API returns `409`. Reactivation checks the current product/package relationship.
Product changes and barcode writes serialize on the product row. Individual package ownership
uses a set lock followed by a current locking read, including under MariaDB REPEATABLE READ.

To add starter units (`PCS`, `KG`, `G`, `T`, `L`, `ML`, `M`, `CM`, `MM`, `M2`, `PACK`, `BOX`,
`PALLET`) idempotently, run after migration:

```bash
.venv/bin/python -m warehouse_erp.catalog.seed_units
```

Classifier codes are deliberately not guessed by the seed; specify the applicable national
classifier code explicitly when creating a unit. This seed does not modify existing entries.

Future stock documents must save the input quantity, selected package/measurement, and the
resolved conversion-factor snapshot alongside the computed storage quantity. Posting and the
ledger are not implemented here; the conversion endpoint is a read-only calculation.

## Category tree

Root categories have `parent_id=null`. Direct children can be loaded with:

```http
GET /api/catalog/categories?parent_id={category_id}
```

Roots can be loaded with:

```http
GET /api/catalog/categories?root_only=true
```

The database index `(parent_id, name)` makes direct-child navigation efficient. The application
rejects self-parenting and indirect cycles. Category updates lock and read the entire category
tree in identifier order before validation, so concurrent moves cannot validate against an old
snapshot. This deliberately serializes category edits in the current base implementation. Moving a category changes only its `parent_id`; product
records do not need to be rewritten.

The category hierarchy is classification, not a manufacturing bill of materials. Manufacturing
components will use a separate many-to-many BOM model because one component may be shared by many
products.

## Product

A product contains everything required to identify and account for a stock item:

- stable unique `code`;
- name, category, storage unit, optional package set, brand, and description;
- separately maintained barcodes for unit and packages;
- extensible JSON attributes;
- inventory policy;
- active/inactive lifecycle state.

Products are intentionally flat. Different sizes, packaging, or variants that are tracked
independently are separate products with separate codes.

## Inventory policy

`tracking_mode` determines whether inventory is tracked by batch:

- `NONE` — no batch tracking;
- `BATCH` — inventory operations identify a batch.

`issue_strategy` determines stock selection for outbound operations:

- `MANUAL` — the operator selects stock explicitly;
- `FIFO` — oldest received stock is issued first;
- `FEFO` — stock with the nearest expiry date is issued first.

Domain invariants:

- `expiry_required=true` requires `tracking_mode=BATCH`;
- `issue_strategy=FEFO` requires `tracking_mode=BATCH`;
- product codes and barcode values are globally unique in their respective tables;
- a new product requires an active category and unit.

The policy reserves `mrp_tracking_enabled` and `quality_tracking_enabled` for future manufacturing
and quality-control modules. Those flags do not implement their workflows inside the catalog.

## Lifecycle

Catalog records are not deleted through the API. They are deactivated with `active=false`, which
preserves references from operational and accounting documents. List endpoints accept the optional
`active` filter.

Codes are normalized to uppercase and cannot be changed through the current API. Renaming a stable
code requires an explicit migration and audit policy.

## Authorization

The module declares its permission contract in `permissions.py`:

- `catalog.read` — list and view records;
- `catalog.create` — create records;
- `catalog.edit` — update or deactivate records.

Routes use `CatalogPermission` constants. Identity stores and assigns permissions, while catalog
owns their meaning and enforcement.

## HTTP API

The router is mounted at `/api/catalog`:

- `POST /categories`, `GET /categories`, `GET/PATCH /categories/{id}`;
- `POST /units`, `GET /units`, `GET/PATCH /units/{id}`, `POST /units/convert`;
- `POST/GET /package-sets`, `GET/PATCH /package-sets/{id}`;
- `POST/GET /package-sets/{id}/packages`, `GET/PATCH /packages/{id}`;
- `POST /products`, `GET /products`, `GET/PATCH /products/{id}`.
- `POST/GET /products/{id}/measurements`, `PATCH /products/{id}/measurements/{measurementId}`;
- `POST/GET /products/{id}/barcodes`, `PATCH /products/{id}/barcodes/{barcodeId}`;
- `POST /products/{id}/convert` — calculate quantity in storage units (does not post stock).

List endpoints support `limit`, `offset`, and `active`. Product lists support `category_id`.
Category lists additionally support `parent_id` and `root_only`.

Typical creation order:

1. create a root or child category;
2. seed or create physical units and packaging units;
3. optionally create a package set and its packages from inner to outer;
4. create a product linked to the category, storage unit, and optional package set;
5. assign optional product measurements and barcodes.

## Package structure

- `api/` — FastAPI routes and request/response schemas;
- `application/` — catalog use cases, commands, and transaction boundaries;
- `domain/` — framework-independent entities, invariants, and repository ports;
- `infrastructure/` — SQLAlchemy models and repository implementations;
- `permissions.py` — stable permissions implemented by this module.

The dependency direction is:

```text
API -> Application -> Domain
          ^             ^
          |             |
      Infrastructure implements ports
```

Do not add stock balances, inventory movements, or BOM lines to this module. Those belong to their
respective modules and reference catalog product identifiers.
