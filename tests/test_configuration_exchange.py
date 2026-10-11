from uuid import uuid4

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command


def test_import_preview_is_atomic_and_preserves_identity(client):
    path = "/api/reference-data/currencies/import"
    item_id = str(uuid4())
    body = {
        "rows": [{"ID": item_id, "Code": "EUR", "Name": "Euro", "Symbol": "€"}],
        "field_mapping": {"ID": "id", "Code": "code", "Name": "name", "Symbol": "symbol"},
    }
    preview = client.post(path, json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid"] is True
    assert preview.json()["applied"] is False
    assert preview.json()["records"][0]["record"]["symbol"] == "€"
    assert preview.json()["records"][0]["before"] is None
    assert client.get("/api/reference-data/currencies").json() == []
    applied = client.post(path, json={**body, "dry_run": False})
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] is True
    item = client.get("/api/reference-data/currencies/" + item_id).json()
    assert item["code"] == "EUR"
    exported = client.get("/api/reference-data/currencies/export").json()
    assert exported["records"] == [item]
    edited = {**item, "name": "European euro"}
    update = client.post(path, json={"dry_run": False, "rows": [edited]})
    assert update.status_code == 200, update.text
    assert update.json()["applied"] is True
    stale = client.post(path, json={"dry_run": False, "rows": [edited]})
    assert stale.json()["valid"] is False
    assert stale.json()["errors"][0]["row"] == 1
    invalid = client.post(
        path,
        json={
            "dry_run": False,
            "rows": [
                {"code": "USD", "name": "Dollar", "symbol": "$"},
                {"code": "USD", "name": "Duplicate", "symbol": "$"},
            ],
        },
    )
    assert invalid.json()["applied"] is False
    assert [v["code"] for v in client.get("/api/reference-data/currencies").json()] == ["EUR"]
    bad_field = client.post(
        path, json={"rows": [{"code": "JPY", "name": "Yen", "symbol": "¥", "unexpected": True}]}
    )
    assert bad_field.json()["valid"] is False
    # Exported source versions do not require a record to exist in the receiving database.
    fresh_id = str(uuid4())
    restored = client.post(
        path,
        json={
            "dry_run": False,
            "rows": [{"id": fresh_id, "version": 5, "code": "JPY", "name": "Yen", "symbol": "¥"}],
        },
    )
    assert restored.json()["applied"] is True, restored.text
    restored_record = client.get("/api/reference-data/currencies/" + fresh_id).json()
    assert restored_record["version"] == 1
    assert restored_record["created_by"] is not None


def test_counterparty_duplicate_warning_and_external_mapping_uniqueness(client):
    path = "/api/reference-data/counterparties"

    def create(code):
        response = client.post(
            path,
            json={"code": code, "name": "Acme", "is_supplier": True, "tax_identifier": "TAX123"},
        )
        assert response.status_code == 201, response.text
        return response.json()

    first, second = create("ACME"), create("ACME_OTHER")
    warnings = client.post(
        path + "/duplicate-check",
        json={"code": "NEW", "name": "Acme", "is_customer": True, "tax_identifier": "TAX123"},
    )
    assert len(warnings.json()["matches"]) == 2
    mapping = {"source": "accounting", "external_id": "party-123"}
    assert (
        client.put(path + "/" + first["id"] + "/external-identifiers", json=mapping).status_code
        == 200
    )
    assert (
        client.put(path + "/" + first["id"] + "/external-identifiers", json=mapping).status_code
        == 200
    )
    assert (
        client.put(path + "/" + second["id"] + "/external-identifiers", json=mapping).status_code
        == 409
    )
    assert client.get(path + "/" + first["id"] + "/external-identifiers").json() == [mapping]
    exported = client.get(path + "/export").json()
    assert exported["external_identifiers"] == [{"record_id": first["id"], **mapping}]
    assert len(client.get(path, params={"q": "TAX123"}).json()) == 2


def test_configuration_upgrade_preserves_existing_warehouse_and_unit(
    migration_database_url, monkeypatch
):
    monkeypatch.setenv("APP_DATABASE_URL", migration_database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "20261002_0008")
    engine = create_engine(migration_database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO catalog_units "
                "(id,code,name,symbol,dimension,`precision`,active,created_at,updated_at) "
                "VALUES (:id,'L','Liter','L','VOLUME',4,1,NOW(),NOW())"
            ),
            {"id": str(uuid4())},
        )
    command.upgrade(config, "head")
    tables = set(inspect(engine).get_table_names())
    assert {
        "configuration_currencies",
        "configuration_vat_rates",
        "configuration_storage_analytics",
        "configuration_storage_analytic_values",
        "configuration_enterprise",
        "configuration_accounting",
        "configuration_numbering",
        "configuration_external_mappings",
    } <= tables
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT display_decimal_places FROM catalog_units")
            ).scalar_one()
            == 4
        )
        assert (
            connection.execute(
                text("SELECT cost_accounting_enabled FROM configuration_accounting")
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(text("SELECT COUNT(*) FROM configuration_numbering")).scalar_one()
            == 9
        )
    command.downgrade(config, "20261002_0008")
    assert "configuration_accounting" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    engine.dispose()
