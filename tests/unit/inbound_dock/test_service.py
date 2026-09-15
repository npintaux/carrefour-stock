"""Unit tests for InboundDockService application service."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.modules.inbound_dock.adapters.memory_repository import (
    InMemoryInboundShipmentRepository,
)
from src.modules.inbound_dock.adapters.service import InboundDockService
from src.modules.inbound_dock.domain.barcode_validator import BarcodeValidator
from src.modules.inbound_dock.domain.exceptions import (
    InvalidBarcodeError,
    InvalidTransitionError,
    ShipmentNotFoundError,
)
from src.modules.inbound_dock.domain.models import PalletLifecycleState


def test_us3_ac3_1_service_ingest_and_receive_compliant() -> None:
    """[US-3][AC-3.1] Test ASN ingestion and receiving compliant chilled pallet."""
    repo = InMemoryInboundShipmentRepository()
    service = InboundDockService(repository=repo)
    validator = BarcodeValidator()

    sscc_prefix = "03760000000000001"
    sscc = f"{sscc_prefix}{validator.calculate_sscc_check_digit(sscc_prefix)}"
    ean_prefix = "356007000001"
    ean = f"{ean_prefix}{validator.calculate_ean13_check_digit(ean_prefix)}"

    shipment = service.ingest_asn(
        idempotency_key="550e8400-e29b-41d4-a716-446655440001",
        asn_id="ASN-101",
        store_id="STORE_FR_75015",
        supplier_id="SUP-001",
        expected_delivery=datetime.now(timezone.utc),
        pallets_data=[
            {
                "sscc": sscc,
                "temperature_regime": "CHILLED",
                "lines": [
                    {
                        "sku": "SKU-MILK",
                        "ean13": ean,
                        "expected_quantity": 20,
                        "lot_number": "LOT-1",
                        "bbd": "2026-10-15",
                    }
                ],
            }
        ],
    )
    assert shipment.asn_id == "ASN-101"

    # Replay idempotency
    shipment_replay = service.ingest_asn(
        idempotency_key="550e8400-e29b-41d4-a716-446655440001",
        asn_id="ASN-101",
        store_id="STORE_FR_75015",
        supplier_id="SUP-001",
        expected_delivery=datetime.now(timezone.utc),
        pallets_data=[],
    )
    assert shipment_replay.asn_id == "ASN-101"

    # Receive pallet compliant
    res, is_compliant = service.receive_pallet(
        asn_id="ASN-101",
        sscc=sscc,
        store_id="STORE_FR_75015",
        operator_id="OP_1",
        probed_temperature=2.5,
    )
    assert is_compliant is True
    assert res.to_state == PalletLifecycleState.BACKROOM_STAGING
    assert res.target_location == "COLD_STORAGE_RESERVE"

    # Re-receiving pallet should trigger InvalidTransitionError
    with pytest.raises(InvalidTransitionError, match="already in state"):
        service.receive_pallet(
            asn_id="ASN-101",
            sscc=sscc,
            store_id="STORE_FR_75015",
            operator_id="OP_1",
            probed_temperature=2.5,
        )


def test_us3_ac3_1_service_receive_breach_and_damage() -> None:
    """[US-3][AC-3.1] Test cold chain violation and damage handling in service."""
    repo = InMemoryInboundShipmentRepository()
    service = InboundDockService(repository=repo)
    validator = BarcodeValidator()

    sscc1 = (
        f"03760000000000001{validator.calculate_sscc_check_digit('03760000000000001')}"
    )
    sscc2 = (
        f"03760000000000002{validator.calculate_sscc_check_digit('03760000000000002')}"
    )

    service.ingest_asn(
        idempotency_key="key-1",
        asn_id="ASN-202",
        store_id="STORE_1",
        supplier_id="SUP_1",
        expected_delivery=datetime.now(timezone.utc),
        pallets_data=[
            {
                "sscc": sscc1,
                "temperature_regime": "CHILLED",
                "lines": [],
            },
            {
                "sscc": sscc2,
                "temperature_regime": "AMBIENT",
                "lines": [],
            },
        ],
    )

    # Cold chain breach: 7.5°C
    res1, compliant1 = service.receive_pallet(
        asn_id="ASN-202",
        sscc=sscc1,
        store_id="STORE_1",
        operator_id="OP_1",
        probed_temperature=7.5,
    )
    assert compliant1 is False
    assert res1.to_state == PalletLifecycleState.STATUS_QUARANTINE
    assert res1.target_location == "QUARANTINE_DAMAGED"
    assert res1.violation_reason == "COLD_CHAIN_VIOLATION"

    # Damage observed
    res2, compliant2 = service.receive_pallet(
        asn_id="ASN-202",
        sscc=sscc2,
        store_id="STORE_1",
        operator_id="OP_1",
        damage_observed=True,
    )
    assert compliant2 is False
    assert res2.to_state == PalletLifecycleState.STATUS_QUARANTINE
    assert res2.target_location == "QUARANTINE_DAMAGED"


def test_us3_ac3_2_service_errors_and_discrepancy() -> None:
    """[US-3][AC-3.2] Test error cases and discrepancy recording."""
    repo = InMemoryInboundShipmentRepository()
    service = InboundDockService(repository=repo)

    with pytest.raises(ShipmentNotFoundError):
        service.get_asn("STORE_1", "NONEXISTENT")

    with pytest.raises(InvalidBarcodeError):
        service.receive_pallet(
            asn_id="ASN-1",
            sscc="BAD",
            store_id="STORE_1",
            operator_id="OP_1",
        )

    # Discrepancy on non-existent ASN
    with pytest.raises(ShipmentNotFoundError):
        service.record_discrepancy(
            asn_id="NONEXISTENT",
            store_id="STORE_1",
            discrepancy_type="DAMAGE",
            reason_code="DAMAGED_CRUSHED",
            reported_by="OP_1",
        )
