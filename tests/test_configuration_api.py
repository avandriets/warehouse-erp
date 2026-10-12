from dataclasses import replace
from uuid import uuid4

import pytest
from conftest import ADMIN_USER_ID

from warehouse_erp.identity.api.dependencies import get_current_user


def create(client, directory, **values):
    response = client.post("/api/reference-data/" + directory, json=values)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "directory,payload",
    [
        ("currencies", dict(code="EUR", name="Euro", symbol="€")),
        ("vat-rates", dict(code="VAT20", name="VAT 20%", treatment="TAXABLE", rate="20")),
        (
            "storage-analytics",
            dict(code="QUALITY", name="Quality", value_type="ENUM", options=["A", "B"]),
        ),
        (
            "counterparties",
            dict(code="SUP", name="Supplier", is_supplier=True, tax_identifier="TAX-123"),
        ),
        ("price-types", dict(code="RETAIL", name="Retail", price_entry_mode="TAX_INCLUSIVE")),
        ("adjustment-reasons", dict(code="SPOILAGE", name="Spoilage", operation="SPOILAGE")),
    ],
)
def test_directory_round_trip_version_search_and_audit(client, directory, payload):
    path = "/api/reference-data/" + directory
    item = create(client, directory, **payload)
    assert client.get(path + "/" + item["id"]).json() == item
    assert client.post(path, json=payload).status_code == 409
    result = client.get(path, params={"q": payload["name"], "limit": 1}).json()
    if directory in {"adjustment-reasons", "price-types", "currencies"}:
        assert result == {"items": [item], "total": 1}
    else:
        assert len(result) == 1
    renamed = client.patch(path + "/" + item["id"], json={"name": "Updated", "expected_version": 1})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["version"] == 2
    assert (
        client.patch(
            path + "/" + item["id"], json={"name": "Lost update", "expected_version": 1}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            path + "/" + item["id"], json={"code": "CHANGED", "expected_version": 2}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            path + "/" + item["id"], json={"name": None, "expected_version": 2}
        ).status_code
        == 422
    )
    archived = client.patch(path + "/" + item["id"], json={"active": False, "expected_version": 2})
    assert archived.status_code == 200
    expected = (
        {"items": [], "total": 0}
        if directory in {"adjustment-reasons", "price-types", "currencies"}
        else []
    )
    assert client.get(path, params={"active": True}).json() == expected
    history = client.get(path + "/" + item["id"] + "/history").json()
    assert len(history) == 3
    assert any(
        h["before"] and h["before"]["name"] == payload["name"] and h["after"]["name"] == "Updated"
        for h in history
    )
    assert all(h["actor_id"] == str(ADMIN_USER_ID) for h in history)


def test_analytic_value_scope_types_and_definition_changes(client):
    definition = create(
        client,
        "storage-analytics",
        code="GRADE",
        name="Grade",
        value_type="ENUM",
        options=["A", "B"],
        enabled=True,
        required=True,
    )
    value = create(
        client,
        "storage-analytic-values",
        code="GRADE_A",
        name="A",
        definition_id=definition["id"],
        value="A",
    )
    path = "/api/reference-data/storage-analytic-values"
    assert client.get(path, params={"definition_id": definition["id"]}).json() == [value]
    assert client.get(path, params={"definition_id": str(uuid4())}).json() == []
    invalid = client.post(
        path, json=dict(code="C", name="C", definition_id=definition["id"], value="C")
    )
    assert invalid.status_code == 422
    assert (
        client.patch(
            "/api/reference-data/storage-analytics/" + definition["id"],
            json={"expected_version": 1, "value_type": "INTEGER", "options": []},
        ).status_code
        == 409
    )


