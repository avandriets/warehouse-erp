from decimal import Decimal

from fastapi.testclient import TestClient


def _create_foundation(client: TestClient) -> tuple[dict, dict]:
    category_response = client.post(
        "/api/catalog/categories",
        json={"code": "tobacco", "name": "Tobacco"},
    )
    assert category_response.status_code == 201

    unit_response = client.post(
        "/api/catalog/units",
        json={
            "code": "pack",
            "name": "Pack",
            "symbol": "pack",
            "dimension": "COUNT",
            "precision": 0,
        },
    )
    assert unit_response.status_code == 201
    return category_response.json(), unit_response.json()


def test_catalog_flow_creates_product_with_expiry_requirement(client: TestClient) -> None:
    category, unit = _create_foundation(client)

    response = client.post(
        "/api/catalog/products",
        json={
            "code": "mlb-red-20",
            "name": "Marlboro Red 20",
            "category_id": category["id"],
            "storage_unit_id": unit["id"],
            "brand": "Marlboro",
            "attributes": {"pack_size": 20},
            "policy": {
                "batch_expiry_required": True,
            },
        },
    )

    assert response.status_code == 201
    product = response.json()
    assert product["code"] == "MLB-RED-20"
    assert product["storage_unit_id"] == unit["id"]
    assert product["policy"] == {"batch_expiry_required": True}

    listed = client.get(f"/api/catalog/products?category_id={category['id']}")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [product["id"]]

    fetched = client.get(f"/api/catalog/products/{product['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == product


def test_category_tree_supports_roots_children_and_cycle_protection(
    client: TestClient,
) -> None:
    root = client.post(
        "/api/catalog/categories",
        json={"code": "raw", "name": "Raw materials"},
    ).json()
    child_response = client.post(
        "/api/catalog/categories",
        json={"code": "wood", "name": "Wood", "parent_id": root["id"]},
    )
    assert child_response.status_code == 201
    child = child_response.json()

    roots = client.get("/api/catalog/categories?root_only=true")
    children = client.get(f"/api/catalog/categories?parent_id={root['id']}")
    assert [category["id"] for category in roots.json()] == [root["id"]]
    assert [category["id"] for category in children.json()] == [child["id"]]

    cycle = client.patch(
        f"/api/catalog/categories/{root['id']}",
        json={"parent_id": child["id"]},
    )
    assert cycle.status_code == 422
    assert "cycle" in cycle.json()["detail"]


def test_duplicate_codes_return_conflict(client: TestClient) -> None:
    payload = {"code": "food", "name": "Food"}
    assert client.post("/api/catalog/categories", json=payload).status_code == 201
    response = client.post("/api/catalog/categories", json=payload)
    assert response.status_code == 409


def test_invalid_fefo_policy_returns_domain_validation_error(client: TestClient) -> None:
    category, unit = _create_foundation(client)

    response = client.post(
        "/api/catalog/products",
        json={
            "code": "INVALID-FEFO",
            "name": "Invalid FEFO product",
            "category_id": category["id"],
            "storage_unit_id": unit["id"],
            "policy": {"tracking_mode": "NONE", "issue_strategy": "FEFO"},
        },
    )

    assert response.status_code == 422
    assert any(item["type"] == "extra_forbidden" for item in response.json()["detail"])


def test_inactive_category_is_rejected_for_new_product(client: TestClient) -> None:
    category, unit = _create_foundation(client)
    updated = client.patch(
        f"/api/catalog/categories/{category['id']}",
        json={"name": "Tobacco products", "active": False},
    )
    assert updated.status_code == 200

    product = client.post(
        "/api/catalog/products",
        json={
            "code": "NEW-PRODUCT",
            "name": "New product",
            "category_id": category["id"],
            "storage_unit_id": unit["id"],
        },
    )
    assert product.status_code == 422
    assert product.json()["detail"] == "Category is inactive"


def test_missing_catalog_entity_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/catalog/products/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 404


def test_nested_packages_convert_to_storage_and_reject_cycles(client: TestClient) -> None:
    category, unit = _create_foundation(client)
    package_unit = client.post(
        "/api/catalog/units",
        json={
            "code": "box",
            "name": "Box",
            "symbol": "box",
            "dimension": "COUNT",
            "precision": 0,
        },
    ).json()
    package_set = client.post(
        "/api/catalog/package-sets",
        json={
            "code": "fasteners",
            "name": "Fastener packaging",
            "kind": "SHARED",
        },
    )
    assert package_set.status_code == 201
    set_id = package_set.json()["id"]
    pack = client.post(
        f"/api/catalog/package-sets/{set_id}/packages",
        json={
            "code": "bag",
            "name": "Bag",
            "unit_id": package_unit["id"],
            "contains_unit_id": unit["id"],
            "contains_quantity": "20",
        },
    )
    assert pack.status_code == 201, pack.text
    fractional_pack = client.post(
        f"/api/catalog/package-sets/{set_id}/packages",
        json={
            "code": "fraction",
            "name": "Fractional bag",
            "unit_id": package_unit["id"],
            "contains_unit_id": unit["id"],
            "contains_quantity": "0.5",
        },
    )
    assert fractional_pack.status_code == 422
    box = client.post(
        f"/api/catalog/package-sets/{set_id}/packages",
        json={
            "code": "box",
            "name": "Box",
            "unit_id": package_unit["id"],
            "contains_package_id": pack.json()["id"],
            "contains_quantity": "10",
        },
    )
    assert box.status_code == 201, box.text
    product = client.post(
        "/api/catalog/products",
        json={
            "code": "bolt",
            "name": "Bolt",
            "category_id": category["id"],
            "storage_unit_id": unit["id"],
            "package_set_id": set_id,
        },
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]
    conversion = client.post(
        f"/api/catalog/products/{product_id}/convert",
        json={
            "quantity": "2",
            "package_id": box.json()["id"],
        },
    )
    assert conversion.status_code == 200, conversion.text
    assert Decimal(conversion.json()["storage_quantity"]) == 400
    assert Decimal(conversion.json()["factor"]) == 200
    cycle = client.patch(
        f"/api/catalog/packages/{pack.json()['id']}",
        json={
            "contains_package_id": box.json()["id"],
        },
    )
    assert cycle.status_code == 422
    assert "cycle" in cycle.json()["detail"]
    unchanged = client.post(
        f"/api/catalog/products/{product_id}/convert",
        json={
            "quantity": "1",
            "package_id": box.json()["id"],
        },
    )
    assert Decimal(unchanged.json()["storage_quantity"]) == 200


def test_measurement_mode_precision_and_product_barcodes(client: TestClient) -> None:
    category, unit = _create_foundation(client)
    kg = client.post(
        "/api/catalog/units",
        json={
            "code": "kg",
            "name": "Kilogram",
            "symbol": "kg",
            "dimension": "MASS",
            "precision": 3,
            "classifier_code": "166",
        },
    )
    assert kg.status_code == 201
    product = client.post(
        "/api/catalog/products",
        json={
            "code": "pipe",
            "name": "Pipe",
            "category_id": category["id"],
            "storage_unit_id": unit["id"],
        },
    ).json()
    item = client.post(
        f"/api/catalog/products/{product['id']}/measurements",
        json={
            "unit_id": kg.json()["id"],
            "storage_quantity": "1",
            "measured_quantity": "2.5",
            "use": "REFERENCE_ONLY",
            "is_report_unit": True,
        },
    )
    assert item.status_code == 201, item.text
    payload = {"quantity": "5", "measurement_id": item.json()["id"]}
    blocked = client.post(f"/api/catalog/products/{product['id']}/convert", json=payload)
    assert blocked.status_code == 422
    enabled = client.patch(
        f"/api/catalog/products/{product['id']}/measurements/{item.json()['id']}",
        json={"use": "DOCUMENT"},
    )
    assert enabled.status_code == 200, enabled.text
    result = client.post(f"/api/catalog/products/{product['id']}/convert", json=payload)
    assert Decimal(result.json()["storage_quantity"]) == 2
    fractional = client.post(
        f"/api/catalog/products/{product['id']}/convert",
        json={
            "quantity": "1",
            "measurement_id": item.json()["id"],
        },
    )
    assert fractional.status_code == 422
    barcode = client.post(
        f"/api/catalog/products/{product['id']}/barcodes",
        json={
            "value": " 1234567890 ",
        },
    )
    assert barcode.status_code == 201, barcode.text
    assert barcode.json()["value"] == "1234567890"
    duplicate = client.post(
        f"/api/catalog/products/{product['id']}/barcodes",
        json={
            "value": "1234567890",
        },
    )
    assert duplicate.status_code == 409
    changed_unit = client.patch(
        f"/api/catalog/products/{product['id']}",
        json={
            "storage_unit_id": kg.json()["id"],
        },
    )
    assert changed_unit.status_code == 422


def test_incompatible_package_set_and_individual_ownership(client: TestClient) -> None:
    category, unit = _create_foundation(client)
    kg = client.post(
        "/api/catalog/units",
        json={
            "code": "kg",
            "name": "Kilogram",
            "symbol": "kg",
            "dimension": "MASS",
        },
    ).json()
    box = client.post(
        "/api/catalog/units",
        json={
            "code": "box",
            "name": "Box",
            "symbol": "box",
            "dimension": "COUNT",
            "precision": 0,
        },
    ).json()
    set_id = client.post(
        "/api/catalog/package-sets",
        json={
            "code": "private",
            "name": "Private",
            "kind": "INDIVIDUAL",
        },
    ).json()["id"]
    package = client.post(
        f"/api/catalog/package-sets/{set_id}/packages",
        json={
            "code": "case",
            "name": "Case",
            "unit_id": box["id"],
            "contains_unit_id": unit["id"],
            "contains_quantity": "12",
        },
    )
    assert package.status_code == 201
    wrong = client.post(
        "/api/catalog/products",
        json={
            "code": "wrong",
            "name": "Wrong",
            "category_id": category["id"],
            "storage_unit_id": kg["id"],
            "package_set_id": set_id,
        },
    )
    assert wrong.status_code == 422
    first = client.post(
        "/api/catalog/products",
        json={
            "code": "first",
            "name": "First",
            "category_id": category["id"],
            "storage_unit_id": unit["id"],
            "package_set_id": set_id,
        },
    )
    assert first.status_code == 201
    second = client.post(
        "/api/catalog/products",
        json={
            "code": "second",
            "name": "Second",
            "category_id": category["id"],
            "storage_unit_id": unit["id"],
            "package_set_id": set_id,
        },
    )
    assert second.status_code == 409


def test_global_unit_conversion_and_classifier_uniqueness(client: TestClient) -> None:
    kg = client.post(
        "/api/catalog/units",
        json={
            "code": "KG",
            "name": "Kilogram",
            "symbol": "kg",
            "dimension": "MASS",
            "precision": 3,
            "classifier_code": "166",
        },
    )
    assert kg.status_code == 201
    gram = client.post(
        "/api/catalog/units",
        json={
            "code": "G",
            "name": "Gram",
            "symbol": "g",
            "dimension": "MASS",
            "precision": 0,
            "base_unit_id": kg.json()["id"],
            "factor_to_base": "0.001",
        },
    )
    assert gram.status_code == 201, gram.text
    result = client.post(
        "/api/catalog/units/convert",
        json={
            "quantity": "1.25",
            "from_unit_id": kg.json()["id"],
            "to_unit_id": gram.json()["id"],
        },
    )
    assert result.status_code == 200, result.text
    assert Decimal(result.json()["quantity"]) == 1250
    invalid_base = client.post(
        "/api/catalog/units",
        json={
            "code": "M",
            "name": "Meter",
            "symbol": "m",
            "dimension": "LENGTH",
            "base_unit_id": kg.json()["id"],
            "factor_to_base": "1",
        },
    )
    assert invalid_base.status_code == 422
    duplicate_classifier = client.post(
        "/api/catalog/units",
        json={
            "code": "KG2",
            "name": "Kilogram duplicate",
            "symbol": "kg",
            "dimension": "MASS",
            "classifier_code": "166",
        },
    )
    assert duplicate_classifier.status_code == 409


def test_legacy_unit_can_be_classified_only_once(client: TestClient) -> None:
    unit = client.post(
        "/api/catalog/units",
        json={
            "code": "legacy",
            "name": "Legacy",
            "symbol": "legacy",
            "dimension": "OTHER",
        },
    ).json()
    updated = client.patch(f"/api/catalog/units/{unit['id']}", json={"dimension": "COUNT"})
    assert updated.status_code == 200
    rejected = client.patch(f"/api/catalog/units/{unit['id']}", json={"dimension": "MASS"})
    assert rejected.status_code == 422
