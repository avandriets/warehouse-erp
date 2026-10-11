from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from warehouse_erp.identity.api.dependencies import get_current_user
from warehouse_erp.identity.application.service import IdentityService
from warehouse_erp.identity.domain.entities import AuthenticatedIdentity, User, UserStatus
from warehouse_erp.main import create_app


@pytest.mark.parametrize("named", [True, False])
def test_own_profile_returns_local_names_without_administrative_permissions(named: bool) -> None:
    user = User(
        status=UserStatus.ACTIVE,
        auth0_subject="auth0|employee",
        first_name="Ada" if named else None,
        last_name="Lovelace" if named else None,
        email="ada@example.test" if named else None,
    )
    uow = Mock()
    uow.identity.get_user_by_subject.return_value = user
    uow.identity.list_grants.return_value = []
    current = IdentityService(uow).resolve_current_user(
        AuthenticatedIdentity(subject="auth0|employee")
    )
    assert current.first_name == user.first_name
    assert current.last_name == user.last_name
    assert current.display_name == user.display_name
    assert current.email == user.email
    uow.identity.get_user_by_subject.assert_called_once_with("auth0|employee")
    uow.commit.assert_not_called()

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: current
    with TestClient(app) as client:
        response = client.get("/api/identity/me")
    assert response.status_code == 200
    assert response.json() == {
        "default_warehouse_id": None,
        "user_id": str(user.id),
        "subject": "auth0|employee",
        "status": "ACTIVE",
        "permissions": [],
        "first_name": "Ada" if named else None,
        "last_name": "Lovelace" if named else None,
        "display_name": "Ada Lovelace" if named else None,
        "email": "ada@example.test" if named else None,
    }