def test_enterprise_and_accounting_settings_persist_and_validate_references(client):
    profile = client.get("/api/settings/enterprise").json()
    saved = client.patch(
        "/api/settings/enterprise",
        json={
            "expected_version": profile["version"],
            "legal_name": "Example SL",
            "tax_identifier": "EX123",
            "tax_identifier_label": "NIF",
            "logo_url": "https://example.test/logo.png",
        },
    )
    assert saved.status_code == 200, saved.text
    assert client.get("/api/settings/enterprise").json()["legal_name"] == "Example SL"
    assert (
        client.get("/api/settings/history/enterprise").json()[0]["after"]["tax_identifier"]
        == "EX123"
    )
    currency = create(client, "currencies", code="EUR", name="Euro", symbol="€")
    vat = create(client, "vat-rates", code="ZERO", name="Zero", treatment="ZERO_RATE")
    accounting = client.get("/api/settings/accounting").json()
    assert accounting["cost_accounting_enabled"] is False
    assert accounting["cost_valuation_method"] == "MOVING_WEIGHTED_AVERAGE"
    saved = client.patch(
        "/api/settings/accounting",
        json={
            "expected_version": accounting["version"],
            "currency_id": currency["id"],
            "vat_enabled": True,
            "default_vat_rate_id": vat["id"],
            "changes_locked_through": "2026-01-31",
            "accounting_timezone": "Europe/Madrid",
        },
    )
    assert saved.status_code == 200, saved.text
    assert client.get("/api/settings/accounting").json() == saved.json()
    assert (
        client.patch(
            "/api/settings/accounting", json={"expected_version": 2, "currency_id": str(uuid4())}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            "/api/settings/accounting",
            json={"expected_version": 2, "accounting_timezone": "Invalid/Zone"},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/reference-data/currencies/" + currency["id"],
            json={"expected_version": 1, "active": False},
        ).status_code
        == 409
    )


def test_numbering_has_all_fixed_document_types_and_versioned_rules(client):
    rules = client.get("/api/settings/document-numbering").json()
    assert len(rules) == 9
    updated = client.patch(
        "/api/settings/document-numbering/GOODS_RECEIPT",
        json={"expected_version": 1, "prefix": "GR-", "numeric_width": 8, "reset_annually": False},
    )
    assert updated.status_code == 200, updated.text
    rules = client.get("/api/settings/document-numbering").json()
    assert next(r for r in rules if r["document_type"] == "GOODS_RECEIPT")["prefix"] == "GR-"
    assert (
        client.patch(
            "/api/settings/document-numbering/CUSTOM", json={"expected_version": 1, "prefix": "X"}
        ).status_code
        == 422
    )


def test_cost_accounting_and_negative_stock_configuration_are_mutually_exclusive(client):
    path = "/api/settings/definitions/inventory.negative_stock_allowed/values"
    assert client.put(path, json={"scope_type": "GLOBAL", "value": True}).status_code == 200
    assert (
        client.patch(
            "/api/settings/accounting",
            json={"expected_version": 1, "cost_accounting_enabled": True},
        ).status_code
        == 409
    )
    assert (
        client.put(
            path, json={"scope_type": "GLOBAL", "value": False, "expected_version": 1}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/api/settings/accounting",
            json={"expected_version": 1, "cost_accounting_enabled": True},
        ).status_code
        == 200
    )
    assert (
        client.put(
            path, json={"scope_type": "GLOBAL", "value": True, "expected_version": 2}
        ).status_code
        == 422
    )
    assert client.get("/api/settings/inventory-defaults").json()["negative_stock_allowed"] is False


