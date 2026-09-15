"""Domain models for inbound dock receiving and cold-chain evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto


class TemperatureRegime(Enum):
    """Cold-chain classification regimes."""

    AMBIENT = "AMBIENT"
    CHILLED = "CHILLED"
    FROZEN = "FROZEN"


class PalletLifecycleState(Enum):
    """Lifecycle states of an inbound pallet."""

    EXPECTED = auto()
    IN_RECEIVING = auto()
    BACKROOM_STAGING = auto()
    STATUS_QUARANTINE = auto()
    REJECTED_RTV = auto()


class PalletEventType(Enum):
    """Domain events driving pallet lifecycle transitions."""

    SCAN = auto()
    PASS_INSPECTION = auto()
    FAIL_COLD_CHAIN = auto()
    FLAG_DAMAGE = auto()
    RETURN_TO_VENDOR = auto()


@dataclass(frozen=True)
class AsnLineItem:
    """Individual product line item on an ASN manifest."""

    sku: str
    ean13: str
    expected_quantity: int
    lot_number: str
    bbd: str  # YYYY-MM-DD


@dataclass(frozen=True)
class PalletEntity:
    """Inbound pallet container domain entity."""

    sscc: str
    asn_id: str
    temperature_regime: TemperatureRegime
    state: PalletLifecycleState
    lines: tuple[AsnLineItem, ...]
    probed_temperature: float | None = None
    received_at: datetime | None = None
    rejection_reason: str | None = None


@dataclass(frozen=True)
class PalletEvent:
    """Event triggering a pallet state transition."""

    event_type: PalletEventType
    entity_id: str  # SSCC
    store_id: str
    operator_id: str
    probed_temperature: float | None = None
    damage_observed: bool = False
    notes: str | None = None


@dataclass(frozen=True)
class TransitionResult:
    """Result of state machine evaluation."""

    success: bool
    from_state: PalletLifecycleState
    to_state: PalletLifecycleState
    target_location: str
    message: str
    violation_reason: str | None = None


@dataclass(frozen=True)
class AsnShipmentEntity:
    """Inbound ASN shipment domain entity."""

    asn_id: str
    store_id: str
    supplier_id: str
    expected_delivery: datetime
    status: str
    pallets: tuple[PalletEntity, ...]


@dataclass(frozen=True)
class DiscrepancyClaimEntity:
    """Discrepancy record domain entity."""

    discrepancy_id: str
    asn_id: str
    store_id: str
    discrepancy_type: str
    reason_code: str
    reported_by: str
    affected_quantity: int
    status: str
    created_at: datetime
    sscc: str | None = None
    sku: str | None = None
    photo_evidence_url: str | None = None
    notes: str | None = None
