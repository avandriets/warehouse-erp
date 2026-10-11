# Agent Instructions — Warehouse ERP V1

## 1. Goal

Build a lightweight, convenient, fast, and functional Warehouse ERP V1 as a document-oriented modular monolith. Keep everyday workflows short and enable optional accounting features only when needed. The system must provide a reliable product catalog, warehouses and locations, batch-aware inventory accounting, an immutable inventory ledger, monthly balances, and an auditable document workflow.

The primary architectural rule is:

> No inventory movement without a posted source document.

Users work with business documents. `InventoryMovement` is an internal accounting result of document posting, not a public CRUD resource.

V1 is a modular monolith: one backend process deployment and one MariaDB database, with synchronous document posting through an internal application service. RabbitMQ and a separately running Posting Service are deferred to V2 (section 10.8). Do not introduce separate databases per module, distributed Saga, distributed transactions, full CQRS, or Event Sourcing. Keep domain/application posting rules independent of HTTP and any future broker.

## 2. Core architecture

Use a modular monolith with at least these modules:

- `catalog`: Product, Category, units, product attributes, product inventory policy.
- `warehouse`: Warehouse, Location.
- `inventory`: stock-affecting documents, posting, batches, inventory movements, balances, periods, stock dimensions.
- `planning`: inbound and outbound orders and their fulfillment links.
- `settings`: categorized and scoped settings, resolved policies, cache invalidation.
- `identity`: User, Role, Permission and audit identity.

Apply Clean/Hexagonal Architecture within modules:

```text
API -> Application -> Domain
          ^             ^
          |             |
      Infrastructure implements ports
```

The domain must not depend on FastAPI, SQLAlchemy, HTTP, or database-specific types. The application layer orchestrates use cases and transaction boundaries. Infrastructure implements persistence, locking, caching, and external adapters. API code handles transport, authentication, authorization, DTO validation, and response mapping.

## 3. Product catalog

`Product` is the single catalog and inventory-accounting entity. Do not introduce a separate SKU entity.

- Each product has a unique stable code, name, description, category, brand, units, and product attributes.
- Inventory, document lines, batches, and stock balances reference `product_id`; inventory does not own catalog descriptions or images.
- Each separately tracked item is represented by a Product record, including items distinguished by variant attributes.

Separate warehouse stock tracking from issue allocation. Warehouse settings apply to every Product stored in that warehouse; Product and Category overrides cannot change these settings.

Each Warehouse has a typed inventory policy:

```text
tracking_mode: NONE | BATCH
issue_strategy: MANUAL | FIFO | FEFO, applicable to BATCH tracking
```

- `tracking_mode = NONE`: keep balances by Product, Location, and enabled storage analytics without identifying receipt batches.
- `tracking_mode = BATCH`: additionally retain batch identity from receipt through issue and transfer. This is a storage/accounting mode, not an issue algorithm.
- The warehouse's `issue_strategy` chooses which available batches to consume: `MANUAL` selects batches explicitly, `FIFO` prioritizes receipt order, and `FEFO` prioritizes the earliest expiry date.
- Without batch tracking, issues consume the selected aggregate stock bucket. Batch selection strategies do not apply; do not introduce hidden receipt layers just to emulate batch selection. Cost layers may still be required when FIFO cost valuation is enabled.
- The same Product may be stored on warehouses with different tracking modes, subject to the expiry requirement below and the V1 transfer restrictions in section 6.

Product policy retains `batch_expiry_required: boolean`. Negative-stock allowance is resolved separately according to section 11.4; it is not a warehouse tracking-mode override.

Expiry dates belong to batches, not Product records. Product policy only specifies whether the batch expiry date is mandatory. A Product with `batch_expiry_required = true` may receive or hold stock only in a BATCH warehouse. Reject receipts, positive adjustments, and incoming transfers to a NONE warehouse for such Products. FEFO requires warehouse batch tracking and populated expiry dates for all batches eligible for FEFO allocation; never silently fall back to FIFO for missing expiry data. Expiry must be considered during issue allocation. Expired batches are excluded from automatic allocation and cannot be sold or issued through ordinary Goods Issue documents. They remain visible in stock until an authorized spoilage/disposal write-off posts explicit movements with a mandatory reason. Such a write-off may consume expired stock but must still enforce available quantity. Specify expiry-date boundary semantics and the enterprise timezone before implementation.

Custom storage analytics are configured separately, not as hard-coded MRP or quality flags. Serial-number tracking may be added later but is out of scope for V1.

### 3.1 Approved master-data directories

V1 includes these business directories:

- Products: code, name, category, base stock unit, description, brand, barcodes, attributes, and inventory policy; no separate SKU.
- Categories: hierarchical classification of Products.
- Units: dimension, symbol, conversion definition, and display decimal places.
- Warehouses and hierarchical storage locations; location selection is shown only for address-enabled warehouses.
- Counterparties: one record with code, name, registration/tax identifiers, addresses, contacts, and supplier/customer/other-recipient roles. A counterparty can have multiple roles; do not duplicate it into separate supplier/customer directories.
- Storage analytic definitions and controlled values: the optional balance-defining analytics described in section 9.
- Write-off/adjustment reasons: code, name, applicable operation, and active state; reasons are mandatory for these operations, including spoilage/disposal.
- VAT rates/treatments: rates and distinct no-VAT/zero-rate treatments used in monetary documents and exports.
- Currencies: code, name, symbol, and monetary rounding/display rules. V1 uses one selected accounting currency; no exchange-rate directory is required.
- Price types: code, name, default tax-inclusive/exclusive entry mode, and active state. Users can define types such as retail, wholesale, or purchase; these are examples rather than mandatory seeded types. V1 prices use the accounting currency.

Store price values separately from PriceType definitions through Price Setting documents (section 5.3): Product, price type, effective date, amount, and price unit. A type is a reusable category, not a price amount. Retain price history; select the applicable effective price when filling a monetary document and save the actual price/tax mode on its line. Later price changes never rewrite posted documents. Price lists do not define stock buckets or replace receipt cost used by cost accounting. Automatic price formulas, discounts, and multicurrency price conversion are deferred unless separately requested.

Users and roles remain in identity administration. Enterprise details stay in settings. Document types, batch-selection strategies, and valuation methods are fixed system choices rather than editable directories. Batches are receipt-document references as described in section 6, not a standalone manually maintained directory.

Deactivate referenced master-data records instead of deleting them; preserve references in documents and history. Optional directories must not impose extra fields on simple quantity-only workflows.

### 3.2 Shared master-data behavior

Apply these rules consistently across business directories:

- Identity: use immutable internal identifiers and stable codes unique within the directory's declared scope. Names can be changed. Follow existing code-normalization rules; code changes require an explicit migration/audit policy.
- Archiving: deactivate referenced records instead of deleting them. Historical documents retain references and remain readable. Exclude archived records from ordinary new-document selection, while allowing users to view/search archived entries explicitly. Deactivation does not remove posted data or bypass structural locks.
- Search: support code/name search, Product barcode lookup, and counterparty tax/registration identifier lookup. Use pagination, stable sorting, applicable filters, and indexed lookup paths; do not load entire directories to fill a selector.
- Duplicate protection: reject duplicate normalized codes and barcodes. Warn about similar names and matching counterparty identifiers for review rather than automatically merging or rejecting legitimately distinct records.
- Import/export: support bulk master-data exchange with explicit field mapping, validation preview, row-level error reporting, and duplicate checks. Preserve identifiers and references; imported changes follow the same permissions, audit, deactivation, and structural-lock rules as interactive edits. Never silently overwrite by matching a name or import inventory movements through master-data import.
- Audit: record who created, changed, and archived a record and when; retain meaningful before/after changes. Master-data edits must not rewrite posted document snapshots or reinterpret ledger history.
- Permissions: distinguish viewing, creating, editing/archiving, and import/export actions. Reuse existing module permissions where appropriate and enforce them server-side.
- Inline creation: let authorized users create a Product or counterparty from a draft document's selector, then return to the draft with the new record selected. Preserve unsaved document input; do not post or alter stock as a side effect.
- External mapping: support external identifiers for exchange with accounting and other systems. Map directory/internal record ID to source system and external ID, with uniqueness within the external system/directory scope. A record may have mappings to multiple systems; external identifiers are not substitutes for internal identity.

