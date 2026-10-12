# Configuration API for admin and warehouse clients

This module completes persisted configuration and the previously missing V1 reference directories.
It does not implement document posting, document number allocation, VAT amount calculation,
valuation, or posting-triggered structural locks. Those workflows consume these settings later.
No settings are inferred from a client application name. Warehouse clients display general
settings read-only; both clients use the same own-profile endpoints.

## General settings

All reads require `settings.read`; all writes require `settings.manage`.

| Section | Read | Save |
| --- | --- | --- |
| Enterprise | `GET /api/settings/enterprise` | `PATCH /api/settings/enterprise` |
| Accounting | `GET /api/settings/accounting` | `PATCH /api/settings/accounting` |
| Document numbering | `GET /api/settings/document-numbering` | `PATCH /api/settings/document-numbering/{document_type}` |
| Warehouse policies | `GET /api/settings/warehouses`, `GET /api/settings/warehouses/{id}` | `PATCH /api/settings/warehouses/{id}` |
| Fixed choices | `GET /api/settings/options` | Fixed system values |
| Enterprise/accounting history | `GET /api/settings/history/{section}` | Audit entries are immutable |

Enterprise, accounting and numbering PATCH bodies contain **only changed fields** plus
`expected_version`, obtained from GET. Warehouse-policy PATCH uses the existing warehouse
contract without a version field and accepts only tracking/allocation/address-storage fields;
master-data name/activation edits belong to `/api/warehouses`. Warehouse settings also enforce
warehouse read/manage permissions (including scoped grants).
A stale version returns `409`. Omitted fields stay unchanged. Explicit null clears nullable
fields; nonnullable fields reject null. Unknown fields are rejected. Default section records
and one numbering rule per document type are initialized by the migration.

```json
{
  "expected_version": 1,
  "legal_name": "Example SL",
  "display_name": "Example",
  "tax_identifier": "EX123",
  "tax_identifier_label": "NIF",
  "registration_identifier": "REG123",
  "registration_identifier_label": "Registration number",
  "legal_address": "Legal address",
  "postal_address": "Postal address",
  "contact_details": "Email and telephone",
  "payment_details": "Payment/bank details",
  "logo_url": "https://example.com/logo.png"
}
```

The logo is an HTTPS asset URL; this API does not fetch it or provide a file upload service.
Enterprise names/labels/addresses/contact/payment data are editable independently of accounting.

Accounting fields:

| Field | Default / allowed values |
| --- | --- |
| `currency_id` | null; UUID from currencies |
| `cost_accounting_enabled` | false |
| `cost_valuation_method` | `MOVING_WEIGHTED_AVERAGE` (default), `FIFO` |
| `changes_locked_through` | null; ISO date |
| `accounting_timezone` | `UTC`; valid IANA timezone |
| `vat_enabled` | false |
| `default_vat_rate_id` | null; UUID from VAT rates |
| `price_entry_mode` | `TAX_EXCLUSIVE` (default), `TAX_INCLUSIVE` |

Currency and default VAT references must point to active existing records. A selected reference
cannot be archived until its defaults are cleared/replaced. A product may also hold a nullable
`default_vat_rate_id` through the existing product API. Invalid/inactive product VAT defaults are
rejected. Rates and no-VAT treatments are not hard-coded to a country or seeded by guesswork.

Negative-stock allowance remains in the existing typed scoped settings API:
`PUT /api/settings/definitions/inventory.negative_stock_allowed/values`.
It defaults to false and permits GLOBAL/COMPANY/WAREHOUSE/CATEGORY/PRODUCT overrides.
Warehouse overrides also require management access to that warehouse; Product/Category overrides
require `catalog.edit`, in addition to `settings.manage`.
Cost accounting cannot be enabled while any negative-stock override is true. Clear those
explicit overrides first. While cost accounting is enabled, negative-stock setting writes are
rejected and `/api/settings/inventory-defaults` resolves negative allowance to false.
Both mutation paths coordinate through the same database guard row.

Numbering has `prefix` (up to 32 characters), `numeric_width` (1–18, default 6), and
`reset_annually` (default true). Document types are fixed system choices: INITIAL_RECEIPT,
GOODS_RECEIPT, GOODS_ISSUE, STOCK_TRANSFER, STOCK_ADJUSTMENT, INVENTORY_COUNT, INBOUND_ORDER,
OUTBOUND_ORDER, PRICE_SETTING. Saving rules does not allocate actual document numbers.

## Reference directories

Each directory supports these paths under `/api/reference-data/{directory}`:

- `POST /`: create; code and name are required;
- `GET /`: list with `q`, `active`, `limit` (1–100), `offset`;
- `GET /{id}`: read one record;
- `PATCH /{id}`: edit/archive with `expected_version`;
- `GET /{id}/history`: audit before/after, actor, timestamp;
- `POST /duplicate-check`: candidate create payload; returns similar existing records;
- `GET /export`: paginated JSON records with internal UUIDs and external identifiers;
- `POST /import`: preview or atomic application, described below;
- `GET /{id}/external-identifiers`, `PUT /{id}/external-identifiers`: external mappings.

Stable codes and internal identifiers cannot be changed. Archiving sets `active=false`;
there is no destructive delete endpoint. Audit records retain before/after snapshots.

