from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from warehouse_erp.database import get_db_session
from warehouse_erp.identity.api.dependencies import get_current_identity, get_current_user
from warehouse_erp.identity.application.errors import (
    AuthenticationNotConfiguredError,
    InvalidAccessTokenError,
)
from warehouse_erp.identity.domain.entities import AuthenticatedIdentity, CurrentUser, UserStatus
from warehouse_erp.identity.infrastructure.auth0 import Auth0AccessTokenVerifier
from warehouse_erp.main import create_app

ISSUER = "https://tenant.example.auth0.com/"
AUDIENCE = "https://api.warehouse-erp"


class StaticSigningKeys:
    def __init__(self, public_key: object) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, _: str) -> object:
        return SimpleNamespace(key=self.public_key)


def _token(*, audience: str = AUDIENCE) -> tuple[str, object]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "sub": "auth0|test-user",
            "aud": audience,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "scope": "openid profile",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    return token, private_key.public_key()


def test_identity_endpoint_requires_bearer_token() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/identity/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_catalog_requires_bearer_token() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/catalog/categories")

    assert response.status_code == 401


def test_cors_allows_local_angular_application() -> None:
    with TestClient(create_app()) as client:
        response = client.options(
            "/api/identity/me",
            headers={
                "Origin": "http://localhost:4300",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:4300"


def test_identity_endpoint_returns_overridden_identity(client: TestClient) -> None:
    response = client.get("/api/identity/me")

    assert response.status_code == 200
    body = response.json()
    assert body["subject"] == "auth0|test-user"
    assert body["status"] == "ACTIVE"
    assert "users.manage" in body["permissions"]


def test_first_login_creates_pending_user(
    session_factory: sessionmaker[Session],
) -> None:
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
        subject="auth0|new-user"
    )

    with TestClient(app) as test_client:
        me = test_client.get("/api/identity/me")
        catalog = test_client.get("/api/catalog/categories")

    assert me.status_code == 200
    assert me.json()["status"] == "PENDING_APPROVAL"
    assert me.json()["permissions"] == []
    assert catalog.status_code == 403
    assert catalog.json()["detail"] == "User is waiting for administrator approval"


def test_admin_can_manage_users_roles_and_assignments(client: TestClient) -> None:
    user_response = client.post(
        "/api/identity/users",
        json={"email": "worker@example.com", "display_name": "Worker"},
    )
    assert user_response.status_code == 201
    user_id = user_response.json()["id"]

    linked = client.put(
        f"/api/identity/users/{user_id}/auth0",
        json={"auth0_subject": "auth0|worker"},
    )
    assert linked.status_code == 200

    activated = client.post(f"/api/identity/users/{user_id}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"

    roles = client.get("/api/identity/roles")
    operator = next(role for role in roles.json() if role["code"] == "WAREHOUSE_OPERATOR")
    assignment = client.post(
        f"/api/identity/users/{user_id}/role-assignments",
        json={"role_id": operator["id"], "scope_type": "GLOBAL"},
    )
    assert assignment.status_code == 201


def test_active_user_without_permission_cannot_manage_roles() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        subject="auth0|ordinary-user",
        status=UserStatus.ACTIVE,
    )

    with TestClient(app) as test_client:
        response = test_client.get("/api/identity/roles")

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission required: users.manage"


def test_auth0_verifier_accepts_valid_token() -> None:
    token, public_key = _token()
    verifier = Auth0AccessTokenVerifier(
        domain="tenant.example.auth0.com",
        audience=AUDIENCE,
        signing_keys=StaticSigningKeys(public_key),
    )

    identity = verifier.verify(token)

    assert identity.subject == "auth0|test-user"
    assert identity.scopes == frozenset({"openid", "profile"})


def test_auth0_verifier_rejects_wrong_audience() -> None:
    token, public_key = _token(audience="https://another-api")
    verifier = Auth0AccessTokenVerifier(
        domain="tenant.example.auth0.com",
        audience=AUDIENCE,
        signing_keys=StaticSigningKeys(public_key),
    )

    with pytest.raises(InvalidAccessTokenError):
        verifier.verify(token)


def test_auth0_verifier_requires_configuration() -> None:
    verifier = Auth0AccessTokenVerifier(domain=None, audience=None)

    with pytest.raises(AuthenticationNotConfiguredError):
        verifier.verify("token")