def test_read_and_write_permissions_do_not_depend_on_client_app_name(client):
    current = client.app.dependency_overrides[get_current_user]()
    client.app.dependency_overrides[get_current_user] = lambda: replace(
        current, grants=tuple(g for g in current.grants if g.permission_code == "settings.read")
    )
    assert client.get("/api/settings/accounting").status_code == 200
    assert client.get("/api/reference-data/currencies").status_code == 200
    assert (
        client.patch(
            "/api/settings/accounting",
            json={"expected_version": 1, "vat_enabled": True, "application": "admin"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/reference-data/currencies", json={"code": "EUR", "name": "Euro", "symbol": "€"}
        ).status_code
        == 403
    )
    assert client.get("/api/reference-data/counterparties").status_code == 403


def test_own_profile_is_allowlisted_and_warehouse_must_be_accessible(client):
    warehouse = client.post("/api/warehouses", json={"code": "MAIN", "name": "Main"}).json()
    saved = client.patch(
        "/api/identity/me", json={"first_name": "Alex", "default_warehouse_id": warehouse["id"]}
    )
    assert saved.status_code == 200, saved.text
    # The mocked auth actor is refreshed like a real subsequent authenticated request.
    current = client.app.dependency_overrides[get_current_user]()
    client.app.dependency_overrides[get_current_user] = lambda: replace(current, grants=())
    assert client.patch("/api/identity/me", json={"first_name": "Own name"}).status_code == 200
    assert client.patch("/api/identity/me", json={"status": "ACTIVE"}).status_code == 422
    assert client.patch("/api/identity/me", json={"user_id": str(uuid4())}).status_code == 422
    assert (
        client.patch("/api/identity/me", json={"default_warehouse_id": warehouse["id"]}).status_code
        == 403
    )
    assert client.patch("/api/identity/me", json={"default_warehouse_id": None}).status_code == 200


def test_address_storage_and_display_precision_round_trip(client):
    warehouse = client.post(
        "/api/warehouses",
        json={"code": "ADDRESS", "name": "Address", "address_storage_enabled": True},
    )
    assert warehouse.status_code == 201, warehouse.text
    warehouse = warehouse.json()
    assert (
        client.get("/api/warehouses/" + warehouse["id"]).json()["address_storage_enabled"] is True
    )
    assert (
        client.patch(
            "/api/warehouses/" + warehouse["id"], json={"address_storage_enabled": False}
        ).json()["address_storage_enabled"]
        is False
    )
    unit = client.post(
        "/api/catalog/units",
        json={
            "code": "L",
            "name": "Liter",
            "symbol": "L",
            "dimension": "VOLUME",
            "precision": 3,
            "display_decimal_places": 0,
        },
    ).json()
    result = client.post(
        "/api/catalog/units/convert",
        json={"quantity": "1.123", "from_unit_id": unit["id"], "to_unit_id": unit["id"]},
    )
    assert result.status_code == 200, result.text
    assert (
        client.patch("/api/catalog/units/" + unit["id"], json={"display_decimal_places": 2}).json()[
            "precision"
        ]
        == 3
    )


def test_general_warehouse_settings_share_data_and_require_both_permissions(client):
    path = "/api/settings/warehouses"
    warehouse = client.post("/api/warehouses", json={"code": "WH", "name": "Warehouse"}).json()
    assert client.get(path + "/" + warehouse["id"]).json()["tracking_mode"] == "NONE"
    changed = client.patch(
        path + "/" + warehouse["id"],
        json={"tracking_mode": "BATCH", "issue_strategy": "FEFO", "address_storage_enabled": True},
    )
    assert changed.status_code == 200, changed.text
    assert client.get("/api/warehouses/" + warehouse["id"]).json()["issue_strategy"] == "FEFO"
    assert client.patch(path + "/" + warehouse["id"], json={"active": False}).status_code == 422
    current = client.app.dependency_overrides[get_current_user]()
    client.app.dependency_overrides[get_current_user] = lambda: replace(
        current,
        grants=tuple(
            g for g in current.grants if g.permission_code in {"settings.read", "warehouse.read"}
        ),
    )
    assert client.get(path).status_code == 200
    assert (
        client.patch(path + "/" + warehouse["id"], json={"issue_strategy": "FIFO"}).status_code
        == 403
    )
    client.app.dependency_overrides[get_current_user] = lambda: replace(
        current, grants=tuple(g for g in current.grants if g.permission_code == "settings.read")
    )
    assert client.get(path).status_code == 403


def test_scoped_overrides_require_resource_permission(client):
    warehouse = client.post("/api/warehouses", json={"code": "WH", "name": "Warehouse"}).json()
    current = client.app.dependency_overrides[get_current_user]()
    client.app.dependency_overrides[get_current_user] = lambda: replace(
        current,
        grants=tuple(
            g for g in current.grants if g.permission_code in {"settings.read", "settings.manage"}
        ),
    )
    path = "/api/settings/definitions/inventory.negative_stock_allowed/values"
    assert client.put(path, json={"scope_type": "GLOBAL", "value": False}).status_code == 200
    assert (
        client.put(
            path, json={"scope_type": "WAREHOUSE", "scope_id": warehouse["id"], "value": True}
        ).status_code
        == 403
    )
    assert (
        client.put(
            path, json={"scope_type": "PRODUCT", "scope_id": str(uuid4()), "value": True}
        ).status_code
        == 403
    )


@pytest.mark.parametrize("directory", ["adjustment-reasons", "price-types"])
def test_directory_total_matches_filters_before_pagination(client, directory):
    path = "/api/reference-data/" + directory
    first = create(client, directory, code="DAMAGE_A", name="Damage A")
    second = create(client, directory, code="DAMAGE_B", name="Damage B")
    archived = create(client, directory, code="DAMAGE_C", name="Damage C", active=False)
    create(client, directory, code="OTHER", name="Other")
    params = {"q": "Damage", "active": True, "limit": 1, "offset": 1}
    response = client.get(path, params=params)
    assert response.status_code == 200
    assert response.json() == {"items": [second], "total": 2}
    params["offset"] = 20
    assert client.get(path, params=params).json() == {"items": [], "total": 2}
    assert client.get(path, params={"q": "DAMAGE_", "limit": 1}).json() == {
        "items": [first],
        "total": 3,
    }
    assert client.get(path, params={"q": "Damage", "active": False}).json() == {
        "items": [archived],
        "total": 1,
    }
    assert client.get(path, params={"q": "missing"}).json() == {"items": [], "total": 0}