| Directory | Specific fields |
| --- | --- |
| `currencies` | Three-letter `code`, `symbol`, `display_decimal_places`, `rounding_decimal_places` (0–9), `rounding_mode`: HALF_UP/HALF_EVEN/DOWN |
| `vat-rates` | `treatment`: TAXABLE/ZERO_RATE/NO_VAT; Decimal `rate` in percent, 0–100 with at most 4 decimal places |
| `storage-analytics` | `value_type`: BOOLEAN/INTEGER/DECIMAL/STRING/ENUM; `required`, `enabled`, `options` for ENUM |
| `storage-analytic-values` | `definition_id`, typed `value`; list optionally filters by `definition_id` |
| `counterparties` | Tax/registration identifiers, legal/postal addresses, contact/payment details, `is_supplier`, `is_customer`, `is_other_recipient`; at least one role |
| `price-types` | `price_entry_mode`: TAX_INCLUSIVE/TAX_EXCLUSIVE; no price amounts |
| `adjustment-reasons` | `operation`: WRITE_OFF/ADJUSTMENT/SPOILAGE/DISPOSAL |

Currencies, VAT and analytics use `settings.read`/`settings.manage`. Counterparties, price types
and reasons reuse `catalog.read`/`catalog.create`/`catalog.edit`. Import additionally requires
`reference_data.import`; export additionally requires `reference_data.export`. These new
permissions are added to ADMIN by the migration. Standard warehouse roles receive
`settings.read`, without gaining settings mutation rights. Do not grant an operator edit rights merely to
populate a selector.

ZERO_RATE and NO_VAT are distinct treatments with rate 0; TAXABLE requires a positive rate.
Analytic values are validated against their parent definition; DECIMAL values are stored as
exact strings. Analytic value codes are unique within their definition. Changing a definition's
type or removing enum choices after values exist is rejected; adding enum choices is allowed; names and enabled/required flags remain editable
at this pre-posting stage. Similar names and matching counterparty identifiers produce warnings
through duplicate-check/import preview; they do not force a merge or reject legitimate duplicates.

## Import and export

Import accepts at most 500 rows per request. `field_mapping` maps source column names to API
field names. Without a mapping, API field names are used directly. `dry_run` defaults to true.

```json
{
  "dry_run": true,
  "field_mapping": {"Currency code": "code", "Currency name": "name", "Sign": "symbol"},
  "rows": [{"Currency code": "EUR", "Currency name": "Euro", "Sign": "€"}]
}
```

The response includes `valid`, `applied`, row-indexed `errors`, candidate UUIDs, complete before/after records and duplicate
warnings. Preview does not change the database. Applying with `dry_run=false` writes every
validated row in one transaction, or none if any row fails. The client should show preview results
before applying. Import parent definitions before their analytic values.

An explicit `id` preserves a supplied UUID on creation. Source versions are ignored when restoring a previously absent UUID; its local version starts at 1.
Existing records are updated only by
that UUID, with `expected_version` (or an exported `version`). Names and codes never silently
select an existing record for overwrite. Updating rows contain a full create-shaped record;
exported audit fields are ignored and cannot replace ERP audit identities. Referenced UUIDs must
already exist. Export is paginated; advance offset until an empty page is returned.

External mappings use a separate PUT body:

```json
{"source": "accounting", "external_id": "partner-123"}
```

Sources are normalized to lowercase; external IDs preserve case and compare case-sensitively.
Each external identifier is unique within its source and directory. Repeating the same mapping
is idempotent; assigning it to a different record returns 409. One ERP record may have mappings
to multiple external systems. Export includes mappings separately from record fields; restore
those via the external-identifiers API after importing records.

## Existing warehouse, unit and user APIs

- Warehouse create/PATCH/read now supports `address_storage_enabled` (default false), alongside
  `tracking_mode` and `issue_strategy`. Explicit changes to these settings require
  `settings.manage` and the applicable warehouse permission.
- Unit create/PATCH/read now supports `display_decimal_places` (0–9), independently of existing
  `precision`. Changing display precision does not change conversion results or stored quantities.
  Existing units inherit their former precision for display during migration.
- `PATCH /api/identity/me` edits only email, first/last/display name and `default_warehouse_id`.
  The user is resolved from authentication; `users.manage` is not required. Roles, status, user IDs
  and external identities are rejected. A nonnull default warehouse must be active and accessible
  under `warehouse.read`. Explicit null clears it. GET `/api/identity/me` includes the effective
  default warehouse; an inaccessible/inactive saved default is returned as null for reselection.

Run `.venv/bin/alembic upgrade head` against the configured application database when deploying.
Tests use only the dedicated MariaDB database named by `TEST_DATABASE_URL`, never the application
schema. No migration is automatically run on application startup.

## Accounting currency and internet reference rates

Currencies list now returns `{ items, total }`. The accounting currency remains `AccountingSettings.currency_id`.

- `GET /api/reference-data/currency-rates`: selected base currency, accounting settings version, and latest saved batch for that base (or null).
- `PATCH /api/reference-data/currency-rates/base-currency`: `{ currency_id, expected_version }`; uses the existing accounting settings validation and audit.
- `POST /api/reference-data/currency-rates/load`: `{ base_currency_id, expected_version }`; manually downloads rates for active currency records from `https://api.frankfurter.dev/v2/rates`.

Reads require `settings.read`; changes/imports require `settings.manage`. A rate is quote currency units per **one base currency unit**. Every download preserves its exact decimal rates, individual observation dates, provider, fetch timestamp, actor, base id/code, and missing currency codes in a new immutable snapshot. Unsupported quotes are listed; empty/malformed/provider-failure responses do not replace saved data. Network I/O occurs before acquiring the configuration guard; settings version and active currency codes are checked again under the guard before the batch is committed. Reference rates do not recalculate monetary documents or stock valuation.

Apply Alembic revision `20261011_0010` before using rate endpoints. No external API key or additional scheduled job is needed.
