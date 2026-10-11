# Warehouse ERP

Document-oriented Warehouse ERP backend built as a FastAPI modular monolith.

The first vertical slice implements the product catalog:

- categories;
- units of measure;
- dimensional unit conversions, nested reusable/product-specific package sets, package barcodes,
  and product-specific measurements;
- hierarchical categories;
- products as the single inventory-accounting item;
- typed product inventory policy (`NONE`/`BATCH`, `MANUAL`/`FIFO`/`FEFO`);
- deactivation instead of destructive deletion;
- Alembic migrations and MariaDB-backed integration tests.

Detailed module documentation: [`src/warehouse_erp/catalog/README.md`](src/warehouse_erp/catalog/README.md).

The foundation also includes [typed scoped settings](src/warehouse_erp/settings/README.md)
and [warehouses with hierarchical locations](src/warehouse_erp/warehouse/README.md).

## Architecture

Each module follows this dependency direction:

```text
API -> Application -> Domain
          ^             ^
          |             |
      Infrastructure implements ports
```

The domain and application layers do not import FastAPI or SQLAlchemy. Future inventory modules must preserve the ERP invariant: no inventory movement without a posted source document.

Each business module owns its stable permission declarations. Identity provides the generic
authorization engine but does not enumerate other modules' capabilities. The application-level
catalog in `warehouse_erp/permission_catalog.py` composes module permissions and default roles;
new modules register their permissions with their own Alembic migration.

## Run locally

The application uses an existing MariaDB server. Docker is not required.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
alembic upgrade head
python -m warehouse_erp.run
```

The same setup is available through Make:

```bash
make init
make migrate
make run
```

OpenAPI is available at <http://127.0.0.1:8100/docs> and health status at
<http://127.0.0.1:8100/health>. `APP_HOST` and `APP_PORT` configure the bind address and port.

`APP_DATABASE_URL` is required and must use the `mariadb+pymysql://` SQLAlchemy URL.
Configure it in `.env` before running migrations or the API.

Database connections are checked before reuse (`pool_pre_ping`) and recycled after 300 seconds.
`APP_DB_POOL_RECYCLE_SECONDS`, `APP_DB_POOL_TIMEOUT_SECONDS`,
`APP_DB_CONNECT_TIMEOUT_SECONDS`, `APP_DB_READ_TIMEOUT_SECONDS`, and
`APP_DB_WRITE_TIMEOUT_SECONDS` configure positive timeouts in seconds; defaults are
300/10/10/45/45 respectively. Set recycle below the server/network idle limit when known.
Unavailable connections and exhausted pools return HTTP 503 with a generic message.
Connection checks cannot prevent a disconnect during an active transaction; the API does not
automatically replay writes after an uncertain commit. `/health` reports process liveness only.

## Authentication

Auth0 authenticates API callers. Configure `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` in `.env`;
the backend validates bearer access tokens locally with the tenant JWKS, issuer, audience,
expiration, and the `RS256` algorithm. The health endpoint remains public. Catalog endpoints and
`GET /api/identity/me` require an access token.

Auth0 stores external login identities only. ERP users, roles, scoped permissions, and audit
identity are stored in the local identity module rather than in Auth0 access-token permissions.
On first login an unknown identity becomes `PENDING_APPROVAL` and has no business access until an
administrator activates it and assigns roles. See the
[identity module documentation](src/warehouse_erp/identity/README.md).
The local Angular origin is `http://localhost:4300` and is allowed through CORS.

## Tests

```bash
make check
```

Database-backed tests require `TEST_DATABASE_URL` for a dedicated, empty MariaDB database whose
name ends in `_test`. Both integration and migration tests use this one database sequentially;
the test runner refuses to use the application database. Create the database and grant access to
an existing `warehouse_app_test_user` by running `scripts/create_test_database.sql` in the MariaDB
console as an administrator. Then configure `TEST_DATABASE_URL` in `.env` and run `make check`.
The test suite creates and removes tables in this database; do not keep valuable data there or run
database tests in parallel. Without the variable, database-backed tests are skipped; pure
domain/auth tests still run.

## API

The catalog API is mounted under `/api/catalog`:

- `POST/GET/PATCH /categories`
- `POST/GET/PATCH /units`
- `POST/GET/PATCH /products`
- `POST/GET/PATCH /package-sets` and their nested `/packages`
- product `/measurements`, `/barcodes`, and `/convert`
- unit `/convert`

Settings management is under `/api/settings`; warehouse and location endpoints are under
`/api/warehouses` and `/api/locations`. The settings and warehouse READMEs describe their
authorization and resolution rules.

After migration, optional starter units can be inserted idempotently with
`.venv/bin/python -m warehouse_erp.catalog.seed_units`.

List endpoints accept `limit`, `offset`, and `active`. Product lists also support category filters;
category lists support parent and root filters.

Persisted enterprise/accounting settings, document numbering rules and reference directories
are described in [the configuration API contract](src/warehouse_erp/configuration/README.md).
