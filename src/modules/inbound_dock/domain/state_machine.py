"""Deterministic finite state machine for inbound pallet lifecycle."""

from __future__ import annotations

from typing import ClassVar

from .exceptions import InvalidTransitionError
from .models import (
    PalletEntity,
    PalletEvent,
    PalletEventType,
    PalletLifecycleState,
    TemperatureRegime,
    TransitionResult,
)


class InboundPalletStateMachine:
    """Manages deterministic lifecycle transitions and guards for inbound pallets."""

    # Explicit transition matrix: (FromState, EventType) -> ToState
    _TRANSITION_TABLE: ClassVar[
        dict[tuple[PalletLifecycleState, PalletEventType], PalletLifecycleState]
    ] = {
        (
            PalletLifecycleState.EXPECTED,
            PalletEventType.SCAN,
        ): PalletLifecycleState.IN_RECEIVING,
        (
            PalletLifecycleState.IN_RECEIVING,
            PalletEventType.PASS_INSPECTION,
        ): PalletLifecycleState.BACKROOM_STAGING,
        (
            PalletLifecycleState.IN_RECEIVING,
            PalletEventType.FAIL_COLD_CHAIN,
        ): PalletLifecycleState.STATUS_QUARANTINE,
        (
            PalletLifecycleState.IN_RECEIVING,
            PalletEventType.FLAG_DAMAGE,
        ): PalletLifecycleState.STATUS_QUARANTINE,
        (
            PalletLifecycleState.STATUS_QUARANTINE,
            PalletEventType.RETURN_TO_VENDOR,
        ): PalletLifecycleState.REJECTED_RTV,
    }

    def can_transition(
        self, from_state: PalletLifecycleState, event_type: PalletEventType
    ) -> bool:
        """Check if transition from current state via event_type is permitted.

        Args:
            from_state: The current lifecycle state of the pallet.
            event_type: The candidate event triggering transition.

        Returns:
            True if transition is valid, False otherwise.
        """
        return (from_state, event_type) in self._TRANSITION_TABLE

    def process_event(
        self, pallet: PalletEntity, event: PalletEvent
    ) -> TransitionResult:
        """Execute state transition on a pallet entity driven by event.

        Args:
            pallet: The pallet entity being transitioned.
            event: The domain event driving the transition.

        Returns:
            TransitionResult describing from_state, to_state, target_location, and message.

        Raises:
            InvalidTransitionError: If the transition is illegal from pallet's current state.
        """
        key = (pallet.state, event.event_type)
        if key not in self._TRANSITION_TABLE:
            raise InvalidTransitionError(
                f"Illegal state transition: cannot apply event '{event.event_type.name}' "
                f"to pallet in state '{pallet.state.name}'"
            )

        target_state = self._TRANSITION_TABLE[key]

        # Determine target location based on resulting state and temperature regime
        target_location = "BACKROOM_STAGING"
        violation_reason = None

        if target_state == PalletLifecycleState.BACKROOM_STAGING:
            if pallet.temperature_regime in (
                TemperatureRegime.CHILLED,
                TemperatureRegime.FROZEN,
            ):
                target_location = "COLD_STORAGE_RESERVE"
            else:
                target_location = "BACKROOM_STAGING"
        elif target_state in (
            PalletLifecycleState.STATUS_QUARANTINE,
            PalletLifecycleState.REJECTED_RTV,
        ):
            target_location = "QUARANTINE_DAMAGED"
            if event.event_type == PalletEventType.FAIL_COLD_CHAIN:
                violation_reason = "COLD_CHAIN_VIOLATION"
            elif event.event_type == PalletEventType.FLAG_DAMAGE:
                violation_reason = "DAMAGED_CRUSHED"

        return TransitionResult(
            success=True,
            from_state=pallet.state,
            to_state=target_state,
            target_location=target_location,
            message=f"Pallet transitioned to {target_state.name}",
            violation_reason=violation_reason,
        )