Brands and manufacturers remain optional Product attributes for V1; dedicated directories are deferred until their own details/workflows are needed. Counterparty contracts, separately managed bank-account directories, and discount-type directories are likewise deferred to the corresponding business scenarios. Basic counterparty/enterprise payment details may still be recorded where needed for documents.

## 4. Document-oriented ERP model

### 4.1 Mandatory invariant

All changes to physical stock must be produced by posting a stock-affecting document. Never create, update, or delete an inventory movement directly from an API endpoint, repository utility, admin screen, import, or test fixture outside the posting mechanism.

Forbidden flow:

```text
POST /inventory/movements -> INSERT inventory_movement
```

Required flow:

```text
Create document
  -> add or edit lines while DRAFT
  -> validate
  -> post atomically
  -> assign receipt-line batch origins when required
  -> generate immutable inventory movements
  -> set document to POSTED
```

Expose document-oriented use cases such as:

```text
CreateGoodsReceipt
UpdateGoodsReceipt
PostGoodsReceipt
ReverseGoodsReceipt

CreateGoodsIssue
UpdateGoodsIssue
PostGoodsIssue
ReverseGoodsIssue
```

Do not expose `CreateInventoryMovement`, `UpdateStock`, or equivalent public use cases.

### 4.2 Common document model

Stock and planned documents should share consistent concepts without forcing every type into one oversized aggregate.

Suggested common header fields:

```text
id: UUID
number: string
document_date: date/time
status: DRAFT | POSTED | CANCELLED | REVERSED
company_id: UUID, if multi-company scope is enabled
warehouse_id: UUID, when applicable
source_document_id: UUID?, when generated from another document
comment: string?
created_at / created_by
updated_at / updated_by
posted_at / posted_by
cancelled_at / cancelled_by
reversed_at / reversed_by
version: integer
```

Suggested common line fields:

```text
id: UUID
document_id: UUID
line_number: integer
product_id: UUID
quantity: positive decimal
unit_id: UUID
location_id: UUID, when applicable
batch_source_line_id: UUID?, according to tracking policy
stock attributes: typed fields required by policy
source_line_id: UUID?, when generated from an order line
```

Use dedicated document and line types when their invariants differ. Avoid a generic `document(type, json_payload)` design for core accounting documents.

### 4.3 Document lifecycle

Use this lifecycle for stock-affecting documents:

```text
DRAFT -> POSTED -> REVERSED
   \-> CANCELLED
```

Rules:

- `DRAFT`: editable, produces no movements and affects no balance.
- `POSTED`: validated and posted atomically; movements exist; normal editing and deletion are forbidden.
- `CANCELLED`: an unposted document was abandoned; it produces no movements.
- `REVERSED`: a previously posted document was neutralized by explicit compensating movements and an audit link to the reversal operation/document.
- Never silently edit or delete a posted document or its movements.
- Do not implement reversal as destructive deletion of ledger rows.
- Posting and reversal must be idempotent. Repeating the same command with the same idempotency key must not duplicate movements or batches.
- Documents dated in a closed inventory period cannot be posted, edited, cancelled through movement deletion, or reversed into that closed period. Corrections must be posted in an open period with a reference to the original document.

If a simpler V1 uses `CANCELLED` to represent reversal, it must still create compensating movements and retain the complete audit trail. Prefer the explicit `REVERSED` state because it distinguishes an abandoned draft from a neutralized posting.

## 5. Initial document catalog

### 5.1 Stock-affecting documents

These documents create inventory movements only when posted.

#### Initial Receipt / Stock Initialization (`INITIAL_RECEIPT`)

Purpose: enter opening stock during migration, system launch, or an explicitly authorized stock discovery process.

Posting result:

```text
INITIAL_RECEIPT +quantity at destination location
```

This is a receipt document and is batch-forming when batch tracking is enabled.

#### Goods Receipt (`GOODS_RECEIPT`)

Purpose: record the physical receipt of goods from a supplier or another external source.

Posting result:

```text
RECEIPT +quantity at destination location
```

It may fulfill an `InboundOrder`. It is batch-forming when batch tracking is enabled.

#### Goods Issue (`GOODS_ISSUE`)

Purpose: record the physical issue, consumption, shipment, write-off, or other outbound movement.

Posting result:

```text
ISSUE -quantity from source location and stock bucket
```

For a batch-tracked Product, each issue line or allocation must identify a batch, or the posting service must allocate batches deterministically according to the configured strategy. The resulting movement always identifies the selected batch.

#### Stock Transfer (`STOCK_TRANSFER`)

Purpose: move stock between warehouses and/or locations.

Posting result for every allocation:

```text
TRANSFER_OUT -quantity from source location
TRANSFER_IN  +quantity to destination location
```

Both movements must be created in one transaction, share the same document/line reference and transfer group, and preserve Product, batch, and all enabled storage analytics. A transfer does not create a new batch. In V1, source and destination warehouses must have the same `tracking_mode`; reject transfers between NONE and BATCH warehouses in either direction. See section 6.

#### Stock Adjustment (`STOCK_ADJUSTMENT`)

Purpose: apply an authorized positive or negative correction with a mandatory reason.

Posting result:

```text
ADJUSTMENT +delta
or
ADJUSTMENT -delta
```

A positive adjustment is receipt-like. When it introduces stock for a batch-tracked Product that is not already tied to an existing batch, it must create or explicitly select a valid batch according to the posting rules.

#### Inventory Count (`INVENTORY_COUNT`)

Purpose: record physical counting results. The count itself should not silently overwrite balances.

Preferred V1 behavior:

```text
Inventory Count
  -> compare expected and counted quantities
  -> create linked Stock Adjustment draft for variances
  -> separately review and post Stock Adjustment
```

If the count is implemented as a directly stock-affecting document, its posting must still generate explicit adjustment movements with document and line links. Never update a quantity field directly.

### 5.2 Planned/order documents

Planned documents describe business intent and fulfillment. They never create inventory movements merely by being created, confirmed, approved, or closed.

#### Inbound Order (`INBOUND_ORDER`)

Purpose: plan expected incoming goods. It may later generate one or more `GoodsReceipt` drafts.

```text
Inbound Order #100
  -> Goods Receipt #245
  -> POST Goods Receipt
  -> InventoryMovement +quantity
```

Support partial receipts. Track ordered, generated, posted/received, cancelled, and remaining quantities per order line. Only posted receipt quantities count as fulfilled stock.

#### Outbound Order (`OUTBOUND_ORDER`)

Purpose: plan expected outgoing goods. It may later generate one or more `GoodsIssue` drafts.

```text
Outbound Order #200
  -> Goods Issue #310
  -> POST Goods Issue
  -> InventoryMovement -quantity
```

Support partial issues. Track ordered, generated, posted/issued, cancelled, and remaining quantities per line.

An order-to-document link must be explicit at both header and line level. Creating a real document from an order must be idempotent and must not over-generate quantity beyond the remaining fulfillable amount.

