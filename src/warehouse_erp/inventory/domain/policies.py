from dataclasses import dataclass
from enum import StrEnum

from warehouse_erp.shared.errors import ValidationError


class TrackingMode(StrEnum):
    NONE = "NONE"
    BATCH = "BATCH"


class IssueStrategy(StrEnum):
    MANUAL = "MANUAL"
    FIFO = "FIFO"
    FEFO = "FEFO"


@dataclass(frozen=True, slots=True)
class WarehouseInventoryPolicy:
    tracking_mode: TrackingMode = TrackingMode.NONE
    issue_strategy: IssueStrategy = IssueStrategy.MANUAL

    def __post_init__(self) -> None:
        if (
            self.tracking_mode is TrackingMode.NONE
            and self.issue_strategy is not IssueStrategy.MANUAL
        ):
            raise ValidationError("FIFO/FEFO require BATCH tracking on the warehouse")

    def validate_product(self, *, batch_expiry_required: bool) -> None:
        if batch_expiry_required and self.tracking_mode is not TrackingMode.BATCH:
            raise ValidationError("Product requiring expiry needs a BATCH warehouse")

    def validate_transfer_to(self, destination: "WarehouseInventoryPolicy") -> None:
        if self.tracking_mode is not destination.tracking_mode:
            raise ValidationError("Transfers between NONE and BATCH warehouses are not supported")
