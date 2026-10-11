from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from warehouse_erp.database import Base


class LegacyInventoryPolicyModel(Base):
    """Migration archive only; never used to resolve active inventory policies."""

    __tablename__ = "inventory_policy_legacy"

    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
