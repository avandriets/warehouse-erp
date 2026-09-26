from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from warehouse_erp.database import Base


class SettingsCategoryModel(Base):
    __tablename__ = "settings_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SettingDefinitionModel(Base):
    __tablename__ = "settings_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("settings_categories.id", ondelete="RESTRICT"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    default_value: Mapped[Any | None] = mapped_column(JSON)
    allowed_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "value_type IN ('BOOLEAN', 'INTEGER', 'DECIMAL', 'STRING', 'ENUM')",
            name="ck_settings_definition_type",
        ),
        Index("ix_settings_definitions_category", "category_id"),
    )


class SettingValueModel(Base):
    __tablename__ = "settings_values"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    definition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("settings_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(36))
    scope_key: Mapped[str] = mapped_column(String(36), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('GLOBAL', 'COMPANY', 'WAREHOUSE', 'CATEGORY', 'PRODUCT')",
            name="ck_settings_value_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'GLOBAL' AND scope_id IS NULL AND scope_key = 'GLOBAL') OR "
            "(scope_type != 'GLOBAL' AND scope_id IS NOT NULL AND scope_key = scope_id)",
            name="ck_settings_value_scope",
        ),
        CheckConstraint("version >= 1", name="ck_settings_value_version"),
        UniqueConstraint(
            "definition_id", "scope_type", "scope_key", name="uq_settings_value_target"
        ),
        Index("ix_settings_values_lookup", "definition_id", "scope_type", "scope_key"),
    )
