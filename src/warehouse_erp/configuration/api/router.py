from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError as PayloadError
from sqlalchemy.orm import Session

from warehouse_erp.catalog.permissions import CatalogPermission
from warehouse_erp.configuration.api.schemas import (
    DIRECTORY_SCHEMAS,
    AccountingSettingsResponse,
    AccountingSettingsUpdate,
    AdjustmentReasonPageResponse,
    CurrencyBaseUpdate,
    CurrencyPageResponse,
    CurrencyRatesLoad,
    CurrencyRatesOverviewResponse,
    DocumentNumberingResponse,
    DocumentNumberingUpdate,
    EnterpriseSettingsResponse,
    EnterpriseSettingsUpdate,
    ExchangeRequest,
    ExternalMappingRequest,
    PriceTypePageResponse,
)
from warehouse_erp.configuration.application.currency_rates import CurrencyRatesService
from warehouse_erp.configuration.application.service import ConfigurationService, settings_id
from warehouse_erp.configuration.domain.entities import DocumentType
from warehouse_erp.configuration.infrastructure.exchange_rates import (
    FrankfurterExchangeRatesProvider,
)
from warehouse_erp.configuration.infrastructure.repositories import (
    SqlAlchemyConfigurationUnitOfWork,
)
from warehouse_erp.configuration.permissions import ConfigurationPermission
from warehouse_erp.database import get_db_session
from warehouse_erp.identity.api.dependencies import get_current_user, require_permission
from warehouse_erp.identity.domain.entities import CurrentUser
from warehouse_erp.inventory.domain.policies import IssueStrategy, TrackingMode
from warehouse_erp.settings.domain.entities import ValueType
from warehouse_erp.settings.permissions import SettingsPermission
from warehouse_erp.shared.errors import ValidationError
from warehouse_erp.warehouse.api.router import (
    Service as WarehouseServiceDependency,
)
from warehouse_erp.warehouse.api.router import (
    get_warehouse,
    list_warehouses,
    update_warehouse,
)
from warehouse_erp.warehouse.api.schemas import WarehouseResponse, WarehouseUpdate

router = APIRouter(tags=["configuration"])


def get_configuration_service(session: Annotated[Session, Depends(get_db_session)]):
    return ConfigurationService(SqlAlchemyConfigurationUnitOfWork(session))


