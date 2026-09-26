from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from warehouse_erp.settings.infrastructure.models import (
    SettingDefinitionModel,
    SettingsCategoryModel,
)


def _id(kind: str, code: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"warehouse-erp/{kind}/{code}"))


def seed_settings_defaults(session: Session) -> None:
    """Mirror the migration's built-in definitions for test databases."""
    now = datetime.now(UTC)
    category_id = _id("settings-category", "inventory")
    if session.get(SettingsCategoryModel, category_id) is None:
        session.add(
            SettingsCategoryModel(
                id=category_id, code="inventory", name="Inventory", created_at=now
            )
        )
    session.flush()
    scopes = ["GLOBAL", "COMPANY", "WAREHOUSE", "CATEGORY", "PRODUCT"]
    definitions = (
        (
            "inventory.default_issue_strategy",
            "Default stock issue strategy",
            "ENUM",
            "MANUAL",
            ["MANUAL", "FIFO", "FEFO"],
        ),
        (
            "inventory.negative_stock_allowed",
            "Allow negative stock by default",
            "BOOLEAN",
            False,
            [],
        ),
    )
    for key, name, value_type, default_value, options in definitions:
        item_id = _id("setting", key)
        if session.get(SettingDefinitionModel, item_id) is None:
            session.add(
                SettingDefinitionModel(
                    id=item_id,
                    category_id=category_id,
                    key=key,
                    name=name,
                    value_type=value_type,
                    default_value=default_value,
                    allowed_scopes=scopes,
                    is_required=True,
                    options=options,
                    created_at=now,
                )
            )
    session.commit()
