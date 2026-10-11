from uuid import uuid4

from fastapi.testclient import TestClient


def _definition(
    client: TestClient,
    *,
    key: str,
    value_type: str,
    default_value: object,
    options: list[str] | None = None,
) -> dict:
    category = client.get("/api/settings/categories").json()[0]
    response = client.post(
        "/api/settings/definitions",
        json={
            "category_id": category["id"],
            "key": key,
            "name": "Test setting",
            "value_type": value_type,
            "default_value": default_value,
            "allowed_scopes": ["GLOBAL", "COMPANY", "WAREHOUSE", "CATEGORY", "PRODUCT"],
            "options": options or [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _scopes(client: TestClient) -> tuple[str, str, str]:
    warehouse = client.post(
        "/api/warehouses",
        json={
            "code": "main",
            "name": "Main warehouse",
        },
    )
    assert warehouse.status_code == 201, warehouse.text
    category = client.post(
        "/api/catalog/categories",
        json={
            "code": "goods",
            "name": "Goods",
        },
    )
    assert category.status_code == 201, category.text
    unit = client.post(
        "/api/catalog/units",
        json={
            "code": "pcs",
            "name": "Pieces",
            "symbol": "pcs",
            "dimension": "COUNT",
            "precision": 0,
        },
    )
    assert unit.status_code == 201, unit.text
    product = client.post(
        "/api/catalog/products",
        json={
            "code": "bolt",
            "name": "Bolt",
            "category_id": category.json()["id"],
            "storage_unit_id": unit.json()["id"],
        },
    )
    assert product.status_code == 201, product.text
    return warehouse.json()["id"], category.json()["id"], product.json()["id"]


def test_settings_type_validation_scope_precedence_and_versions(client: TestClient) -> None:
    _definition(client, key="custom.reorder_point", value_type="INTEGER", default_value=10)
    warehouse_id, category_id, product_id = _scopes(client)
    base = client.get("/api/settings/resolve/custom.reorder_point")
    assert base.status_code == 200
    assert base.json()["value"] == 10
    assert base.json()["source_scope"] is None

    global_value = client.put(
        "/api/settings/definitions/custom.reorder_point/values",
        json={
            "scope_type": "GLOBAL",
            "value": 20,
        },
    )
    assert global_value.status_code == 200, global_value.text
    assert global_value.json()["version"] == 1
    invalid = client.put(
        "/api/settings/definitions/custom.reorder_point/values",
        json={
            "scope_type": "PRODUCT",
            "scope_id": product_id,
            "value": True,
        },
    )
    assert invalid.status_code == 422
    warehouse = client.put(
        "/api/settings/definitions/custom.reorder_point/values",
        json={
            "scope_type": "WAREHOUSE",
            "scope_id": warehouse_id,
            "value": 30,
        },
    )
    assert warehouse.status_code == 200, warehouse.text
    category = client.put(
        "/api/settings/definitions/custom.reorder_point/values",
        json={
            "scope_type": "CATEGORY",
            "scope_id": category_id,
            "value": 40,
        },
    )
    assert category.status_code == 200
    product = client.put(
        "/api/settings/definitions/custom.reorder_point/values",
        json={
            "scope_type": "PRODUCT",
            "scope_id": product_id,
            "value": 50,
        },
    )
    assert product.status_code == 200

    path = (
        "/api/settings/resolve/custom.reorder_point"
        f"?warehouse_id={warehouse_id}&category_id={category_id}&product_id={product_id}"
    )
    resolved = client.get(path)
    assert resolved.json()["value"] == 50
    assert resolved.json()["source_scope"] == "PRODUCT"
    assert (
        client.get(
            "/api/settings/resolve/custom.reorder_point"
            f"?warehouse_id={warehouse_id}&category_id={category_id}"
        ).json()["value"]
        == 40
    )
    stale = client.put(
        "/api/settings/definitions/custom.reorder_point/values",
        json={
            "scope_type": "PRODUCT",
            "scope_id": product_id,
            "value": 60,
            "expected_version": 2,
        },
    )
    assert stale.status_code == 409
    changed = client.put(
        "/api/settings/definitions/custom.reorder_point/values",
        json={
            "scope_type": "PRODUCT",
            "scope_id": product_id,
            "value": 60,
            "expected_version": 1,
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert client.get(path).json()["value"] == 60
    auto_category = client.get(
        "/api/settings/resolve/custom.reorder_point"
        f"?warehouse_id={warehouse_id}&product_id={product_id}"
    )
    assert auto_category.json()["value"] == 60
    missing_target = client.put(
        "/api/settings/definitions/custom.reorder_point/values",
        json={"scope_type": "WAREHOUSE", "scope_id": str(uuid4()), "value": 80},
    )
    assert missing_target.status_code == 404


def test_typed_inventory_snapshot_uses_warehouse_and_invalidates_changes(
    client: TestClient,
) -> None:
    warehouse_id, _, product_id = _scopes(client)
    path = f"/api/settings/inventory-defaults?warehouse_id={warehouse_id}&product_id={product_id}"
    initial = client.get(path)
    assert initial.status_code == 200, initial.text
    assert initial.json()["tracking_mode"] == "NONE"
    assert initial.json()["issue_strategy"] is None
    assert initial.json()["negative_stock_allowed"] is False
    changed = client.patch(
        f"/api/warehouses/{warehouse_id}",
        json={
            "tracking_mode": "BATCH",
            "issue_strategy": "FIFO",
        },
    )
    assert changed.status_code == 200, changed.text
    assert client.get(path).json()["issue_strategy"] == "FIFO"
    updated = client.put(
        "/api/settings/definitions/inventory.negative_stock_allowed/values",
        json={"scope_type": "GLOBAL", "value": True},
    )
    assert updated.status_code == 200, updated.text
    assert client.get(path).json()["negative_stock_allowed"] is True
    assert client.get("/api/settings/inventory-defaults").json()["issue_strategy"] is None
    assert (
        client.get("/api/settings/definitions/inventory.default_issue_strategy").status_code == 404
    )


def test_product_expiry_and_warehouse_compatibility_is_checked(client: TestClient) -> None:
    warehouse_id, _, product_id = _scopes(client)
    path = f"/api/settings/inventory-defaults?warehouse_id={warehouse_id}&product_id={product_id}"
    assert client.get(path).status_code == 200  # populate cache
    result = client.patch(
        f"/api/catalog/products/{product_id}",
        json={
            "policy": {"batch_expiry_required": True},
        },
    )
    assert result.status_code == 200, result.text
    incompatible = client.get(path)
    assert incompatible.status_code == 422
    assert "BATCH" in incompatible.json()["detail"]
    assert (
        client.patch(
            f"/api/warehouses/{warehouse_id}",
            json={
                "tracking_mode": "BATCH",
                "issue_strategy": "FEFO",
            },
        ).status_code
        == 200
    )
    resolved = client.get(path)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["batch_expiry_required"] is True
    assert resolved.json()["issue_strategy"] == "FEFO"


def test_generic_setting_cannot_reintroduce_inventory_issue_defaults(client: TestClient) -> None:
    category = client.get("/api/settings/categories").json()[0]
    result = client.post(
        "/api/settings/definitions",
        json={
            "category_id": category["id"],
            "key": "inventory.default_issue_strategy",
            "name": "Strategy",
            "value_type": "ENUM",
            "default_value": "MANUAL",
            "allowed_scopes": ["PRODUCT"],
            "options": ["MANUAL", "FIFO", "FEFO"],
        },
    )
    assert result.status_code == 422


def test_decimal_setting_is_canonical_and_scope_is_checked(client: TestClient) -> None:
    _definition(client, key="custom.weight_limit", value_type="DECIMAL", default_value="12.50")
    resolved = client.get("/api/settings/resolve/custom.weight_limit")
    assert resolved.json()["value"] == "12.50"
    invalid_scope = client.put(
        "/api/settings/definitions/custom.weight_limit/values",
        json={
            "scope_type": "GLOBAL",
            "scope_id": str(uuid4()),
            "value": "2.5",
        },
    )
    assert invalid_scope.status_code == 422
    invalid_decimal = client.put(
        "/api/settings/definitions/custom.weight_limit/values",
        json={
            "scope_type": "GLOBAL",
            "value": "NaN",
        },
    )
    assert invalid_decimal.status_code == 422
