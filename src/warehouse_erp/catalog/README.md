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

Product policy contains only `batch_expiry_required`. Expiry dates themselves belong to
receipt-line batches. Tracking (`NONE`/`BATCH`) and issue allocation (`MANUAL`/`FIFO`/`FEFO`)
are explicit Warehouse settings; Product/Category overrides cannot change them. A Product
requiring expiry may hold stock only in BATCH warehouses.

Product policy JSON is `{"batch_expiry_required": true}`. Removed fields are rejected with
422, including the old `expiry_required` name, tracking/allocation, negative-stock flags,
MRP, and quality flags. Negative stock is resolved through scoped settings instead.

Product codes and barcodes remain unique; new Products require an active category and unit.

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

Units now expose independent `display_decimal_places` (0–9), editable without changing
`precision`, conversion results or stored quantities. Migration preserves the previous precision
as the initial display precision. Products also support nullable `default_vat_rate_id`;
selected rates must exist and be active in the configuration VAT directory.
