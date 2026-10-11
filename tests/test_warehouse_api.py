from uuid import UUID

from fastapi.testclient import TestClient

from warehouse_erp.identity.api.dependencies import get_current_user
from warehouse_erp.identity.domain.entities import (
    CurrentUser,
    PermissionGrant,
    ScopeType,
    UserStatus,
)
from warehouse_erp.warehouse.permissions import WarehousePermission


def _warehouse(client: TestClient, code: str) -> dict:
    response = client.post(
        "/api/warehouses",
        json={
            "code": code,
            "name": f"Warehouse {code}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _location(
    client: TestClient, warehouse_id: str, code: str, parent_id: str | None = None
) -> dict:
    response = client.post(
        f"/api/warehouses/{warehouse_id}/locations",
        json={
            "code": code,
            "name": code,
            "kind": "ZONE" if parent_id is None else "BIN",
            "parent_id": parent_id,
            "allows_stock": parent_id is not None,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_warehouse_location_tree_and_lifecycle(client: TestClient) -> None:
    first = _warehouse(client, "main")
    second = _warehouse(client, "reserve")
    assert first["code"] == "MAIN"
    root = _location(client, first["id"], "A")
    child = _location(client, first["id"], "A-01", root["id"])
    assert [
        item["id"]
        for item in client.get(f"/api/warehouses/{first['id']}/locations?root_only=true").json()
    ] == [root["id"]]
    assert [
        item["id"]
        for item in client.get(
            f"/api/warehouses/{first['id']}/locations?parent_id={root['id']}"
        ).json()
    ] == [child["id"]]
    cycle = client.patch(f"/api/locations/{root['id']}", json={"parent_id": child["id"]})
    assert cycle.status_code == 422
    assert "cycle" in cycle.json()["detail"]
    other_root = _location(client, second["id"], "A")
    cross = client.patch(
        f"/api/locations/{child['id']}",
        json={
            "parent_id": other_root["id"],
        },
    )
    assert cross.status_code == 422
    duplicate = client.post(
        f"/api/warehouses/{first['id']}/locations",
        json={
            "code": "A",
            "name": "Duplicate",
            "kind": "ZONE",
        },
    )
    assert duplicate.status_code == 409
    blocked = client.patch(f"/api/warehouses/{first['id']}", json={"active": False})
    assert blocked.status_code == 422
    blocked_parent = client.patch(f"/api/locations/{root['id']}", json={"active": False})
    assert blocked_parent.status_code == 422
    assert client.patch(f"/api/locations/{child['id']}", json={"active": False}).status_code == 200
    assert client.patch(f"/api/locations/{root['id']}", json={"active": False}).status_code == 200
    assert client.patch(f"/api/warehouses/{first['id']}", json={"active": False}).status_code == 200
    rejected = client.post(
        f"/api/warehouses/{first['id']}/locations",
        json={
            "code": "new",
            "name": "New",
            "kind": "BIN",
        },
    )
    assert rejected.status_code == 422


def test_warehouse_scoped_permissions_filter_reads_and_writes(client: TestClient) -> None:
    first = _warehouse(client, "main")
    second = _warehouse(client, "reserve")
    first_id = UUID(first["id"])
    grants = tuple(
        PermissionGrant(
            permission_code=permission.value,
            role_id=UUID("00000000-0000-0000-0000-000000000020"),
            scope_type=ScopeType.WAREHOUSE,
            scope_id=first_id,
        )
        for permission in (WarehousePermission.READ, WarehousePermission.MANAGE)
    )
    client.app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        subject="auth0|scoped",
        status=UserStatus.ACTIVE,
        grants=grants,
    )
    listed = client.get("/api/warehouses")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [first["id"]]
    assert client.get(f"/api/warehouses/{first['id']}").status_code == 200
    assert client.get(f"/api/warehouses/{second['id']}").status_code == 403
    assert (
        client.post("/api/warehouses", json={"code": "third", "name": "Third"}).status_code == 403
    )
    assert (
        client.post(
            f"/api/warehouses/{first['id']}/locations",
            json={
                "code": "A",
                "name": "A",
                "kind": "ZONE",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/warehouses/{second['id']}/locations",
            json={
                "code": "A",
                "name": "A",
                "kind": "ZONE",
            },
        ).status_code
        == 403
    )


def test_warehouse_inventory_policy_create_patch_and_validation(client: TestClient) -> None:
    result = client.post(
        "/api/warehouses",
        json={
            "code": "batches",
            "name": "Batches",
            "tracking_mode": "BATCH",
            "issue_strategy": "FEFO",
        },
    )
    assert result.status_code == 201, result.text
    warehouse_id = result.json()["id"]
    assert client.get(f"/api/warehouses/{warehouse_id}").json()["issue_strategy"] == "FEFO"
    invalid = client.patch(f"/api/warehouses/{warehouse_id}", json={"tracking_mode": "NONE"})
    assert invalid.status_code == 422
    assert client.get(f"/api/warehouses/{warehouse_id}").json()["tracking_mode"] == "BATCH"
    for payload in ({"issue_strategy": None}, {"tracking_mode": None}, {"issue_strategy": "LIFO"}):
        assert client.patch(f"/api/warehouses/{warehouse_id}", json=payload).status_code == 422
    changed = client.patch(
        f"/api/warehouses/{warehouse_id}",
        json={
            "tracking_mode": "NONE",
            "issue_strategy": "MANUAL",
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["tracking_mode"] == "NONE"


def test_inventory_policy_edit_requires_settings_permission(client: TestClient) -> None:
    item = _warehouse(client, "permissions")
    client.app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        subject="auth0|test-user",
        status=UserStatus.ACTIVE,
        grants=(
            PermissionGrant(
                permission_code=WarehousePermission.MANAGE,
                role_id=UUID(item["id"]),
                scope_type=ScopeType.GLOBAL,
                scope_id=None,
            ),
        ),
    )
    assert (
        client.patch(f"/api/warehouses/{item['id']}", json={"name": "Renamed"}).status_code == 200
    )
    assert (
        client.patch(f"/api/warehouses/{item['id']}", json={"tracking_mode": "BATCH"}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/warehouses",
            json={
                "code": "denied",
                "name": "Denied",
                "tracking_mode": "BATCH",
            },
        ).status_code
        == 403
    )