Service = Annotated[ConfigurationService, Depends(get_configuration_service)]
Actor = Annotated[CurrentUser, Depends(get_current_user)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
Search = Annotated[str | None, Query(max_length=255)]
GENERAL_DIRECTORIES = {"currencies", "vat-rates", "storage-analytics", "storage-analytic-values"}


def register_directory(kind, create_schema, update_schema, response_schema):
    read = SettingsPermission.READ if kind in GENERAL_DIRECTORIES else CatalogPermission.READ
    create = SettingsPermission.MANAGE if kind in GENERAL_DIRECTORIES else CatalogPermission.CREATE
    edit = SettingsPermission.MANAGE if kind in GENERAL_DIRECTORIES else CatalogPermission.EDIT
    path = f"/reference-data/{kind}"

    page_schema = {
        "adjustment-reasons": AdjustmentReasonPageResponse,
        "price-types": PriceTypePageResponse,
        "currencies": CurrencyPageResponse,
    }.get(kind)

    def list_records(
        service: Service,
        q: Search = None,
        active: bool | None = None,
        limit: Limit = 50,
        offset: Offset = 0,
    ):
        if page_schema is not None:
            items, total = service.list_page(kind, q=q, active=active, limit=limit, offset=offset)
            return {"items": items, "total": total}
        return service.list(
            kind, q=q, active=active, definition_id=None, limit=limit, offset=offset
        )

    def list_values(
        service: Service,
        definition_id: UUID | None = None,
        q: Search = None,
        active: bool | None = None,
        limit: Limit = 50,
        offset: Offset = 0,
    ):
        return service.list(
            kind, q=q, active=active, definition_id=definition_id, limit=limit, offset=offset
        )

    def get_record(item_id: UUID, service: Service):
        return service.get(kind, item_id)

    def create_record(payload, service: Service, actor: Actor):
        return service.create(kind, payload.model_dump(), actor.user_id)

    def update_record(item_id: UUID, payload, service: Service, actor: Actor):
        return service.update(
            kind,
            item_id,
            payload.model_dump(exclude_unset=True, exclude={"expected_version"}),
            payload.expected_version,
            actor.user_id,
        )

    def history(item_id: UUID, service: Service, limit: Limit = 50, offset: Offset = 0):
        service.get(kind, item_id)
        return service.uow.records.history(kind, item_id, limit, offset)

    def export_records(
        service: Service,
        q: Search = None,
        active: bool | None = None,
        limit: Limit = 100,
        offset: Offset = 0,
    ):
        items = service.list(
            kind, q=q, active=active, definition_id=None, limit=limit, offset=offset
        )
        return {
            "directory": kind,
            "limit": limit,
            "offset": offset,
            "records": [
                response_schema.model_validate(item).model_dump(mode="json") for item in items
            ],
            "external_identifiers": [
                dict(record_id=str(item.id), **mapping)
                for item in items
                for mapping in service.uow.records.mappings(kind, item.id)
            ],
        }

    def import_records(payload: ExchangeRequest, service: Service, actor: Actor):
        if len(set(payload.field_mapping.values())) != len(payload.field_mapping):
            raise ValidationError("Field mapping targets must be unique")
        allowed = set(create_schema.model_fields) | {
            "id",
            "expected_version",
            "version",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        }
        if set(payload.field_mapping.values()) - allowed:
            raise ValidationError("Unknown field mapping target")
        rows, errors = [], []
        for index, raw in enumerate(payload.rows, 1):
            try:
                data = (
                    {
                        target: raw[source]
                        for source, target in payload.field_mapping.items()
                        if source in raw
                    }
                    if payload.field_mapping
                    else dict(raw)
                )
                raw_id = data.pop("id", None)
                item_id = UUID(str(raw_id)) if raw_id is not None else None
                expected = data.pop("expected_version", None)
                source_version = data.pop("version", None)
                for version in (expected, source_version):
                    if version is not None and (type(version) is not int or version < 1):
                        raise ValueError("version must be a positive integer")
                for field in ("created_at", "updated_at", "created_by", "updated_by"):
                    data.pop(field, None)
                values = create_schema.model_validate(data).model_dump()
                rows.append(
                    {
                        "row": index,
                        "id": item_id,
                        "expected_version": expected,
                        "source_version": source_version,
                        "values": values,
                    }
                )
            except (PayloadError, ValueError) as exc:
                errors.append({"row": index, "message": str(exc)})
        result = service.import_records(
            kind, rows, actor.user_id, dry_run=payload.dry_run, errors=errors
        )
        for row in result["records"]:
            row["record"] = response_schema.model_validate(row["record"]).model_dump(mode="json")
            if row["before"] is not None:
                row["before"] = response_schema.model_validate(row["before"]).model_dump(
                    mode="json"
                )
        return result

    def duplicate_check(payload, service: Service):
        from warehouse_erp.configuration.domain.entities import DIRECTORIES

        item = DIRECTORIES[kind](**payload.model_dump())
        return {"matches": service.uow.records.similar(kind, item)}

    def get_mappings(item_id: UUID, service: Service):
        service.get(kind, item_id)
        return service.uow.records.mappings(kind, item_id)

    def set_mapping(item_id: UUID, payload: ExternalMappingRequest, service: Service, actor: Actor):
        service.uow.records.lock()
        service.get(kind, item_id)
        result = service.uow.records.set_mapping(
            kind, item_id, payload.source, payload.external_id, actor.user_id
        )
        service.uow.commit()
        return result

    duplicate_check.__annotations__["payload"] = create_schema
    router.add_api_route(
        path + "/export",
        export_records,
        methods=["GET"],
        name=f"{kind}_export",
        dependencies=[
            Depends(require_permission(read)),
            Depends(require_permission(ConfigurationPermission.EXPORT)),
        ],
    )
    router.add_api_route(
        path + "/import",
        import_records,
        methods=["POST"],
        name=f"{kind}_import",
        dependencies=[
            Depends(require_permission(create)),
            Depends(require_permission(edit)),
            Depends(require_permission(ConfigurationPermission.IMPORT)),
        ],
    )
    router.add_api_route(
        path + "/duplicate-check",
        duplicate_check,
        methods=["POST"],
        name=f"{kind}_duplicate_check",
        dependencies=[Depends(require_permission(read))],
    )
    router.add_api_route(
        path + "/{item_id}/external-identifiers",
        get_mappings,
        methods=["GET"],
        name=f"{kind}_external_identifiers",
        dependencies=[Depends(require_permission(read))],
    )
    router.add_api_route(
        path + "/{item_id}/external-identifiers",
        set_mapping,
        methods=["PUT"],
        name=f"{kind}_set_external_identifier",
        dependencies=[Depends(require_permission(edit))],
    )

    create_record.__annotations__["payload"] = create_schema
    update_record.__annotations__["payload"] = update_schema
    for method, endpoint, suffix, permission, model in (
        (
            "GET",
            list_values if kind == "storage-analytic-values" else list_records,
            "",
            read,
            page_schema or list[response_schema],
        ),
        ("POST", create_record, "", create, response_schema),
        ("GET", get_record, "/{item_id}", read, response_schema),
        ("PATCH", update_record, "/{item_id}", edit, response_schema),
        ("GET", history, "/{item_id}/history", read, None),
    ):
        router.add_api_route(
            path + suffix,
            endpoint,
            methods=[method],
            response_model=model,
            status_code=201 if method == "POST" else 200,
            name=f"{kind}_{endpoint.__name__}",
            dependencies=[Depends(require_permission(permission))],
        )


for directory, schemas in DIRECTORY_SCHEMAS.items():
    register_directory(directory, *schemas)


@router.get(
    "/settings/options", dependencies=[Depends(require_permission(SettingsPermission.READ))]
)
def options():
    from warehouse_erp.configuration.domain.entities import (
        PriceEntryMode,
        TaxTreatment,
        ValuationMethod,
    )

    return {
        "document_types": list(DocumentType),
        "tracking_modes": list(TrackingMode),
        "issue_strategies": list(IssueStrategy),
        "cost_valuation_methods": list(ValuationMethod),
        "vat_treatments": list(TaxTreatment),
        "price_entry_modes": list(PriceEntryMode),
        "analytic_value_types": list(ValueType),
        "rounding_modes": ["HALF_UP", "HALF_EVEN", "DOWN"],
        "adjustment_operations": ["WRITE_OFF", "ADJUSTMENT", "SPOILAGE", "DISPOSAL"],
    }


@router.get(
    "/settings/warehouses",
    response_model=list[WarehouseResponse],
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def warehouse_settings(
    service: WarehouseServiceDependency,
    actor: Actor,
    limit: Limit = 50,
    offset: Offset = 0,
    active: bool | None = None,
):
    return list_warehouses(service, actor, limit, offset, active)


@router.get(
    "/settings/warehouses/{warehouse_id}",
    response_model=WarehouseResponse,
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def warehouse_setting(warehouse_id: UUID, service: WarehouseServiceDependency, actor: Actor):
    return get_warehouse(warehouse_id, service, actor)


@router.patch(
    "/settings/warehouses/{warehouse_id}",
    response_model=WarehouseResponse,
    dependencies=[Depends(require_permission(SettingsPermission.MANAGE))],
)
def update_warehouse_setting(
    warehouse_id: UUID, payload: WarehouseUpdate, service: WarehouseServiceDependency, actor: Actor
):
    if payload.model_fields_set - {"tracking_mode", "issue_strategy", "address_storage_enabled"}:
        raise ValidationError("Edit warehouse master-data fields through the warehouse directory")
    return update_warehouse(warehouse_id, payload, service, actor)


@router.get(
    "/settings/enterprise",
    response_model=EnterpriseSettingsResponse,
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def enterprise(service: Service):
    return service.section("enterprise")


@router.patch(
    "/settings/enterprise",
    response_model=EnterpriseSettingsResponse,
    dependencies=[Depends(require_permission(SettingsPermission.MANAGE))],
)
def update_enterprise(payload: EnterpriseSettingsUpdate, service: Service, actor: Actor):
    return service.update(
        "enterprise",
        settings_id("enterprise"),
        payload.model_dump(exclude_unset=True, exclude={"expected_version"}),
        payload.expected_version,
        actor.user_id,
    )


@router.get(
    "/settings/accounting",
    response_model=AccountingSettingsResponse,
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def accounting(service: Service):
    return service.section("accounting")


@router.patch(
    "/settings/accounting",
    response_model=AccountingSettingsResponse,
    dependencies=[Depends(require_permission(SettingsPermission.MANAGE))],
)
def update_accounting(payload: AccountingSettingsUpdate, service: Service, actor: Actor):
    return service.update(
        "accounting",
        settings_id("accounting"),
        payload.model_dump(exclude_unset=True, exclude={"expected_version"}),
        payload.expected_version,
        actor.user_id,
    )


@router.get(
    "/settings/document-numbering",
    response_model=list[DocumentNumberingResponse],
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def numbering(service: Service):
    return service.numbering()


@router.patch(
    "/settings/document-numbering/{document_type}",
    response_model=DocumentNumberingResponse,
    dependencies=[Depends(require_permission(SettingsPermission.MANAGE))],
)
def update_numbering(
    document_type: DocumentType, payload: DocumentNumberingUpdate, service: Service, actor: Actor
):
    return service.update_numbering(
        document_type,
        payload.model_dump(exclude_unset=True, exclude={"expected_version"}),
        payload.expected_version,
        actor.user_id,
    )


@router.get(
    "/settings/history/{section}",
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def settings_history(section: str, service: Service, limit: Limit = 50, offset: Offset = 0):
    from warehouse_erp.shared.errors import NotFoundError

    if section not in {"enterprise", "accounting"}:
        raise NotFoundError("Unknown settings section")
    return service.uow.records.history(section, settings_id(section), limit, offset)


def get_currency_rates_service(session: Annotated[Session, Depends(get_db_session)]):
    return CurrencyRatesService(
        SqlAlchemyConfigurationUnitOfWork(session), FrankfurterExchangeRatesProvider()
    )


RatesService = Annotated[CurrencyRatesService, Depends(get_currency_rates_service)]


@router.get(
    "/reference-data/currency-rates",
    response_model=CurrencyRatesOverviewResponse,
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def currency_rates(service: RatesService):
    return service.overview()


@router.patch(
    "/reference-data/currency-rates/base-currency",
    response_model=CurrencyRatesOverviewResponse,
    dependencies=[Depends(require_permission(SettingsPermission.MANAGE))],
)
def set_currency_base(payload: CurrencyBaseUpdate, service: RatesService, actor: Actor):
    return service.set_base(payload.currency_id, payload.expected_version, actor.user_id)


@router.post(
    "/reference-data/currency-rates/load",
    response_model=CurrencyRatesOverviewResponse,
    dependencies=[Depends(require_permission(SettingsPermission.MANAGE))],
)
def load_currency_rates(payload: CurrencyRatesLoad, service: RatesService, actor: Actor):
    return service.load(payload.base_currency_id, payload.expected_version, actor.user_id)