The distinction is mandatory:

```text
Planned/order document = intention, no ledger effect
Stock-affecting document = physical/accounting fact after POST, creates ledger entries
```

Reservations are a separate future concern. Do not treat an order as physical stock movement. If reservations are introduced, model them separately from on-hand movements and balances.

### 5.3 Price-setting document

#### Price Setting (`PRICE_SETTING`)

Purpose: establish Product prices by price type from an effective date. This is a business document with a header and lines, not direct editing of current price values.

Header fields include document number/date, effective date/time, comment, status, and audit identity. Each line specifies Product, price type, price unit, amount, accounting currency, and the actual tax-inclusive/exclusive mode. Rates/treatments are specified when applicable. The same document may set several Products and price types; reject duplicate Product/type/unit keys within a document.

Lifecycle: DRAFT is editable and has no effect; POSTED is immutable and writes the effective price register atomically; CANCELLED applies to abandoned drafts. Posting is idempotent and creates neither inventory movements nor batch origins nor receipt-cost changes. Future effective prices become applicable only from their effective date/time.

Preserve prior prices and the source document/line for each register entry. Define a unique effective entry for each Product/price type/price unit/effective date-time; reject conflicting entries rather than silently overwrite them. Monetary documents select the applicable price for their pricing date and save their actual price; later price setting never changes existing posted documents.

Correct a posted price-setting document by an explicit linked replacement/correction that supersedes its erroneous register entries while retaining them for audit. Price-history selection must distinguish superseded entries from valid entries; do not delete history or generate stock reversals. Enforce numbering, permissions, and the enterprise date lock for posting/correction and effective dates. Historical corrections never rewrite prices already saved on posted monetary documents.

Expose one simple price-entry document with optional bulk import of lines. Automatic formulas, percentage repricing, discounts, and currency conversion remain outside V1 unless separately requested.

## 6. Receipt documents as batches

A stock receipt document is the origin of an accounting batch; do not require a separate manually maintained Batch directory. When the receiving Warehouse has `tracking_mode = BATCH`, each posted receipt line forms an identifiable batch for that Product.

Use the receipt document and its line as the batch reference:

```text
batch origin = posted receipt document + receipt line
batch_source_line_id = stable globally unique receipt-line identifier
```

The receipt document number/date labels the batch for users. The line distinguishes Products and stock with different expiry dates or supplier lot numbers within the same receipt. Separate such stock into separate receipt lines. This does not introduce a separate SKU or an independently editable Batch entity.

Batch-forming origins include Initial Receipt, Goods Receipt, and a positive Stock Adjustment/count variance that introduces previously unrecorded stock. A positive correction for an already identified batch may retain its original reference explicitly. Transfers and reversal/compensation flows preserve original batch references rather than form new batches.

Receipt-line data includes:

```text
id
product_id
supplier_batch_number?  # informational supplier lot, not the accounting-batch identity
manufactured_at?
expires_at?
storage analytic values
```

- Required expiry and analytic data must be present before receipt posting. Expiry belongs to the receipt-line batch data; Product policy only controls its requirement.
- A repeated supplier lot in another receipt does not silently merge the accounting batches: each receipt origin remains traceable.
- Receipt movements reference their own batch-forming source line. Issues, transfer pairs, adjustments using an existing batch, and reversals retain this origin. `source_document_line_id` identifies the current operation; `batch_source_line_id` identifies the original receipt. They are different links.
- MANUAL lets users select available receipt batches; FIFO prioritizes receipt posting order, and FEFO prioritizes expiry with deterministic receipt/line tie-breaks.
- Posting validates that the referenced origin is a posted batch-forming line for the same Product. Use an enforceable shared source-line registry if document lines live in separate tables.
- For a Warehouse with `tracking_mode = NONE`, `batch_source_line_id` is NULL; document audit links still remain mandatory.
- V1 transfers are allowed only between warehouses with matching tracking modes: BATCH to BATCH retains the original receipt-line origin and expiry data; NONE to NONE retains aggregate stock and document audit links. Reject BATCH to NONE and NONE to BATCH transfers before any movements are written. Do not discard a batch origin or invent a new batch from a transfer. Cross-mode conversion is deferred to a separately specified migration workflow.
- Batch assignment and movements are atomic with posting. Retries do not duplicate origins or movements.
- A batch balance/history list is a derived view by receipt origin, not a CRUD directory. Posted origin data is immutable; corrections follow explicit document flows.

## 7. Posting engine and rules

Implement posting as an application service with domain rules, not as controller logic or database triggers hidden from the application.

The posting transaction must:

1. Load and lock the document or verify its optimistic version.
2. Verify that it is `DRAFT` and that the idempotency key has not already succeeded.
3. Resolve effective typed inventory policy for each Product and Warehouse involved; transfers resolve both source and destination policies.
4. Validate header, lines, positive quantities, units, warehouses, locations, permissions, stock dimensions, batch data, and the open accounting period.
5. For outgoing lines, resolve exact stock buckets/batch allocations and lock/revalidate current total rows needed to prevent overselling (section 10).
6. Enforce the resolved negative-stock policy for every outgoing allocation under concurrency.
7. Assign receipt-line batch origins or preserve an explicitly referenced existing origin for receipt-like lines where required.
8. Generate all inventory movements, each linked to its source document and source line, and apply their deltas to current totals, period turnovers, and enabled valuation projections in the same transaction (section 10).
9. Mark the document `POSTED`, record the actor and posting time, and persist the posting/idempotency record.
10. Commit all changes atomically. Any failure rolls back the entire posting.

Posting rules should be selected by document type through explicit strategies/handlers, for example:

```text
PostingService
  -> InitialReceiptPostingRule
  -> GoodsReceiptPostingRule
  -> GoodsIssuePostingRule
  -> StockTransferPostingRule
  -> StockAdjustmentPostingRule
```

Do not build a user-configurable rules engine in V1.

Minimum invariants:

- A document must contain at least one line.
- Line quantity must be greater than zero; the posting rule determines movement sign.
- All referenced entities must be active and valid on the document date.
- Source and destination locations of a transfer must differ.
- Transfer OUT and IN totals must match for every line/allocation.
- A batch-tracked Product requires a batch on every resulting movement.
- A non-batch Product forbids a batch.
- Stock-defining attributes must not be lost or changed by transfer.
- Negative stock is rejected unless the resolved policy explicitly allows it; enabling it never bypasses other posting invariants.
- Closed periods are immutable.
- One source document line may create multiple movements, but every movement has exactly one source document and source line.

## 8. Inventory movement ledger

`InventoryMovement` is immutable and is the source of truth for stock changes. It should contain at least:

```text
id: UUID
movement_type
quantity_delta: signed decimal
occurred_at
product_id
warehouse_id
location_id
batch_source_line_id?
typed stock attributes
source_document_type
source_document_id
source_document_line_id
posting_id / posting_version
reverses_movement_id?
created_at
created_by
```

Required database constraints/indexes:

- Foreign keys to the source document and line, or an equivalent enforceable reference registry if documents use separate tables.
- A movement cannot exist without `source_document_id` and `source_document_line_id`.
- Unique posting output identity, such as `(source_document_id, source_document_line_id, posting_version, movement_sequence)`, to prevent duplicates.
- Indexes supporting balance queries by period and `InventoryKey`.
- Check constraint preventing zero `quantity_delta`.

No public general-purpose create/update/delete endpoints are allowed for movements. A read-only ledger/history API is allowed and should expose the source document link.

