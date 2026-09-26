# Identity and access management

This module owns local ERP users, the permission registry, roles, and role assignments. Auth0
remains the authentication provider: it proves who the caller is, while this module evaluates the
permissions contributed by business modules.

## Login and approval flow

1. Angular obtains an Auth0 access token for audience `https://api.warehouse-erp`.
2. The backend validates its signature, issuer, audience, lifetime, algorithm, and `sub` claim.
3. `GET /api/identity/me` resolves `sub` to a local user. An unknown identity is created as
   `PENDING_APPROVAL` with no permissions.
4. An administrator links or reviews the local user, assigns one or more roles, then activates it.
5. `ACTIVE` users may call endpoints allowed by their effective permissions. Pending, invited, and
   suspended users are denied protected business operations.

There is no automatic email-based account linking. An administrator explicitly links an invited
local user to an Auth0 `sub`, avoiding accidental account takeover when email data changes.

User states are `INVITED`, `PENDING_APPROVAL`, `ACTIVE`, and `SUSPENDED`.

## Authorization model

- Permissions are stable application codes such as `catalog.read`, `catalog.create`,
  `catalog.edit`, and `users.manage`.
- Roles group permissions. The migration creates `WAREHOUSE_OPERATOR`, `WAREHOUSE_MANAGER`, and
  `ADMIN` system roles.
- A role assignment belongs to a user and a scope: `GLOBAL`, `COMPANY`, or `WAREHOUSE`.
- Global grants apply everywhere. Company and warehouse scopes are ready for later modules and
  require a `scope_id`.
- Effective permissions are read from the database for every request; Auth0 token permissions are
  intentionally not used as ERP authorization data.

### Extending permissions from another module

Permission definitions belong to the module that implements the protected operation. For example,
catalog codes live in `catalog/permissions.py`, identity codes in `identity/permissions.py`, and
inventory codes in `inventory/permissions.py`. The application composition root
`warehouse_erp/permission_catalog.py` combines those declarations and validates uniqueness and
system-role references.

When adding a module such as manufacturing:

1. add `manufacturing/permissions.py` with stable namespaced codes;
2. use its constants in `require_permission(...)` checks;
3. include its definitions in `permission_catalog.py`;
4. add a manufacturing-owned Alembic migration that inserts the permission rows and grants them
   to `ADMIN` when appropriate.

The identity domain, service, repository, and API do not change. Historical migrations remain
frozen; permissions are versioned by the migration of the module that introduces them. Arbitrary
permission creation is intentionally not exposed because a permission has meaning only when code
enforces it. Administrators remain free to create roles from all registered permissions.

## Administrative API

All management endpoints require the `users.manage` permission:

- `GET/POST /api/identity/users`
- `GET/PATCH /api/identity/users/{user_id}`
- `PUT /api/identity/users/{user_id}/auth0`
- `POST /api/identity/users/{user_id}/activate`
- `POST /api/identity/users/{user_id}/suspend`
- `GET /api/identity/permissions`
- `GET/POST /api/identity/roles`
- `GET/PATCH /api/identity/roles/{role_id}`
- `GET/PUT /api/identity/roles/{role_id}/permissions`
- `GET/POST /api/identity/users/{user_id}/role-assignments`
- `DELETE /api/identity/users/{user_id}/role-assignments/{assignment_id}`

`GET /api/identity/me` requires only a valid access token and returns the local status and effective
permission codes. This is the endpoint the frontend should call immediately after login.

## First administrator

Run migrations, log in to Auth0 once, copy the token's exact `sub` value (or read it from the
pending local user), and bootstrap the first administrator:

```bash
python -m warehouse_erp.identity.bootstrap_admin \
  --auth0-sub 'auth0|USER_ID' \
  --email admin@example.com \
  --display-name 'ERP administrator'
```

The command is idempotent: it activates the user and ensures a global `ADMIN` assignment. It must
be run in a trusted local or deployment environment and does not call the Auth0 Management API.

## Package structure

- `api/` — HTTP schemas, routes, authentication and permission dependencies;
- `application/` — use cases and Auth0 verification ports;
- `domain/` — entities, invariants, and repository contracts;
- `permissions.py` — permission codes implemented by the identity module itself;
- `infrastructure/` — Auth0 JWT verification and SQLAlchemy persistence.

Database changes belong in Alembic migrations. Keep business rules out of API and SQLAlchemy
models so the module can later be extracted into a service without rewriting its core logic.
