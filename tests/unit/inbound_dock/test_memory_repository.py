"""Unit tests for InMemoryInboundShipmentRepository adapter."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.modules.inbound_dock.adapters.memory_repository import (
    InMemoryInboundShipmentRepository,
)
from src.modules.inbound_dock.domain.exceptions import (
    DuplicateShipmentError,
    PalletNotFoundError,
    ShipmentNotFoundError,
)
from src.modules.inbound_dock.domain.models import (
    AsnLineItem,
    AsnShipmentEntity,
    DiscrepancyClaimEntity,
    PalletEntity,
    PalletLifecycleState,
    TemperatureRegime,
)


def test_us3_ac3_2_memory_repository_crud() -> None:
    """[US-3][AC-3.2] Verify saving and loading shipments and pallets."""
    repo = InMemoryInboundShipmentRepository()
    now = datetime.now(timezone.utc)
    line = AsnLineItem(
        sku="SKU-1",
        ean13="3560070000014",
        expected_quantity=5,
        lot_number="LOT-1",
        bbd="2026-10-01",
    )
    pallet = PalletEntity(
        sscc="037600000000000017",
        asn_id="ASN-1",
        temperature_regime=TemperatureRegime.CHILLED,
        state=PalletLifecycleState.EXPECTED,
        lines=(line,),
    )
    shipment = AsnShipmentEntity(
        asn_id="ASN-1",
        store_id="STORE_1",
        supplier_id="SUP-1",
        expected_delivery=now,
        status="EXPECTED",
        pallets=(pallet,),
    )

    # Save
    repo.save_shipment(shipment)

    # Duplicate check
    with pytest.raises(DuplicateShipmentError, match="already exists"):
        repo.save_shipment(shipment)

    # Get
    retrieved = repo.get_shipment("STORE_1", "ASN-1")
    assert retrieved is not None
    assert retrieved.asn_id == "ASN-1"
    assert len(retrieved.pallets) == 1

    # Update pallet
    updated_pallet = PalletEntity(
        sscc="037600000000000017",
        asn_id="ASN-1",
        temperature_regime=TemperatureRegime.CHILLED,
        state=PalletLifecycleState.BACKROOM_STAGING,
        lines=(line,),
        probed_temperature=2.0,
    )
    repo.update_pallet("STORE_1", "ASN-1", updated_pallet)
    retrieved_after_update = repo.get_shipment("STORE_1", "ASN-1")
    assert retrieved_after_update is not None
    assert (
        retrieved_after_update.pallets[0].state == PalletLifecycleState.BACKROOM_STAGING
    )
    assert retrieved_after_update.pallets[0].probed_temperature == 2.0


def test_us3_ac3_2_memory_repository_errors() -> None:
    """[US-3][AC-3.2] Verify error handling on missing shipment and pallet."""
    repo = InMemoryInboundShipmentRepository()
    line = AsnLineItem(
        sku="SKU-1",
        ean13="3560070000014",
        expected_quantity=5,
        lot_number="LOT-1",
        bbd="2026-10-01",
    )
    pallet = PalletEntity(
        sscc="037600000000000017",
        asn_id="ASN-1",
        temperature_regime=TemperatureRegime.CHILLED,
        state=PalletLifecycleState.EXPECTED,
        lines=(line,),
    )
    with pytest.raises(ShipmentNotFoundError, match="not found"):
        repo.update_pallet("STORE_1", "ASN-NONEXISTENT", pallet)

    # Now create shipment without that SSCC
    shipment = AsnShipmentEntity(
        asn_id="ASN-1",
        store_id="STORE_1",
        supplier_id="SUP-1",
        expected_delivery=datetime.now(timezone.utc),
        status="EXPECTED",
        pallets=(),
    )
    repo.save_shipment(shipment)
    with pytest.raises(PalletNotFoundError, match="not found"):
        repo.update_pallet("STORE_1", "ASN-1", pallet)


def test_us3_ac3_3_memory_repository_idempotency_and_discrepancy() -> None:
    """[US-3][AC-3.3] Verify idempotency token recording and discrepancy logging."""
    repo = InMemoryInboundShipmentRepository()
    key = "550e8400-e29b-41d4-a716-446655440000"
    assert repo.check_idempotency(key) is False
    repo.record_idempotency(key, "CREATED")
    assert repo.check_idempotency(key) is True

    claim = DiscrepancyClaimEntity(
        discrepancy_id="DISC-1",
        asn_id="ASN-1",
        store_id="STORE_1",
        discrepancy_type="DAMAGE",
        reason_code="DAMAGED_CRUSHED",
        reported_by="OP_1",
        affected_quantity=2,
        status="LOGGED",
        created_at=datetime.now(timezone.utc),
    )
    repo.save_discrepancy(claim)