Reversals create new movements with opposite deltas. They reference both the reversing source document/operation and the original movement using `reverses_movement_id` or an equivalent explicit link.

## 9. Inventory key and configurable storage analytics

Define the logical stock bucket as:

```text
InventoryKey = Product + Location + optional Batch + enabled storage analytics
```

Users can add storage analytics when their business needs them, or work without any additional analytics. MRP was an example of a possible custom analytic, not a mandatory built-in feature. Do not hard-code MRP or quality-status accounting into V1.

Distinguish:

1. Product attributes: describe the item, such as brand, color, or pack size; owned by Catalog.
2. Storage analytics: distinguish stock balances and determine which stock bucket an issue consumes. Users configure these explicitly.
3. Informational document/movement attributes: used for reporting and do not split stock balances.

Use a small controlled configuration model for storage analytics:

```text
StorageAnalyticDefinition(id, code, name, value_type, required, enabled)
StorageAnalyticValue(definition_id, typed_value)
```

Definitions must specify a supported value type; validate and normalize values before posting. Document lines and movements retain the selected values. Balance queries, issue selection, transfer, and reversal must preserve the complete analytic combination. The same logical combination must always identify the same stock bucket.

Expose analytics as optional fields in receipt and issue forms; keep the basic workflow simple when none are enabled. An informational attribute must never silently become a balance-defining analytic. Lock balance-defining analytic configuration after the first stock posting in its accounting scope (enterprise-wide in V1); any later structural change would require a separately designed migration preserving balances and history.

Keep this a small configuration feature, not a universal rules engine or an unvalidated JSON payload.

## 10. Stock registers, current totals, and inventory periods

Use a register-style design inspired by 1C accumulation registers: posted documents produce movements, and stored totals provide fast balance reads. Implement it as ordinary MariaDB/InnoDB tables inside the existing modular monolith, not a generic register-construction platform.

### 10.1 Three layers

1. `InventoryMovement`: immutable quantity deltas and their source document/line, Product, warehouse/location, receipt-line batch origin, analytics, accounting date, and posting timestamp. This is the authoritative history.
2. `StockBalance`: one current quantity total per normalized `InventoryKey`, updated synchronously by posting. It is a rebuildable projection, not an independently editable source of truth.
3. Closed monthly quantity snapshots and period turnovers: accelerate historical reports and retain the closing state by the same stock keys.

```text
Posted document
  -> immutable movements
  -> current totals
  -> period turnovers
  -> COMMIT together
```

Suggested structures:

```text
StockBalance(stock_key_id, quantity, version, updated_at)
PeriodTurnover(period_id, stock_key_id, incoming, outgoing, adjustments)
ClosedPeriodBalance(period_id, stock_key_id, closing_quantity, closed_at)
```

Represent positive/negative adjustments consistently without counting them again as receipts/issues in the same report. Opening stock is an explicit Initial Receipt movement, never a hidden initial quantity. No public API, import, or admin form can directly set `StockBalance.quantity`.

### 10.2 Stock keys and reads

A stock key identifies Product + warehouse location + optional receipt-line batch origin + enabled storage analytics. Warehouse is determined by location and retained for efficient filtering. A non-addressed warehouse uses its default internal location. Normalize absent batch/analytic values and enforce unique logical keys even when nullable fields are involved. Do not rely on nullable composite uniqueness or an unchecked JSON/hash alone; equivalent analytic combinations must resolve to the same key.

Read current balances from `StockBalance`, with indexed warehouse/Product filters and pagination. Warehouse/Product totals aggregate current stock-key rows, not all historic movements. Batch details show receipt number/date, expiry, location, and analytics. Keep expired physical stock in on-hand totals; show eligible-for-issue stock separately. Planned orders do not reduce on-hand quantity; reservations are outside V1.

Posting cannot use a cached UI balance for availability checks. Check authoritative transactionally maintained totals at the exact stock keys being consumed. Read batch allocation candidates from current positive balances, excluding expired stock for ordinary issues. Manual allocations identify the exact keys; FIFO/FEFO use deterministic ordering and locked/revalidated candidates.

Do not create additional Product/warehouse aggregate tables or Redis balance caches initially. Add derived aggregate projections only after representative measurements show a need, with the same rebuild and consistency rules.

### 10.3 Atomic posting and concurrency

Within one database transaction:

1. Lock/check the document, idempotency record, relevant structural policy locks, and open-period state.
2. Resolve the typed policy snapshot and normalize the affected stock keys.
3. Create missing total/guard rows safely under unique constraints, and lock affected rows in a deterministic order. Never use an unlocked missing-row read as a concurrency guard.
4. Resolve/revalidate allocations, including aggregate demand across repeated lines; check expiry and available quantities. Cost accounting always prohibits negative stock; otherwise apply the explicit allowance.
5. Calculate quantity and, when enabled, cost effects. Transfers validate source availability and preserve quantities, batches, analytics, and transferred value.
6. Append immutable movements; apply the exact same deltas to current totals and period turnovers; update valuation projections when enabled.
7. Mark the document POSTED and persist the successful idempotency result, then commit.

Any failure rolls back all layers. In V1, a successful posting API response is returned only after commit and means totals are already updated. The internal posting service must never defer totals updates to another worker after committing movements. MariaDB `SELECT ... FOR UPDATE` or guarded atomic updates must execute inside this transaction. Use a globally consistent lock order for document/policy/period/stock/valuation resources, and bounded whole-transaction retries for deadlocks with the same idempotency key. A document-level retry never duplicates deltas.

For example, if stock is 10 and concurrent documents each issue 7, at most one succeeds when negative stock is prohibited; the other observes insufficient stock after serialization. Transfer OUT and IN commit together; no intermediate half-transfer is visible as committed stock.

Reversal appends compensating movements and updates totals through the same engine. It does not delete original movements or directly restore an old total. Reversing a receipt must check whether removing its quantity is permitted; it may fail if that stock has already been consumed.

### 10.4 Historical balances and monthly closing

For a requested accounting timestamp:

```text
balance at time T
  = nearest closed snapshot before T
  + sum(movements after snapshot boundary through T)
```

If no closed snapshot exists, sum the relevant movements from the beginning. Use explicit nonoverlapping timestamp boundaries and deterministic posting order for ties. Distinguish accounting date from posting time; ordinary historical reports use accounting dates, while audit history also records when the transaction actually occurred. Current totals cover committed postings; future-dated documents remain drafts until their accounting date becomes eligible.

Quantity-only backdated posting in an open period changes current totals and that period's turnovers. When negatives are forbidden, also validate the affected historical balance trajectory from the insertion point; checking only today's balance is insufficient. Reject a backdated operation that would introduce a forbidden historical deficit. This more expensive check belongs to backdated posting, not ordinary balance reads.

Costed operations must follow the defined valuation sequence. For a simple V1, reject accounting dates preceding the last valued operation in the affected valuation scope rather than silently recalculate immutable past issue costs. Backdated cost recomputation is a separate future capability; explain the restriction to users before posting.

Period closing coordinates with posting so no document can enter the closing period during snapshot calculation. Reconcile register movements, turnovers, and opening/closing totals, save immutable closing snapshots, and mark the period closed atomically or through a protected recoverable closing operation. Closed-period corrections use new documents in an open period with original-document links. Closing does not erase movements or reset current totals.

### 10.5 Stock cost accounting

Keep physical stock selection and monetary valuation separate. When cost accounting is off, do not require monetary register data.

When on, retain immutable cost effects with document/line and quantity-movement references as applicable, and maintain corresponding current valuation totals synchronously. Value-only corrections, when supported, must use explicit source documents and cannot alter quantity balances. InventoryMovement's nonzero-quantity constraint does not apply to the separate cost register.

