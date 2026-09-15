"""Unit tests for InboundPalletStateMachine."""

from __future__ import annotations

import pytest

from src.modules.inbound_dock.domain.exceptions import InvalidTransitionError
from src.modules.inbound_dock.domain.models import (
    PalletEntity,
    PalletEvent,
    PalletEventType,
    PalletLifecycleState,
    TemperatureRegime,
)
from src.modules.inbound_dock.domain.state_machine import InboundPalletStateMachine


def test_us3_ac3_1_state_machine_happy_path_ambient() -> None:
    """[US-3][AC-3.1] Happy path: EXPECTED -> IN_RECEIVING -> BACKROOM_STAGING."""
    sm = InboundPalletStateMachine()
    pallet = PalletEntity(
        sscc="037600000000000017",
        asn_id="ASN-1",
        temperature_regime=TemperatureRegime.AMBIENT,
        state=PalletLifecycleState.EXPECTED,
        lines=(),
    )
    scan_event = PalletEvent(
        event_type=PalletEventType.SCAN,
        entity_id="037600000000000017",
        store_id="STORE_1",
        operator_id="OP_1",
    )
    res = sm.process_event(pallet, scan_event)
    assert res.success is True
    assert res.to_state == PalletLifecycleState.IN_RECEIVING

    # Next: pass inspection
    receiving_pallet = PalletEntity(
        sscc="037600000000000017",
        asn_id="ASN-1",
        temperature_regime=TemperatureRegime.AMBIENT,
        state=PalletLifecycleState.IN_RECEIVING,
        lines=(),
    )
    pass_event = PalletEvent(
        event_type=PalletEventType.PASS_INSPECTION,
        entity_id="037600000000000017",
        store_id="STORE_1",
        operator_id="OP_1",
    )
    res2 = sm.process_event(receiving_pallet, pass_event)
    assert res2.success is True
    assert res2.to_state == PalletLifecycleState.BACKROOM_STAGING
    assert res2.target_location == "BACKROOM_STAGING"


def test_us3_ac3_1_state_machine_chilled_staging() -> None:
    """[US-3][AC-3.1] Chilled compliant pallet targets COLD_STORAGE_RESERVE."""
    sm = InboundPalletStateMachine()
    chilled_pallet = PalletEntity(
        sscc="037600000000000017",
        asn_id="ASN-1",
        temperature_regime=TemperatureRegime.CHILLED,
        state=PalletLifecycleState.IN_RECEIVING,
        lines=(),
    )
    pass_event = PalletEvent(
        event_type=PalletEventType.PASS_INSPECTION,
        entity_id="037600000000000017",
        store_id="STORE_1",
        operator_id="OP_1",
        probed_temperature=2.5,
    )
    res = sm.process_event(chilled_pallet, pass_event)
    assert res.to_state == PalletLifecycleState.BACKROOM_STAGING
    assert res.target_location == "COLD_STORAGE_RESERVE"


def test_us3_ac3_1_state_machine_cold_chain_breach_quarantine() -> None:
    """[US-3][AC-3.1] Cold-chain breach transitions IN_RECEIVING to STATUS_QUARANTINE."""
    sm = InboundPalletStateMachine()
    pallet = PalletEntity(
        sscc="037600000000000017",
        asn_id="ASN-1",
        temperature_regime=TemperatureRegime.CHILLED,
        state=PalletLifecycleState.IN_RECEIVING,
        lines=(),
    )
    fail_event = PalletEvent(
        event_type=PalletEventType.FAIL_COLD_CHAIN,
        entity_id="037600000000000017",
        store_id="STORE_1",
        operator_id="OP_1",
        probed_temperature=7.5,
    )
    res = sm.process_event(pallet, fail_event)
    assert res.to_state == PalletLifecycleState.STATUS_QUARANTINE
    assert res.target_location == "QUARANTINE_DAMAGED"
    assert res.violation_reason == "COLD_CHAIN_VIOLATION"


def test_us3_ac3_1_state_machine_flag_damage_quarantine() -> None:
    """[US-3][AC-3.1] Damage observed transitions IN_RECEIVING to STATUS_QUARANTINE."""
    sm = InboundPalletStateMachine()
    pallet = PalletEntity(
        sscc="037600000000000017",
        asn_id="ASN-1",
        temperature_regime=TemperatureRegime.AMBIENT,
        state=PalletLifecycleState.IN_RECEIVING,
        lines=(),
    )
    damage_event = PalletEvent(
        event_type=PalletEventType.FLAG_DAMAGE,
        entity_id="037600000000000017",
        store_id="STORE_1",
        operator_id="OP_1",
        damage_observed=True,
    )
    res = sm.process_event(pallet, damage_event)
    assert res.to_state == PalletLifecycleState.STATUS_QUARANTINE
    assert res.target_location == "QUARANTINE_DAMAGED"


def test_us3_ac3_1_state_machine_quarantine_to_rtv() -> None:
    """[US-3][AC-3.1] Return to vendor transitions STATUS_QUARANTINE to REJECTED_RTV."""
    sm = InboundPalletStateMachine()
    quarantine_pallet = PalletEntity(
        sscc="037600000000000017",
        asn_id="ASN-1",
        temperature_regime=TemperatureRegime.CHILLED,
        state=PalletLifecycleState.STATUS_QUARANTINE,
        lines=(),
    )
    rtv_event = PalletEvent(
        event_type=PalletEventType.RETURN_TO_VENDOR,
        entity_id="037600000000000017",
        store_id="STORE_1",
        operator_id="OP_1",
    )
    res = sm.process_event(quarantine_pallet, rtv_event)
    assert res.to_state == PalletLifecycleState.REJECTED_RTV
    assert res.target_location == "QUARANTINE_DAMAGED"


def test_us3_ac3_1_state_machine_illegal_transition() -> None:
    """[US-3][AC-3.1] Attempting illegal transition raises InvalidTransitionError."""
    sm = InboundPalletStateMachine()
    staged_pallet = PalletEntity(
        sscc="037600000000000017",
        asn_id="ASN-1",
        temperature_regime=TemperatureRegime.AMBIENT,
        state=PalletLifecycleState.BACKROOM_STAGING,
        lines=(),
    )
    scan_event = PalletEvent(
        event_type=PalletEventType.SCAN,
        entity_id="037600000000000017",
        store_id="STORE_1",
        operator_id="OP_1",
    )
    assert (
        sm.can_transition(PalletLifecycleState.BACKROOM_STAGING, PalletEventType.SCAN)
        is False
    )
    with pytest.raises(InvalidTransitionError, match="Illegal state transition"):
        sm.process_event(staged_pallet, scan_event)
