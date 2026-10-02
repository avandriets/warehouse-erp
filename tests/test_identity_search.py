import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def searchable_users(client: TestClient) -> list[dict]:
    users = []
    for email, name in [
        ("unrelated@example.test", "Unrelated"),
        ("first@example.test", "Needle Alpha"),
        ("needle@example.test", "Beta"),
        ("literal@example.test", "Literal %_/ Name"),
    ]:
        first_name, _, last_name = name.partition(" ")
        response = client.post(
            "/api/identity/users",
            json={"email": email, "first_name": first_name, "last_name": last_name or None},
        )
        assert response.status_code == 201
        users.append(response.json())
    return users


def test_user_search_matches_name_and_email_before_pagination(
    client: TestClient, searchable_users: list[dict]
) -> None:
    matching_ids = {user["id"] for user in searchable_users[1:3]}
    expected_users = [
        user
        for user in client.get("/api/identity/users").json()["items"]
        if user["id"] in matching_ids
    ]
    for offset, expected in enumerate(expected_users):
        response = client.get(
            "/api/identity/users", params={"q": "  nEeDlE  ", "limit": 1, "offset": offset}
        )
        assert response.status_code == 200
        assert response.json()["total"] == len(expected_users)
        assert [user["id"] for user in response.json()["items"]] == [expected["id"]]


def test_user_search_combines_status_filter(
    client: TestClient, searchable_users: list[dict]
) -> None:
    response = client.get("/api/identity/users", params={"q": "needle", "status": "ACTIVE"})
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}
    response = client.get("/api/identity/users", params={"q": "needle", "status": "INVITED"})
    assert {user["id"] for user in response.json()["items"]} == {
        user["id"] for user in searchable_users[1:3]
    }


@pytest.mark.parametrize("q", ["%", "_", "/", "%_/"])
def test_user_search_treats_wildcards_literally(
    client: TestClient, searchable_users: list[dict], q: str
) -> None:
    response = client.get("/api/identity/users", params={"q": q})
    assert response.status_code == 200
    assert [user["id"] for user in response.json()["items"]] == [searchable_users[3]["id"]]


@pytest.fixture
def searchable_roles(client: TestClient) -> list[dict]:
    roles = []
    for code, name in [("SEARCH_ALPHA", "First"), ("SECOND", "Search beta %_/")]:
        response = client.post("/api/identity/roles", json={"code": code, "name": name})
        assert response.status_code == 201
        roles.append(response.json())
    response = client.patch(
        f"/api/identity/roles/{roles[1]['id']}",
        json={"name": roles[1]["name"], "active": False},
    )
    assert response.status_code == 200
    return roles


def test_role_search_matches_code_and_name_with_active_filter(
    client: TestClient, searchable_roles: list[dict]
) -> None:
    response = client.get("/api/identity/roles", params={"q": "  sEaRcH  "})
    assert response.status_code == 200
    assert {role["id"] for role in response.json()} == {role["id"] for role in searchable_roles}
    for active, expected in [("true", searchable_roles[0]), ("false", searchable_roles[1])]:
        response = client.get("/api/identity/roles", params={"q": "search", "active": active})
        assert [role["id"] for role in response.json()] == [expected["id"]]


@pytest.mark.parametrize("q", ["%", "/", "%_/"])
def test_role_search_treats_wildcards_literally(
    client: TestClient, searchable_roles: list[dict], q: str
) -> None:
    response = client.get("/api/identity/roles", params={"q": q})
    assert response.status_code == 200
    assert [role["id"] for role in response.json()] == [searchable_roles[1]["id"]]


@pytest.mark.parametrize("resource", ["users", "roles"])
def test_search_empty_missing_and_no_matches(client: TestClient, resource: str) -> None:
    path = f"/api/identity/{resource}"
    original = client.get(path)
    assert original.status_code == 200
    for q in ["", "   "]:
        assert client.get(path, params={"q": q}).json() == original.json()
    response = client.get(path, params={"q": "does-not-exist-xyz"})
    assert response.status_code == 200
    expected = {"items": [], "total": 0} if resource == "users" else []
    assert response.json() == expected
    assert client.get(path, params={"q": "a" * 256}).status_code == 422