For moving weighted average, the proposed valuation scope is Product + Warehouse + stock-defining analytics, excluding cell and receipt-line batch origin. It pools interchangeable stock within a warehouse; this grouping must be confirmed before costing implementation. Maintain quantity and total value for the valuation scope:

```text
receipt: new quantity = old quantity + receipt quantity
         new value = old value + receipt cost
issue cost = issued quantity * (current value / current quantity)
```

Use high-precision calculation and defined monetary rounding, allocating any rounding remainder on final consumption so zero quantity does not leave a phantom value. Intra-warehouse cell transfers do not change pooled valuation. Inter-warehouse transfers carry source issue cost into destination receipt value. FIFO valuation instead consumes receipt cost layers; these remain distinct from user-visible physical batch selection.

Month snapshots/rebuild procedures must include valuation totals and any FIFO-layer state when enabled. Do not label balances as available for sale merely because their quantity/value is positive: expiry and other allocation restrictions still apply.

### 10.6 Verification, rebuilding, and performance

Enforce the reconciliation identities:

```text
current quantity for key = sum(all committed quantity deltas for key)
period close = period open + receipts - issues + signed adjustments
```

Compare stored projections against the authoritative journals. Rebuild totals into temporary/versioned tables from a consistent journal snapshot, then validate and swap under a posting barrier or catch-up mechanism; never replace live totals with a stale rebuild while posting continues. No manual correction of projected totals is allowed.

Index current keys for warehouse/Product/batch selection and movements for stock key + accounting timestamp and source document. Benchmark representative volumes, analytic combinations, and concurrent hot-key writes. Compare normal balances, receipt/issue posting, transfers, historical reports, and closing. No unmeasured claim of being faster than 1C is implied.

Official design references:

