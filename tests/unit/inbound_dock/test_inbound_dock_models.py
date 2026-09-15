"""Unit tests for inbound_dock domain models and exceptions."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.modules.inbound_dock.domain.exceptions import (
    ColdChainViolationError,
    DatabaseAdapterError,
    InboundDockError,
    InvalidBarcodeError,
    InvalidTransitionError,
    MissingTemperatureError,
    PalletNotFoundError,
    ShipmentNotFoundError,
)
from src.modules.inbound_dock.domain.models import (
    AsnLineItem,
    PalletEntity,
    PalletEvent,
    PalletEventType,
    PalletLifecycleState,
    TemperatureRegime,
    TransitionResult,
)


def test_us3_ac3_1_models_instantiation() -> None:
    """[US-3][AC-3.1] Verify domain models can be instantiated with frozen immutability."""
    line = AsnLineItem(
        sku="SKU-001",
        ean13="3560070000014",
        expected_quantity=10,
        lot_number="LOT-2026",
        bbd="2026-12-31",
    )
    assert line.sku == "SKU-001"
    with pytest.raises(FrozenInstanceError):
        line.sku = "MUTATED"  # type: ignore[misc]

    pallet = PalletEntity(
        sscc="037600000000000017",
        asn_id="ASN-100",
        temperature_regime=TemperatureRegime.CHILLED,
        state=PalletLifecycleState.EXPECTED,
        lines=(line,),
    )
    assert pallet.state == PalletLifecycleState.EXPECTED
    assert pallet.temperature_regime == TemperatureRegime.CHILLED

    event = PalletEvent(
        event_type=PalletEventType.SCAN,
        entity_id="037600000000000017",
        store_id="STORE_FR_75015",
        operator_id="OP_123",
        probed_temperature=2.5,
    )
    assert event.probed_temperature == 2.5

    res = TransitionResult(
        success=True,
        from_state=PalletLifecycleState.EXPECTED,
        to_state=PalletLifecycleState.IN_RECEIVING,
        target_location="BACKROOM_STAGING",
        message="Pallet scanned",
    )
    assert res.success is True


def test_us3_ac3_1_exceptions_hierarchy() -> None:
    """[US-3][AC-3.1] Verify exception hierarchy and error codes."""
    err = InvalidBarcodeError("Bad barcode")
    assert isinstance(err, InboundDockError)
    assert err.code == "INVALID_SSCC_BARCODE"

    err2 = MissingTemperatureError("Temp missing")
    assert err2.code == "MISSING_PROBE_TEMPERATURE"

    err3 = ShipmentNotFoundError("Not found")
    assert err3.code == "SHIPMENT_NOT_FOUND"

    err4 = PalletNotFoundError("Pallet not found")
    assert err4.code == "PALLET_NOT_FOUND"

    err5 = InvalidTransitionError("Conflict")
    assert err5.code == "STATE_CONFLICT"

    err6 = ColdChainViolationError("Cold chain breached")
    assert err6.code == "COLD_CHAIN_VIOLATION"

    err7 = DatabaseAdapterError("DB failed")
    assert err7.code == "INTERNAL_DATABASE_ERROR"
