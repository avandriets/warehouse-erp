# Warehouse ERP development rules

## Architecture

- V1 is a modular monolith with one backend deployment and MariaDB. Post documents synchronously through an internal application service. RabbitMQ and a separately deployed Posting Service are deferred to V2; do not implement that infrastructure for V1.
- Within every module preserve `API -> Application -> Domain`; Infrastructure implements ports.
- Domain code must not import FastAPI, SQLAlchemy, HTTP, or database-specific types.
- Implement work as tested vertical slices, not empty framework layers.

## Catalog

- `Product` is the single catalog and inventory-accounting item; do not introduce a separate SKU
  entity without a demonstrated variant requirement.
- Categories form an adjacency-list tree through `parent_id`; prevent hierarchy cycles.
- Existing catalog records are deactivated, not destructively deleted.
- Inventory policies are typed. `FEFO` and `expiry_required` require `BATCH` tracking.
- Treat codes as stable identifiers. Do not add code-changing endpoints without a migration/audit policy.

## Future inventory work

- No inventory movement without a posted source document.
- Stock-changing requests call the internal PostingService; commit movements, totals, valuation, and result together before returning success. Persist idempotency so retries after a lost response cannot repost a document.
- Do not expose create/update/delete APIs for inventory movements.
- Posted documents and ledger movements are immutable; corrections use explicit reversals.
- Every movement must reference its source document, source line, and catalog product.
- Planned orders do not affect stock; they generate real stock documents.
- Receipt-like documents form accounting batches through their posted receipt-line origins when batch tracking is enabled; there is no standalone manually maintained Batch directory. Transfers and reversals preserve the original receipt-line batch reference.
- Current stock is read from rebuildable totals maintained atomically with document movements; the immutable ledger remains authoritative. Use period snapshots plus interval movements for historical balances. Never edit totals directly. See docs/specs/warehouse.md section 10.
- Negative stock is forbidden by default and may be enabled through the resolved inventory policy; enforce the setting under concurrency without bypassing other posting invariants.
- Cost accounting always forbids negative stock, overriding all inventory settings; the cost-accounting mode is chosen before first stock posting and locked afterward. No provisional negative-stock costing is required in V1.
- Exclude expired batches from normal issue and automatic allocation; disposal requires an explicit authorized write-off with a reason.

## Settings and warehouses

- General Enterprise/Accounting/Warehouses/Documents settings are editable in the admin app and read-only in the warehouse app. Both apps use the same own-user profile/preferences. Enforce backend permissions and structural locks independently of UI placement; see specification section 11.11.
- Resolve settings to typed snapshots; domain code must not fetch arbitrary string keys.
- Scoped setting precedence is Product, Category, Warehouse, Company, Global, then default.
- Resolve a posting policy once per transaction; do not change its meaning mid-posting.
- Lock structural accounting settings after first relevant posting, including opening balances; enforce locks in the API and under concurrency. Drafts do not lock settings, and reversals or zero stock do not unlock them. See docs/specs/warehouse.md section 11.10.
- Warehouse locations use an adjacency-list tree; reject cycles and cross-warehouse parents.
- Keep warehouse/location master data separate from inventory balances and movements.

## Quality gates

- Add domain and API/integration tests for every behavior.
- Run `pytest` before handing off changes.
- Add Alembic migrations for persistent model changes.
- Use MariaDB for development and testing. Integration tests must use an isolated test database;
  never run test schema creation or teardown against the application database.
- Keep database-specific behavior out of domain and application code.

## Specifications

- Project specifications live in `docs/specs/`; start with `docs/specs/README.md`.
- Before changing functionality, read the relevant specification.
- Record agreed requirement changes in the corresponding specification and update the index when adding documents.
- Keep stable filenames; use Git for version history.
- Keep specifications consistent with the repository rules above; flag any newly discovered discrepancy for reconciliation.