- [1C accumulation registers: records, dimensions, resources, and current totals](https://1c-dn.com/library/tutorials/practical_developer_guide_understanding_accumulation_registers/).
- [MariaDB FOR UPDATE transaction locking](https://mariadb.com/docs/server/reference/sql-statements/data-manipulation/selecting-data/for-update).

### 10.7 V1: synchronous posting inside the monolith

The API calls the inventory application PostingService in-process. The service validates permissions, document version/idempotency, settings, period, and stock, then executes the atomic transaction described in section 10.3. Return the posted document/result after commit or a domain-specific error after rollback. If the response is lost after commit, retrying with the same idempotency key returns the recorded result without duplicate posting.

Keep one explicit application entry point for each posting/reversal use case. Controllers handle transport, not accounting rules. Use the same engine for all stock-changing documents; UI, imports, and integrations cannot update totals directly. Preserve concurrency locks, deterministic resource ordering, and bounded transient retries even without RabbitMQ: simultaneous HTTP requests can execute concurrently inside a monolith.

V1 has no RabbitMQ dependency, outbox-based posting dispatch, PostingJob queue state, separate posting worker deployment, or accepted-but-not-yet-posted API flow. Do not build V2 infrastructure as a prerequisite for V1. Extracting execution later should reuse the domain/application engine, not redesign ledger rules.

### 10.8 V2 roadmap: dedicated Posting Service and RabbitMQ

The following describes a deferred V2 design only. It is not part of V1 implementation or acceptance checks.

Run the Posting Service as a separately deployable worker process from the shared backend codebase, using the same MariaDB database and existing domain/application posting rules. It is a runtime boundary, not a requirement for independent microservices or duplicate models.

```text
API: save/freeze document version + PostingJob + Outbox in one transaction
  -> Outbox publisher -> RabbitMQ
  -> Posting Service
  -> one MariaDB transaction: movements + totals + valuation + document/job result
  -> COMMIT -> acknowledge RabbitMQ message
```

The API creates durable posting requests; RabbitMQ buffers and delivers them; the service executes them. RabbitMQ messages contain job/document identifiers, operation, and expected document version, not an authoritative copy of editable document data. All stock-changing operations, including receipts, issues, transfers, adjustments, and reversals, go through this service. Do not retain an alternative synchronous API path that bypasses the queue. Closing and structural-setting changes still coordinate through the same period/policy guards.

A request atomically records the initiating user, operation, expected version, idempotency key, and outbox entry, and freezes editing of the requested document version. Reject competing edits/requests. The service loads the version from the database, revalidates permissions and current period/policy/availability, and preserves initiating-user audit identity along with worker execution metadata. Do not put bearer tokens in messages.

Keep processing state in a separate PostingJob, e.g. QUEUED, PROCESSING, SUCCEEDED, REJECTED, FAILED. DRAFT/POSTED/REVERSED remain business document states; a QUEUED job has no stock effect. Return HTTP 202 and a job identifier when accepted; expose job status with a human-readable failure reason. Documents stay immutable while a live request is pending; allow correction/resubmission after a terminal failure through explicit versioning. Recover abandoned PROCESSING jobs safely.

Use a durable RabbitMQ queue, persistent messages, publisher confirms, and manual acknowledgements. Retain/retry outbox entries until confirmed publication. Acknowledge a successful message only after the MariaDB transaction commits. Crash after commit but before acknowledgement may cause redelivery; persisted job/idempotency checks must return the already recorded result without reposting. Business rejections are persisted and acknowledged; retry temporary errors with bounded backoff, and preserve exhausted/invalid tasks for diagnosis rather than infinite immediate requeue loops. The database job record remains the authority for processing results.

Default to one active consumer with prefetch=1 and sequential processing. Single Active Consumer can provide standby worker failover; standby processes do not increase throughput. After disconnect/failover an old in-flight database transaction can overlap a new delivery, so job/document locks and idempotency remain necessary even in sequential mode. Queue delivery order is not a strict global business/accounting order, especially across publishers and retries.

Two or three active consumers are an optional future operating mode after contention tests; concurrent document completion order differs from delivery order, and deterministic locks/retries remain mandatory. Switching modes requires controlled worker/queue configuration and accounting-order checks, not merely launching more replicas. Never promise constant processing or end-to-end response time: monitor queue age/depth separately from execution time, by document size and contention.

Official transport references:

- [RabbitMQ consumers and Single Active Consumer](https://www.rabbitmq.com/docs/consumers).
- [RabbitMQ acknowledgements and publisher confirms](https://www.rabbitmq.com/docs/confirms).

## 11. Settings and policies

Store configurable settings in the relational database, organized by category and scope.

Suggested model:

```text
SettingsCategory(id, code, name)
SettingDefinition(id, category_id, key, value_type, default_value, is_required)
SettingValue(id, definition_id, scope_type, scope_id, value, updated_at, updated_by)
```

For inventory settings that explicitly permit scoped overrides, use:

```text
Product -> Category -> Warehouse -> Company -> Global -> default
```

Each setting definition declares its allowed scopes. Enterprise-only settings (currency, cost valuation, VAT, date lock) do not inherit Product or Category overrides; warehouse settings apply to their warehouse, and user preferences never override accounting or access rules. `tracking_mode` and `issue_strategy` are explicit Warehouse settings, not members of the generic override chain; Product/Category/Company/Global values cannot override them. Product `batch_expiry_required` is an explicit Product requirement. Resolve these together with any permitted negative-stock overrides into a typed policy for the Product and Warehouse involved in each operation.

Do not let domain code request raw string keys. Resolve settings into typed objects such as `InventoryPolicy` before executing use cases.

Cache resolved policies, not individual keys. For V1 use an in-process cache with a short TTL plus explicit invalidation after settings changes. Posting must use one consistent resolved-policy snapshot for the whole transaction.

### 11.1 Enterprise details and accounting currency

V1 must provide a simple enterprise settings screen with details used in printed documents:

- legal/display name;
- tax and registration identifiers, with labels appropriate to the enterprise;
- legal and postal addresses;
- contact details;
- bank/payment details when needed by the document template;
- optional logo.

Start with one enterprise profile; do not require multi-company setup for ordinary use. Document print templates use these details. Preserve the enterprise details used for posted documents so later settings changes do not silently alter historical document output.

Configure one accounting currency with a currency code and display/rounding rules. Monetary fields and reports must identify their currency. Accounting currency is separate from whether stock cost accounting is enabled. Multicurrency transactions and exchange-rate accounting are outside V1 unless separately requested. Lock the accounting currency after the first posted monetary document; V1 does not expose an ordinary currency change afterward.

### 11.2 Quantity accounting versus stock cost accounting

Quantity accounting is mandatory: receipts increase quantities, issues decrease them, and balances reconcile with the movement ledger.

Stock cost accounting is a separate feature: receipt stock carries a cost; issues consume both quantity and the corresponding stock value. Receipt cost is distinct from a selling price or a custom storage analytic. Batch selection (MANUAL/FIFO/FEFO) and the cost valuation method are different decisions and must not be conflated.

V1 must support an enterprise-level setting:

```text
cost_accounting_enabled: boolean = false
```

Expose it as a simple “Enable stock cost accounting” toggle in enterprise accounting settings. It applies consistently to the enterprise, not as a Product/Category/Warehouse override.

- Disabled: posting records quantities and storage analytics; stock costs are not required, cost fields are hidden from the basic workflow, and stock valuation/cost-of-issue reports are unavailable.
- Enabled: receipts record stock cost in the accounting currency, issues calculate cost, and reports expose stock value and cost of issues. Transfers preserve total stock value; adjustments and reversals must reconcile both quantities and values.
- Selling prices are separate from stock cost and must not be substituted for receipt cost.
- Resolve this setting once per posting transaction along with the other accounting policies.

Select the cost-accounting mode before the first stock posting, including opening-balance documents. After that posting the mode is locked as described in section 11.10. V1 does not expose enabling/disabling on an active ledger; any future mode migration would require a separately designed conversion procedure preserving quantities, values, and history.

When cost accounting is enabled, expose an enterprise-level `cost_valuation_method` setting with these planned options:

- `MOVING_WEIGHTED_AVERAGE`: recalculate average unit cost after receipts; issues consume stock at that average.
- `FIFO`: consume the value of the earliest available receipt cost layers; cost layers are needed even when physical batch tracking is disabled.

The default valuation method is `MOVING_WEIGHTED_AVERAGE`. Keep the valuation method separate from physical batch selection. Specify valuation grouping, transfers, adjustments, reversals, rounding, and closed-period behavior before implementing each method. The valuation method is locked after the first stock posting; changing it later would require a separately designed migration, outside normal V1 settings. Negative stock is controlled by the inventory setting described in section 11.4. When cost accounting is enabled, every outgoing posting must reject insufficient stock regardless of the negative-stock setting. V1 does not implement provisional costing for negative stock.

### 11.3 Address-based storage

Each warehouse has `address_storage_enabled: boolean = false`.

- Disabled: the user selects only the warehouse. Internally, movements use one default location so ledger keys remain consistent; do not expose a required cell field.
- Enabled: users select configured locations/cells for receipt, issue, transfer, and counting.
- Both modes preserve warehouse-level totals. Lock this mode after the first stock posting in the warehouse; V1 does not expose ordinary mode switching afterward.

### 11.3.1 Warehouse batch tracking and allocation

Configure `tracking_mode = NONE | BATCH` and, for BATCH only, `issue_strategy = MANUAL | FIFO | FEFO` separately for each warehouse in general warehouse settings. Product cards expose the expiry requirement, not warehouse tracking or allocation settings. These settings are editable in the admin application and read-only in the warehouse application, as described in section 11.11.

Lock warehouse tracking mode after the first stock posting in that warehouse, including opening balances. Changing allocation strategy is prospective: selecting FEFO requires expiry dates on existing stock eligible for allocation and on future batch receipts. Enabling a Product's expiry requirement requires all its existing stock to be in BATCH warehouses with expiry data; reject the change until these prerequisites hold. Disabling the requirement does not remove stored expiry dates or bypass restrictions on expired stock.

### 11.4 Negative-stock setting

Expose “Allow negative stock” (`negative_stock_allowed: boolean = false`) in enterprise inventory settings. Explicit Warehouse/Category/Product overrides may follow the declared inventory policy scopes.

- Disabled: reject any issue, transfer-out, negative adjustment, or reversal that removes more than the available stock in a bucket, including concurrent posting.
- Enabled: allow negative quantity balances in explicitly identified stock buckets and display them clearly in balances/reports. Keep document and ledger audit links intact.
- The setting does not bypass batch identity, expiry restrictions, required storage analytics, permissions, or date locks. A batch-tracked issue still needs an existing valid batch; automatic allocation must not invent batches or silently select nonexistent stock. A deficit allocation must be explicit.
- Disabling with existing negative balances requires resolving those deficits first; do not conceal or rewrite them.
- With cost accounting enabled, negative stock is always forbidden for issues, transfer-out, negative adjustments, and reversals that remove stock. This rule takes precedence over all inventory policy scopes and overrides. Make the negative-stock toggle unavailable while cost accounting is enabled, with an explanation. Validate the rule server-side as well. The cost-accounting mode must be chosen before first stock posting and is locked afterward; see section 11.10. V1 does not require provisional issue costing or reconciliation for negative stock.

### 11.5 Date lock

Expose enterprise-level `changes_locked_through: date?`, initially unset. Documents with an accounting date on or before that date cannot be created, edited, posted, cancelled, or reversed into the locked date range. Corrections use an eligible open date. Evaluate dates in the enterprise accounting timezone. This operational lock supplements closed-period restrictions; removing the date lock never reopens a closed period or permits editing posted documents. Only authorized administrators can change the lock, with an audit trail.

### 11.6 Document numbering

Configure automatic numbering separately for each document type: prefix, numeric width, and whether the sequence resets annually. Numbers must be unique within their defined type/enterprise/year scope and allocated safely under concurrent creation. Preserve assigned numbers; gaps are acceptable and numbers must not be reused after cancellation. Changing a numbering rule applies to future documents. Do not add a requirement for legally gapless numbering without a separately agreed jurisdiction-specific document requirement.

### 11.7 User preferences

Extend the user settings model with `default_warehouse_id`, separate from roles, permissions, and enterprise accounting settings. Use it to prefill new documents; users can change the warehouse when authorized. A default never grants access. If it is inactive or inaccessible, ask the user to select an available warehouse instead of retaining an invalid default. Store preferences per user and provide an editable user settings screen; UI preferences may be added later without modifying accounting policies.

### 11.8 VAT

Add enterprise-level VAT configuration, independent of stock cost accounting:

- whether VAT applies to the enterprise's monetary documents;
- a maintained directory of VAT rates/treatments, including a distinct no-VAT treatment and zero rate;
- default rate/treatment, with a Product default where appropriate;
- default price-entry mode: tax-inclusive or tax-exclusive.

Do not hard-code a country's rates. Monetary document lines preserve the actual rate/treatment, price-entry mode, net amount, VAT amount, and gross amount. Support different rates on different lines and print their totals. Use Decimal arithmetic and explicit monetary rounding rules. Document-specific changes require suitable permissions; later default/rate changes must not alter posted documents. Quantity-only documents do not require artificial prices or tax amounts.

VAT and cost valuation are different concerns. Before implementing receipt valuation, agree how recoverable and nonrecoverable VAT affects receipt cost for the enterprise's tax regime. V1 VAT amount calculation and printing do not imply full tax returns or statutory tax accounting.

### 11.9 Units, conversion, and display precision

Each Product has one base stock unit (`unit_id`). Store balances and movement quantities in that unit. Selecting a unit belongs to the Product card, not an enterprise feature toggle. Compatible alternative units may be used for input and display; convert input into the base unit when saving a document line and use the base quantity for posting.

Each Unit has a configurable `display_decimal_places` field for screens and printed documents (for example pieces: 0, liters: 3). Display precision does not define calculation/storage precision or valid quantity increments. If an indivisible unit must reject fractional quantities, specify that as a separate validation rule; hiding decimal places alone must never silently round input.

Use exact decimal arithmetic for quantities and conversion coefficients, never binary floating point. Maintain higher internal precision than display precision. Choose the database scale, calculation precision, rounding rule, and supported quantity range to cover supported conversions before implementation. Arbitrary conversions, especially reciprocals, may require rounding at the storage boundary; do not promise mathematically lossless conversion for every value. Round once at the defined boundary, never after each intermediate conversion.

- Changing the displayed unit must always recalculate from the preserved base quantity, not from the previously rounded display value.
- Merely changing display precision or units must not change a stored quantity or count as a quantity edit. An unchanged rounded field must not overwrite the original precise value on save.
- Preserve the entered quantity/unit, conversion coefficient used, and resulting base quantity on document lines for reproducibility. Posted movements and reversal quantities use the saved base quantity.
- Define conversion factors using decimal values or exact ratios as appropriate, and restrict conversion to compatible dimensions (volume to volume, mass to mass, etc.). Mass/volume conversion requires product-specific data and is outside these generic unit conversions.
- Distinguish US liquid gallons and imperial gallons with separate unit identities and coefficients; never use an ambiguous generic gallon.
- Changes to coefficients or a Product's base unit must not reinterpret historical documents or ledger entries. Lock the base unit after the first stock posting for that Product; any future base-unit migration is outside ordinary V1 settings.

Unit conversion is approved for V1. Packaging and product-specific pack-size conversions remain deferred; do not require packaging in basic workflows.

### 11.10 Lock structural settings after posting

Lock structural accounting settings when the first relevant stock document is posted, including Initial Receipt/opening balances. Saving a draft does not activate the lock. Locks depend on historical postings, not current balance: zero stock, reversal, or disposal must not unlock settings.

| Setting | Lock trigger |
| --- | --- |
| Cost accounting enabled/disabled | First stock posting in the enterprise |
| Cost valuation method | First stock posting in the enterprise; relevant when cost accounting is enabled |
| Accounting currency | First posted monetary document |
| Address-storage mode | First stock posting in that warehouse |
| Warehouse batch tracking mode | First stock posting in that warehouse; no other setting scope may indirectly change the mode |
| Product base unit | First stock posting for that Product |
| Balance-defining storage analytics: enabled set, value types, requiredness, key semantics | First stock posting in the enterprise |

Adding new values to an existing controlled analytic is allowed if its definition/key semantics stay unchanged. New warehouses and Products can be configured independently before their own first posting. No administrator role bypasses structural locks through normal settings screens or APIs. Any future structural migration is separate from V1 settings editing.

Keep locked values visible, disable editing, and show why (including a reference to the first relevant posted document). Enforce the same locks server-side. Settings changes and first posting must coordinate transactionally so concurrent requests cannot change structural policy during posting.

Settings that remain editable under permissions include enterprise contact/print details, user default warehouse, display decimal places, future document numbering rules, date lock, and future VAT defaults. Preserve historical document snapshots. Batch allocation strategy and expiry requirements may change prospectively, provided referenced stock is eligible and FEFO-required expiry data exists. Negative-stock allowance remains editable only without cost accounting and subject to clearing deficits before disabling. None of these changes reinterpret historical postings.

### 11.11 Settings placement in admin and warehouse applications

The authenticated own-profile endpoint `GET /api/identity/me` returns nullable `first_name`, `last_name`, `display_name`, and `email` from the local ERP user record alongside identity, status, and permissions. Reading these own-profile fields does not require `users.manage`.

Use a single shared backend source for general settings and user profiles. Do not maintain application-specific copies of the same enterprise configuration or user preference.

| Section | Admin application | Warehouse application |
| --- | --- | --- |
| Enterprise | View and edit with permissions | View only |
| Accounting | View and edit with permissions | View only |
| Warehouses (general warehouse settings) | View and edit with permissions | View only |
| Documents (general rules and numbering) | View and edit with permissions | View only |
| My profile / user preferences | View/edit own profile | View/edit own profile |

Group Enterprise, Accounting, Warehouses, and Documents under general settings in the admin application. Provide the same four sections in the warehouse application in read-only mode, with values and explanations but no save/edit actions, including for users who also have administrative permissions. Structural locks from section 11.10 still apply when editing through the admin application.

Warehouse general-settings screens do not define permissions for separate operational warehouse/location directories; directory access remains governed by their module permissions.

Both applications expose the same user's profile/preferences, including the default warehouse. Changes in one application must be reflected when the profile is loaded/refreshed in the other. Editable self-service fields must be explicitly allowlisted; roles, permissions, activation state, and external identity cannot be changed through own-profile editing. Resolve the user from the authenticated identity, not an arbitrary user identifier supplied by the client. User administration in the admin application remains a separate privileged workflow.

Backend read access to general settings uses `settings.read`; general-setting changes use `settings.manage` and applicable resource permissions. UI placement never grants permission, and the backend must enforce write authorization and structural locks independently. Do not trust a client-supplied application name as an authorization boundary. Read-only warehouse screens never issue general-setting mutation requests.

## 12. Permissions and audit

Start with roles such as:

```text
WAREHOUSE_OPERATOR
WAREHOUSE_MANAGER
ADMIN
```

Authorize by permission, not hard-coded role names. Minimum permissions should distinguish:

```text
catalog.read / catalog.create / catalog.edit
inventory.read
inventory.document.create / inventory.document.edit
inventory.document.post / inventory.document.reverse
inventory.adjust
inventory.period.close
warehouse.manage
settings.read / settings.manage
users.manage
```

Posting, reversal, period closing, and adjustments require an audit identity. Preserve who created, edited, posted, cancelled, and reversed a document and when.

## 13. API guidance

Prefer document-oriented endpoints. Examples:

```text
POST   /api/inventory/goods-receipts
PUT    /api/inventory/goods-receipts/{id}
POST   /api/inventory/goods-receipts/{id}/post
POST   /api/inventory/goods-receipts/{id}/cancel
POST   /api/inventory/goods-receipts/{id}/reverse

POST   /api/planning/inbound-orders
POST   /api/planning/inbound-orders/{id}/create-receipt

GET    /api/inventory/movements?sourceDocumentId=...
GET    /api/inventory/balances?productId=...&warehouseId=...
```

Use optimistic versioning for draft edits and idempotency keys for posting, reversal, and document generation from orders. Return domain-specific conflicts rather than leaking database errors.

## 14. Suggested implementation order

Implement vertical slices in this order. Each slice must include domain rules, migrations, repositories, application use cases, API, authorization, audit data, and unit/integration tests before moving on.

### Phase 1 — Foundation and product catalog

1. Project structure, database transaction boundary, IDs, audit fields, authentication skeleton.
2. Product, Category, units, product inventory policy, and the approved master-data directories in section 3.1.
3. Warehouse and Location.
4. Enterprise details for printed documents, accounting currency, optional stock cost accounting, typed settings resolution, and minimal cache.
5. Inventory period model and open-period validation.

### Phase 2 — Receipt and issue vertical slices

1. Common document lifecycle primitives and an internal synchronous, idempotent PostingService inside the monolith.
2. Initial Receipt, including receipt-line batch origins and opening stock.
3. Goods Receipt, including batch, expiry, and enabled storage-analytic rules.
4. Read-only inventory ledger and calculated balance query.
5. Goods Issue, first with explicit batch selection; add FIFO/FEFO allocation only after manual allocation is correct.
6. Concurrency protection and negative-stock integration tests.

This phase is the first complete accounting loop:

```text
Catalog/Product -> Receipt document -> POST -> stock -> Issue document -> POST -> stock
```

### Phase 3 — Transfer and stock control

1. Stock Transfer with atomic OUT/IN pairs.
2. Stock Adjustment with reason codes and stricter permission.
3. Inventory Count producing linked adjustment drafts.
4. Reversal/compensation flows for all posted document types.
5. Monthly closing and reproducible balance snapshots.

### Phase 4 — Planned documents

1. Inbound Order with partial fulfillment and generation of Goods Receipt drafts.
2. Outbound Order with partial fulfillment and generation of Goods Issue drafts.
3. Header/line source links, remaining-quantity rules, idempotent generation, and fulfillment status projections.

### Phase 5 — Hardening

1. Permissions and audit review.
2. Concurrent posting, retry, and idempotency tests.
3. Posting/reversal failure recovery tests.
4. Performance indexes and representative balance queries.
5. API documentation and operational diagnostics.

Do not begin planned orders before receipt, issue, transfer, and ledger rules are correct. Planned documents orchestrate real documents; they must not become an alternate path for changing stock.

## 15. Required tests

At minimum, cover:

- Master-data search and paging work consistently; archived records remain readable in history and cannot be selected for new operations.
- Import validation catches duplicates and row errors and enforces permissions and structural locks.
- Inline creation preserves document drafts, external mappings are scoped uniquely, and master-data edits retain an audit trail.
- Draft documents produce no movements.
- Posting creates the exact expected movements once.
- A retry does not duplicate movements or batches.
- Posted documents cannot be edited or deleted.
- Cancelling a draft produces no movement.
- Reversal creates compensating movements and preserves originals.
- Every movement has valid `source_document` and `source_line` links.
- Warehouse batch tracking `NONE` forbids batches; `BATCH` requires/resolves them. Product/Category overrides cannot change warehouse tracking or allocation strategy.
- Products requiring expiry cannot receive or hold stock in NONE warehouses; enabling that requirement validates existing stock and expiry data.
- Transfers between NONE and BATCH warehouses are rejected atomically in either direction; transfers between BATCH warehouses preserve origin and expiry data.
- Every batch-forming receipt assigns the correct receipt-line origin atomically; supplier lot reuse never merges accounting origins implicitly.
- Issues, transfers, and reversals preserve original receipt-line batch references; mixed expiry/supplier-lot data uses separate receipt lines.
- Batch expiry requirements and FEFO ordering are enforced from typed policy.
- Custom storage analytics validate typed values, split balances consistently, and survive transfer and reversal.
- With no custom analytics and no batch tracking, receipt and issue work with simple Product/Location balances.
- Disabled cost accounting permits quantity-only posting without mandatory cost fields.
- Enabled cost accounting reconciles quantities and stock values through receipts, issues, transfers, adjustments, and reversals.
- Cost-accounting mode changes preserve history and require opening valuation when enabling with existing stock.
- Outgoing posting rejects insufficient stock under concurrency when negative stock is forbidden; enabled quantity-only posting can record explicit deficits without bypassing other invariants.
- Disabling negative stock cannot hide outstanding deficits; cost-accounting mode is locked after first stock posting.
- Cost-accounting posting rejects every negative-stock outcome even if a stored policy override permits negative stock.
- Expired batches cannot be issued normally or allocated automatically; authorized disposal write-offs retain reasons and audit links and never exceed available quantity.
- Address-storage modes preserve totals and user defaults respect warehouse permissions.
- Date locks supplement closed periods; document numbering is unique under concurrent requests.
- VAT inclusive/exclusive calculations reconcile line and document totals and preserve historical rates.
- Unit conversion uses precise base quantities; repeated display-unit changes do not accumulate rounding errors.
- Saving an unchanged rounded display preserves the underlying precise quantity.
- Document posting and reversal preserve base quantities and historical conversion coefficients.
- Structural settings lock after first relevant posting, including Initial Receipt; drafts do not lock them, and zero balances/reversals do not unlock them.
- Structural settings APIs and concurrent first posting enforce the same locks as the UI.
- Transfer creates balanced OUT/IN movements and preserves stock dimensions.
- Inventory count variance becomes an explicit adjustment.
- Planned documents never change physical balances.
- Price Setting posts effective prices idempotently without changing quantities, batches, or stock cost; future dates and conflicting entries are handled explicitly.
- Price corrections retain source links and history, and never alter prices on posted monetary documents.
- Partial inbound/outbound order fulfillment cannot exceed remaining quantity.
- Closed-period documents and movements cannot be mutated.
- Monthly closing balances reconcile with the ledger by `InventoryKey`.
- Current totals, movements, period turnovers, valuation, and document status commit or roll back together; retries never duplicate deltas.
- Concurrent hot-key issues cannot oversell when negatives are forbidden; transfers lock keys deterministically and remain atomic.
- Historical snapshots/boundaries and quantity-only backdated deficit checks are correct; costed backdating restrictions are enforced.
- Projection rebuilding reconciles journals without losing concurrently posted movements.
- Admin general-setting edits enforce permissions/structural locks; warehouse general-setting screens are read-only.
- Both applications read/write the same own-profile preferences; self-service profile changes cannot modify privileges or another user.
- Synchronous posting returns success only after commit; retries after a lost response return the recorded result without duplicate movements.
- Concurrent HTTP posting uses the same locks and idempotency guarantees as all other application entry points.

## 16. Non-goals for V1

Unless separately requested, do not implement:

- microservices or separate databases per module;
- RabbitMQ/outbox posting queues, separately deployed posting workers (deferred to V2), distributed Saga, or distributed transactions;
- full Event Sourcing;
- a universal workflow/rules engine;
- arbitrary executable business rules or unvalidated user-defined stock dimensions;
- serial-number tracking;
- multi-organization operation, packaging conversions, and statutory VAT reporting;
- reservations, picking, packing, shipping, payments, forecasting, or procurement automation;
- silent direct stock corrections.

Keep extension points explicit so later iterations can add `Sales Order -> Reservation -> Picking -> Goods Issue -> Shipment`, internal domain events, broader integrations, further service extraction, Saga, and read projections without weakening the document/ledger invariants.

## 17. Definition of done

Warehouse ERP V1 is acceptable only when:

- users can maintain Product catalog data and the approved master-data directories with the shared behavior in sections 3.1–3.2;
- warehouses and locations exist;
- initial receipt, goods receipt, goods issue, transfer, adjustment, and inventory count flows work through documents;
- batch-forming inbound posting works for Products received into BATCH warehouses;
- inbound and outbound orders can generate linked real documents without directly changing stock;
- all stock changes are traceable from movement to source document and source line;
- lifecycle, posting, reversal, closed-period, batch, and concurrency invariants are enforced in domain/application code and the database where possible;
- current and monthly balances reconcile with the immutable movement ledger;
- the core behavior is protected by automated tests.
