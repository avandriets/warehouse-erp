# Warehouse ERP development rules

## Architecture

- Keep the application a modular monolith until a demonstrated requirement justifies extraction.
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
- Do not expose create/update/delete APIs for inventory movements.
- Posted documents and ledger movements are immutable; corrections use explicit reversals.
- Every movement must reference its source document, source line, and catalog product.
- Planned orders do not affect stock; they generate real stock documents.
- Receipt-like documents create or resolve batches when the product uses batch tracking.
- Current stock is derived from the ledger and period balances, never silently overwritten.

## Settings and warehouses

- Resolve settings to typed snapshots; domain code must not fetch arbitrary string keys.
- Scoped setting precedence is Product, Category, Warehouse, Company, Global, then default.
- Resolve a posting policy once per transaction; do not change its meaning mid-posting.
- Warehouse locations use an adjacency-list tree; reject cycles and cross-warehouse parents.
- Keep warehouse/location master data separate from inventory balances and movements.

## Quality gates

- Add domain and API/integration tests for every behavior.
- Run `pytest` before handing off changes.
- Add Alembic migrations for persistent model changes.
- Use MariaDB for development and testing. Integration tests must use an isolated test database;
  never run test schema creation or teardown against the application database.
- Keep database-specific behavior out of domain and application code.
