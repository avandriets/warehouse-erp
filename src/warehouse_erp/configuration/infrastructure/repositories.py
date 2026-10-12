from dataclasses import asdict, fields
from datetime import UTC, date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from warehouse_erp.configuration.application.service import settings_id
from warehouse_erp.configuration.domain.entities import (
    DIRECTORIES,
    SETTINGS,
    DocumentNumbering,
    DocumentType,
    Record,
    now,
)
from warehouse_erp.configuration.domain.exchange_rates import CurrencyRateBatch, ExchangeRate
from warehouse_erp.configuration.infrastructure.models import (
    MODELS,
    AccountingSettingsModel,
    ConfigurationAuditModel,
    ConfigurationGuardModel,
    CurrencyModel,
    CurrencyRateBatchModel,
    CurrencyRateModel,
    ExternalMappingModel,
    StorageAnalyticValueModel,
)
from warehouse_erp.settings.infrastructure.models import SettingDefinitionModel, SettingValueModel
from warehouse_erp.shared.errors import ConflictError, ValidationError

CLASSES = {**DIRECTORIES, **SETTINGS, "numbering": DocumentNumbering}
UUID_FIELDS = {
    "id",
    "created_by",
    "updated_by",
    "definition_id",
    "currency_id",
    "default_vat_rate_id",
}


def snapshot(item: Record | None) -> dict | None:
    if item is None:
        return None

    def encode(value):
        if isinstance(value, UUID | Decimal | date):
            return value.isoformat() if isinstance(value, date) else str(value)
        if isinstance(value, StrEnum):
            return value.value
        if isinstance(value, tuple):
            return list(value)
        return value

    return {key: encode(value) for key, value in asdict(item).items()}


def model_values(item: Record) -> dict:
    return {
        key: str(value)
        if isinstance(value, UUID)
        else value.value
        if isinstance(value, StrEnum)
        else list(value)
        if isinstance(value, tuple)
        else value
        for key, value in asdict(item).items()
    }


def entity(kind: str, model) -> Record:
    data = {f.name: getattr(model, f.name) for f in fields(CLASSES[kind])}
    for key in UUID_FIELDS & data.keys():
        if data[key] is not None:
            data[key] = UUID(data[key])
    for key in ("created_at", "updated_at"):
        if data[key].tzinfo is None:
            data[key] = data[key].replace(tzinfo=UTC)
    return CLASSES[kind](**data)


class SqlAlchemyConfigurationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.locked = False

    def lock(self) -> None:
        # Shared serialization point for accounting, reference edits and negative-stock writes.
        guard = self.session.scalar(
            select(ConfigurationGuardModel).where(ConfigurationGuardModel.id == 1).with_for_update()
        )
        if guard is None:
            raise RuntimeError("Configuration defaults have not been migrated/seeded")
        self.locked = True

    def get(self, kind: str, item_id: UUID) -> Record | None:
        query = (
            select(MODELS[kind])
            .where(MODELS[kind].id == str(item_id))
            .execution_options(populate_existing=True)
        )
        if self.locked:
            query = query.with_for_update()
        model = self.session.scalar(query)
        return entity(kind, model) if model else None

    def get_by_code(self, kind: str, code: str, definition_id: UUID | None) -> Record | None:
        model = MODELS[kind]
        query = select(model).where(model.code == code)
        if definition_id is not None:
            query = query.where(model.definition_id == str(definition_id))
        if self.locked:
            query = query.with_for_update()
        found = self.session.scalar(query)
        return entity(kind, found) if found else None

    def list(
        self,
        kind: str,
        *,
        q: str | None,
        active: bool | None,
        definition_id: UUID | None,
        limit: int,
        offset: int,
    ) -> list[Record]:
        model = MODELS[kind]
        query = self._filtered_query(kind, q=q, active=active, definition_id=definition_id)
        query = query.order_by(model.name, model.id)
        if self.locked:
            query = query.with_for_update()
        return [
            entity(kind, row) for row in self.session.scalars(query.limit(limit).offset(offset))
        ]

    def count(
        self, kind: str, *, q: str | None, active: bool | None, definition_id: UUID | None
    ) -> int:
        query = self._filtered_query(kind, q=q, active=active, definition_id=definition_id)
        return self.session.scalar(select(func.count()).select_from(query.subquery())) or 0

    def _filtered_query(
        self, kind: str, *, q: str | None, active: bool | None, definition_id: UUID | None
    ):
        model = MODELS[kind]
        query = select(model)
        if active is not None:
            query = query.where(model.active == active)
        if definition_id is not None:
            if kind != "storage-analytic-values":
                raise ValidationError("definition_id applies only to analytic values")
            query = query.where(model.definition_id == str(definition_id))
        if q and q.strip():
            columns = [model.code, model.name]
            if kind == "counterparties":
                columns += [model.tax_identifier, model.registration_identifier]
            query = query.where(or_(*(c.contains(q.strip(), autoescape=True) for c in columns)))
        return query

    def active_currencies(self):
        query = (
            select(CurrencyModel).where(CurrencyModel.active.is_(True)).order_by(CurrencyModel.code)
        )
        if self.locked:
            query = query.with_for_update()
        return [
            entity("currencies", row)
            for row in self.session.scalars(query.execution_options(populate_existing=True))
        ]

    def latest_currency_rates(self, base_currency_id: UUID) -> CurrencyRateBatch | None:
        batch = self.session.scalar(
            select(CurrencyRateBatchModel)
            .where(CurrencyRateBatchModel.base_currency_id == str(base_currency_id))
            .order_by(CurrencyRateBatchModel.fetched_at.desc(), CurrencyRateBatchModel.id.desc())
            .limit(1)
        )
        if batch is None:
            return None
        rows = self.session.scalars(
            select(CurrencyRateModel)
            .where(CurrencyRateModel.batch_id == batch.id)
            .order_by(CurrencyRateModel.quote_code)
        )
        return CurrencyRateBatch(
            id=UUID(batch.id),
            base_currency_id=base_currency_id,
            base_code=batch.base_code,
            source=batch.source,
            fetched_at=batch.fetched_at.replace(tzinfo=UTC),
            fetched_by=UUID(batch.fetched_by),
            missing_codes=tuple(batch.missing_codes),
            rates=tuple(
                ExchangeRate(
                    base_code=batch.base_code,
                    quote_code=row.quote_code,
                    date=row.date,
                    rate=row.rate,
                )
                for row in rows
            ),
        )

    def save_currency_rates(self, batch: CurrencyRateBatch) -> None:
        self.session.add(
            CurrencyRateBatchModel(
                id=str(batch.id),
                base_currency_id=str(batch.base_currency_id),
                base_code=batch.base_code,
                source=batch.source,
                fetched_at=batch.fetched_at,
                fetched_by=str(batch.fetched_by),
                missing_codes=list(batch.missing_codes),
            )
        )
        self.session.flush()
        self.session.add_all(
            [
                CurrencyRateModel(
                    batch_id=str(batch.id),
                    quote_code=rate.quote_code,
                    date=rate.date,
                    rate=rate.rate,
                )
                for rate in batch.rates
            ]
        )
        self.session.flush()

    def save(self, kind: str, item: Record, expected_version: int | None) -> None:
        if expected_version is None:
            self.session.add(MODELS[kind](**model_values(item)))
        else:
            result = self.session.execute(
                update(MODELS[kind])
                .where(MODELS[kind].id == str(item.id), MODELS[kind].version == expected_version)
                .values(**model_values(item))
            )
            if result.rowcount != 1:
                raise ConflictError("Configuration was changed concurrently")
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Configuration conflicts with an existing record") from exc

    def similar(self, kind: str, item: Record) -> list[dict]:
        model = MODELS[kind]
        clauses = [model.name.icontains(item.name, autoescape=True)]
        if kind == "counterparties":
            if item.tax_identifier:
                clauses.append(model.tax_identifier == item.tax_identifier)
            if item.registration_identifier:
                clauses.append(model.registration_identifier == item.registration_identifier)
        query = select(model).where(model.id != str(item.id), or_(*clauses)).order_by(model.id)
        return [
            {"id": row.id, "code": row.code, "name": row.name}
            for row in self.session.scalars(query.limit(20))
        ]

    def mappings(self, kind: str, item_id: UUID) -> list[dict]:
        rows = self.session.scalars(
            select(ExternalMappingModel)
            .where(
                ExternalMappingModel.kind == kind, ExternalMappingModel.record_id == str(item_id)
            )
            .order_by(ExternalMappingModel.source, ExternalMappingModel.external_id)
        )
        return [{"source": row.source, "external_id": row.external_id} for row in rows]

    def set_mapping(
        self, kind: str, item_id: UUID, source: str, external_id: str, actor_id: UUID
    ) -> dict:
        source, external_id = source.strip().lower(), external_id.strip()
        if not source or len(source) > 128 or not external_id or len(external_id) > 255:
            raise ValidationError("Invalid external identifier")
        row = self.session.scalar(
            select(ExternalMappingModel)
            .where(
                ExternalMappingModel.kind == kind,
                ExternalMappingModel.source == source,
                ExternalMappingModel.external_id == external_id,
            )
            .with_for_update()
        )
        if row is not None and row.record_id != str(item_id):
            raise ConflictError("External identifier is already mapped to another record")
        if row is None:
            self.session.add(
                ExternalMappingModel(
                    id=str(uuid4()),
                    kind=kind,
                    record_id=str(item_id),
                    source=source,
                    external_id=external_id,
                    created_by=str(actor_id),
                    created_at=now(),
                )
            )
        return {"source": source, "external_id": external_id}

    def audit(self, kind: str, before: Record | None, after: Record, actor_id: UUID) -> None:
        self.session.add(
            ConfigurationAuditModel(
                id=str(uuid4()),
                kind=kind,
                record_id=str(after.id),
                actor_id=str(actor_id),
                changed_at=now(),
                before=snapshot(before),
                after=snapshot(after),
            )
        )

    def history(self, kind: str, item_id: UUID, limit: int, offset: int) -> list[dict]:
        rows = self.session.scalars(
            select(ConfigurationAuditModel)
            .where(
                ConfigurationAuditModel.kind == kind,
                ConfigurationAuditModel.record_id == str(item_id),
            )
            .order_by(ConfigurationAuditModel.changed_at.desc(), ConfigurationAuditModel.id)
            .limit(limit)
            .offset(offset)
        )
        return [
            dict(
                id=row.id,
                actor_id=row.actor_id,
                changed_at=row.changed_at,
                before=row.before,
                after=row.after,
            )
            for row in rows
        ]

    def negative_stock_overrides_enabled(self) -> bool:
        rows = self.session.scalars(
            select(SettingValueModel)
            .join(SettingDefinitionModel)
            .where(SettingDefinitionModel.key == "inventory.negative_stock_allowed")
            .with_for_update()
        )
        return any(row.value is True for row in rows)

    def referenced(self, kind: str, item_id: UUID) -> bool:
        if kind == "storage-analytics":
            return (
                self.session.scalar(
                    select(StorageAnalyticValueModel.id)
                    .with_for_update()
                    .where(
                        StorageAnalyticValueModel.definition_id == str(item_id),
                        StorageAnalyticValueModel.active.is_(True),
                    )
                    .limit(1)
                )
                is not None
            )
        if kind == "vat-rates":
            from warehouse_erp.catalog.infrastructure.models import ProductModel

            if (
                self.session.scalar(
                    select(ProductModel.id)
                    .with_for_update()
                    .where(ProductModel.default_vat_rate_id == str(item_id))
                    .limit(1)
                )
                is not None
            ):
                return True
        column = {
            "currencies": AccountingSettingsModel.currency_id,
            "vat-rates": AccountingSettingsModel.default_vat_rate_id,
        }.get(kind)
        return (
            column is not None
            and self.session.scalar(
                select(AccountingSettingsModel.id)
                .with_for_update()
                .where(column == str(item_id))
                .limit(1)
            )
            is not None
        )


class SqlAlchemyConfigurationUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.records = SqlAlchemyConfigurationRepository(session)

    def commit(self) -> None:
        try:
            self.session.commit()
            self.records.locked = False
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Configuration conflicts with an existing record") from exc

    def rollback(self) -> None:
        self.session.rollback()
        self.records.locked = False


def seed_configuration_defaults(session: Session) -> None:
    if session.get(ConfigurationGuardModel, 1) is None:
        session.add(ConfigurationGuardModel(id=1))
    for section, cls in SETTINGS.items():
        item_id = settings_id(section)
        if session.get(MODELS[section], str(item_id)) is None:
            session.add(MODELS[section](**model_values(cls(id=item_id))))
    for document_type in DocumentType:
        item_id = settings_id(f"numbering/{document_type.value}")
        if session.get(MODELS["numbering"], str(item_id)) is None:
            item = DocumentNumbering(id=item_id, document_type=document_type)
            session.add(MODELS["numbering"](**model_values(item)))
    session.flush()
