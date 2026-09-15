"""Domain value objects, entities, and enumerations for the stock ledger subsystem."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class StockZone(str, Enum):
    """Granular multi-zone store sub-location topology (FR-2.1)."""

    RECEIVING_DOCK = "RECEIVING_DOCK"
    COLD_STORAGE_RESERVE = "COLD_STORAGE_RESERVE"
    DRY_RESERVE = "DRY_RESERVE"
    IN_TRANSIT_FLOOR = "IN_TRANSIT_FLOOR"
    SALES_FLOOR_FACING = "SALES_FLOOR_FACING"
    QUARANTINE_DAMAGED = "QUARANTINE_DAMAGED"
    CUSTOMER_CLICK_COLLECT_STAGED = "CUSTOMER_CLICK_COLLECT_STAGED"


class AdjustmentStatus(str, Enum):
    """Lifecycle status of inventory adjustment or shrinkage write-off."""

    AUTO_APPROVED = "AUTO_APPROVED"
    PENDING_DIRECTOR_APPROVAL = "PENDING_DIRECTOR_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ReasonCode(str, Enum):
    """Categorized reason for shrinkage or variance write-off."""

    THEFT = "THEFT"
    BREAKAGE = "BREAKAGE"
    INTERNAL_CONSUMPTION = "INTERNAL_CONSUMPTION"
    MISCOUNT = "MISCOUNT"
    EXPIRY_SPOILAGE = "EXPIRY_SPOILAGE"
    OTHER = "OTHER"


@dataclass(frozen=True)
class StockItem:
    """Immutable stock balance record for a specific SKU and zone."""

    sku_id: str
    ean13: str
    product_name: str
    department_id: str
    zone: StockZone
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True)
class AdjustmentEvaluationRequest:
    """Immutable input payload for adjustment policy rule evaluation."""

    request_id: str
    store_id: str
    sku_id: str
    department_id: str
    zone: StockZone
    quantity_delta: int
    unit_price_cents: int
    reason_code: ReasonCode
    initiator_id: str
    initiator_role: str
    user_departments: tuple[str, ...]
    threshold_cents: int = 50000


@dataclass(frozen=True)
class Decision:
    """Immutable outcome produced by rule evaluation."""

    is_allowed: bool
    status_code: int
    error_code: str | None
    reason: str
    action: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class AdjustmentRecord:
    """Persisted adjustment entity in datastore."""

    adjustment_id: str
    store_id: str
    sku_id: str
    department_id: str
    zone: StockZone
    quantity_delta: int
    unit_price_cents: int
    total_value_cents: int
    reason_code: ReasonCode
    initiator_id: str
    status: AdjustmentStatus
    director_id: str | None = None
    director_note: str | None = None
