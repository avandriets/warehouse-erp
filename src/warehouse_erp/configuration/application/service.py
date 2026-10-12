from dataclasses import replace
from uuid import NAMESPACE_URL, UUID, uuid5

from warehouse_erp.configuration.domain.entities import (
    DIRECTORIES,
    AccountingSettings,
    DocumentType,
    Record,
    StorageAnalytic,
    StorageAnalyticValue,
    now,
    validate_analytic_value,
)
from warehouse_erp.configuration.domain.repositories import ConfigurationUnitOfWork
from warehouse_erp.shared.errors import ConflictError, NotFoundError, ValidationError


def settings_id(section: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"warehouse-erp/configuration/{section}")


class ConfigurationService:
    def __init__(self, uow: ConfigurationUnitOfWork) -> None:
        self.uow = uow

    def get(self, kind: str, item_id: UUID) -> Record:
        item = self.uow.records.get(kind, item_id)
        if item is None:
            raise NotFoundError("Configuration record not found")
        return item

    def list(self, kind: str, **filters) -> list[Record]:
        return self.uow.records.list(kind, **filters)

    def list_page(
        self, kind: str, *, q: str | None, active: bool | None, limit: int, offset: int
    ) -> tuple[list[Record], int]:
        filters = dict(q=q, active=active, definition_id=None)
        items = self.uow.records.list(kind, **filters, limit=limit, offset=offset)
        total = self.uow.records.count(kind, **filters)
        return items, total

    def create(self, kind: str, values: dict, actor_id: UUID) -> Record:
        self.uow.records.lock()
        item = self.prepare_create(kind, values, actor_id)
        self.uow.records.save(kind, item, None)
        self.uow.records.audit(kind, None, item, actor_id)
        self.uow.commit()
        return item

    def prepare_create(self, kind: str, values: dict, actor_id: UUID) -> Record:
        item = DIRECTORIES[kind](**values, created_by=actor_id, updated_by=actor_id)
        definition_id = getattr(item, "definition_id", None)
        if self.uow.records.get_by_code(kind, item.code, definition_id):
            raise ConflictError("Directory code already exists")
        self._validate(kind, item, None)
        return item

    def update(
        self, kind: str, item_id: UUID, changes: dict, expected_version: int, actor_id: UUID
    ) -> Record:
        self.uow.records.lock()
        before, item = self.prepare_update(kind, item_id, changes, expected_version, actor_id)
        self.uow.records.save(kind, item, expected_version)
        self.uow.records.audit(kind, before, item, actor_id)
        self.uow.commit()
        return item

    def prepare_update(
        self, kind: str, item_id: UUID, changes: dict, expected_version: int, actor_id: UUID
    ) -> tuple[Record, Record]:
        if set(changes) & {
            "id",
            "version",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "code",
            "definition_id",
            "document_type",
        }:
            raise ValidationError("Record identity and audit fields are immutable")
        before = self.get(kind, item_id)
        if before.version != expected_version:
            raise ConflictError("Configuration version does not match")
        item = replace(
            before, **changes, version=before.version + 1, updated_at=now(), updated_by=actor_id
        )
        self._validate(kind, item, before)
        return before, item

    def import_records(
        self, kind: str, rows: list[dict], actor_id: UUID, *, dry_run: bool, errors: list[dict]
    ) -> dict:
        self.uow.records.lock()
        prepared = []
        seen_ids, seen_codes = set(), set()
        results = []
        for row in rows:
            index, values = row["row"], dict(row["values"])
            item_id = row.get("id")
            before = self.uow.records.get(kind, item_id) if item_id else None
            try:
                if item_id in seen_ids:
                    raise ConflictError("Duplicate identifier in import")
                if item_id is not None:
                    seen_ids.add(item_id)
                if before is not None:
                    if values.pop("code").upper().strip() != before.code:
                        raise ValidationError("Import cannot change stable codes")
                    if "definition_id" in values:
                        if values.pop("definition_id") != before.definition_id:
                            raise ValidationError("Import cannot change analytic definition")
                    expected = row.get("expected_version")
                    if expected is None:
                        expected = row.get("source_version")
                    if expected is None:
                        raise ConflictError("Updating imports requires expected_version")
                    before, item = self.prepare_update(kind, item_id, values, expected, actor_id)
                else:
                    if row.get("expected_version") is not None:
                        raise ConflictError("Record for imported version does not exist")
                    if item_id is not None:
                        values["id"] = item_id
                    item = self.prepare_create(kind, values, actor_id)
                key = (getattr(item, "definition_id", None), item.code)
                if key in seen_codes:
                    raise ConflictError("Duplicate code in import")
                seen_codes.add(key)
                warnings = self.uow.records.similar(kind, item)
                prepared.append((before, item))
                results.append(
                    {
                        "row": index,
                        "id": str(item.id),
                        "warnings": warnings,
                        "record": item,
                        "before": before,
                    }
                )
            except (ValidationError, ConflictError, NotFoundError) as exc:
                errors.append({"row": index, "message": str(exc)})
        applied = not dry_run and not errors
        if applied:
            for before, item in prepared:
                self.uow.records.save(kind, item, before.version if before else None)
                self.uow.records.audit(kind, before, item, actor_id)
            self.uow.commit()
        return {
            "dry_run": dry_run,
            "applied": applied,
            "valid": not errors,
            "records": results,
            "errors": sorted(errors, key=lambda r: r["row"]),
        }

    def section(self, section: str) -> Record:
        return self.get(section, settings_id(section))

    def numbering(self) -> list[Record]:
        return [self.get("numbering", settings_id(f"numbering/{t.value}")) for t in DocumentType]

    def update_numbering(
        self, document_type: DocumentType, changes: dict, expected_version: int, actor_id: UUID
    ) -> Record:
        return self.update(
            "numbering",
            settings_id(f"numbering/{document_type.value}"),
            changes,
            expected_version,
            actor_id,
        )

    def _active_reference(self, kind: str, item_id: UUID) -> Record:
        item = self.get(kind, item_id)
        if not item.active:
            raise ValidationError("Referenced directory record is inactive")
        return item

    def _validate(self, kind: str, item: Record, before: Record | None) -> None:
        if isinstance(item, StorageAnalyticValue):
            definition = self._active_reference("storage-analytics", item.definition_id)
            validate_analytic_value(definition, item)
        if isinstance(item, StorageAnalytic) and before is not None:
            values = self.uow.records.list(
                "storage-analytic-values",
                q=None,
                active=None,
                definition_id=item.id,
                limit=1,
                offset=0,
            )
            if values and item.value_type != before.value_type:
                raise ConflictError("Analytic type cannot change after values exist")
            if values and not set(before.options).issubset(item.options):
                raise ConflictError("Existing analytic enum options cannot be removed")
        if hasattr(item, "active") and before is not None and before.active and not item.active:
            if self.uow.records.referenced(kind, item.id):
                raise ConflictError("Record is selected in settings; replace the reference first")
        if isinstance(item, AccountingSettings):
            if item.currency_id is not None:
                self._active_reference("currencies", item.currency_id)
            if item.default_vat_rate_id is not None:
                self._active_reference("vat-rates", item.default_vat_rate_id)
            if item.cost_accounting_enabled and self.uow.records.negative_stock_overrides_enabled():
                raise ConflictError(
                    "Disable negative-stock overrides before enabling cost accounting"
                )
