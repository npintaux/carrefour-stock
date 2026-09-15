"""Application service coordinator for inbound dock receiving."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.modules.inbound_dock.domain.barcode_validator import BarcodeValidator
from src.modules.inbound_dock.domain.cold_chain_evaluator import ColdChainEvaluator
from src.modules.inbound_dock.domain.exceptions import (
    DuplicateShipmentError,
    InvalidTransitionError,
    MissingTemperatureError,
    PalletNotFoundError,
    ShipmentNotFoundError,
)
from src.modules.inbound_dock.domain.models import (
    AsnLineItem,
    AsnShipmentEntity,
    DiscrepancyClaimEntity,
    PalletEntity,
    PalletEvent,
    PalletEventType,
    PalletLifecycleState,
    TemperatureRegime,
    TransitionResult,
)
from src.modules.inbound_dock.domain.repository import InboundShipmentRepository
from src.modules.inbound_dock.domain.state_machine import InboundPalletStateMachine


class InboundDockService:
    """Coordinates business operations for inbound shipments, pallets, and claims."""

    def __init__(
        self,
        repository: InboundShipmentRepository,
        barcode_validator: BarcodeValidator | None = None,
        cold_chain_evaluator: ColdChainEvaluator | None = None,
        state_machine: InboundPalletStateMachine | None = None,
    ) -> None:
        """Initialize service with domain collaborators and persistence port.

        Args:
            repository: Port for shipment persistence.
            barcode_validator: Domain validator for SSCC and EAN barcodes.
            cold_chain_evaluator: Domain evaluator for cold-chain regimes.
            state_machine: Domain state machine for pallet lifecycle transitions.
        """
        self._repo = repository
        self._barcode_validator = barcode_validator or BarcodeValidator()
        self._cold_chain_evaluator = cold_chain_evaluator or ColdChainEvaluator()
        self._state_machine = state_machine or InboundPalletStateMachine()

    def ingest_asn(
        self,
        idempotency_key: str,
        asn_id: str,
        store_id: str,
        supplier_id: str,
        expected_delivery: datetime,
        pallets_data: list[dict[str, object]],
    ) -> AsnShipmentEntity:
        """Ingest and register a new ASN shipment.

        Args:
            idempotency_key: UUID idempotency token.
            asn_id: Unique ASN identifier.
            store_id: Destination store identifier.
            supplier_id: Supplier identifier.
            expected_delivery: Scheduled delivery timestamp.
            pallets_data: List of pallet manifest dictionaries.

        Returns:
            The created or existing AsnShipmentEntity.

        Raises:
            InvalidBarcodeError: If any pallet SSCC or line EAN is malformed.
        """
        # Check idempotency
        existing = self._repo.get_shipment(store_id, asn_id)
        if existing is not None:
            if self._repo.check_idempotency(idempotency_key):
                return existing
            raise DuplicateShipmentError(
                f"Shipment '{asn_id}' already exists with different idempotency key"
            )

        pallet_entities: list[PalletEntity] = []
        for p in pallets_data:
            sscc = str(p["sscc"])
            self._barcode_validator.validate_sscc(sscc)
            regime_str = str(p["temperature_regime"])
            regime = TemperatureRegime(regime_str)

            lines_data = p.get("lines", [])
            line_entities: list[AsnLineItem] = []
            if isinstance(lines_data, list):
                for item in lines_data:
                    if isinstance(item, dict):
                        ean = str(item["ean13"])
                        self._barcode_validator.validate_ean13(ean)
                        line_entities.append(
                            AsnLineItem(
                                sku=str(item["sku"]),
                                ean13=ean,
                                expected_quantity=int(item["expected_quantity"]),
                                lot_number=str(item["lot_number"]),
                                bbd=str(item["bbd"]),
                            )
                        )

            pallet_entities.append(
                PalletEntity(
                    sscc=sscc,
                    asn_id=asn_id,
                    temperature_regime=regime,
                    state=PalletLifecycleState.EXPECTED,
                    lines=tuple(line_entities),
                )
            )

        shipment = AsnShipmentEntity(
            asn_id=asn_id,
            store_id=store_id,
            supplier_id=supplier_id,
            expected_delivery=expected_delivery,
            status="EXPECTED",
            pallets=tuple(pallet_entities),
        )
        self._repo.save_shipment(shipment)
        self._repo.record_idempotency(idempotency_key, asn_id)
        return shipment

    def get_asn(self, store_id: str, asn_id: str) -> AsnShipmentEntity:
        """Retrieve an ASN shipment by store and ASN ID.

        Args:
            store_id: Store identifier.
            asn_id: ASN identifier.

        Returns:
            AsnShipmentEntity domain entity.

        Raises:
            ShipmentNotFoundError: If the shipment is not found.
        """
        shipment = self._repo.get_shipment(store_id, asn_id)
        if shipment is None:
            raise ShipmentNotFoundError(
                f"Shipment '{asn_id}' not found for store '{store_id}'"
            )
        return shipment

    def receive_pallet(
        self,
        asn_id: str,
        sscc: str,
        store_id: str,
        operator_id: str,
        probed_temperature: float | None = None,
        damage_observed: bool = False,
        notes: str | None = None,
    ) -> tuple[TransitionResult, bool]:
        """Process pallet scan, cold-chain checks, and transition lifecycle state.

        Args:
            asn_id: ASN identifier.
            sscc: Pallet SSCC barcode.
            store_id: Store identifier.
            operator_id: Specialist operator identifier.
            probed_temperature: Probed temperature in °C.
            damage_observed: Whether damage was flagged.
            notes: Optional notes.

        Returns:
            Tuple of (TransitionResult, is_compliant).

        Raises:
            InvalidBarcodeError: If SSCC is invalid.
            ShipmentNotFoundError: If ASN is not found.
            PalletNotFoundError: If pallet SSCC is not part of shipment.
            InvalidTransitionError: If pallet is already received or state conflict.
        """
        self._barcode_validator.validate_sscc(sscc)
        shipment = self.get_asn(store_id, asn_id)

        target_pallet: PalletEntity | None = None
        for p in shipment.pallets:
            if p.sscc == sscc:
                target_pallet = p
                break

        if target_pallet is None:
            raise PalletNotFoundError(
                f"Pallet '{sscc}' not found in shipment '{asn_id}'"
            )

        # Validate temperature presence for chilled / frozen regimes
        if (
            target_pallet.temperature_regime
            in (
                TemperatureRegime.CHILLED,
                TemperatureRegime.FROZEN,
            )
            and probed_temperature is None
        ):
            raise MissingTemperatureError(
                f"Missing probed temperature reading for {target_pallet.temperature_regime.value} pallet"
            )

        if target_pallet.state != PalletLifecycleState.EXPECTED:
            raise InvalidTransitionError(
                f"Pallet '{sscc}' is already in state '{target_pallet.state.name}'"
            )

        # Step 1: Scan event (EXPECTED -> IN_RECEIVING)
        scan_event = PalletEvent(
            event_type=PalletEventType.SCAN,
            entity_id=sscc,
            store_id=store_id,
            operator_id=operator_id,
            probed_temperature=probed_temperature,
            damage_observed=damage_observed,
            notes=notes,
        )
        intermediate_res = self._state_machine.process_event(target_pallet, scan_event)
        in_receiving_pallet = PalletEntity(
            sscc=target_pallet.sscc,
            asn_id=target_pallet.asn_id,
            temperature_regime=target_pallet.temperature_regime,
            state=intermediate_res.to_state,
            lines=target_pallet.lines,
            probed_temperature=probed_temperature,
        )

        # Step 2: Quality & Cold-Chain evaluation
        is_compliant, violation_reason = self._cold_chain_evaluator.evaluate(
            target_pallet.temperature_regime, probed_temperature
        )

        if damage_observed:
            is_compliant = False
            inspection_event = PalletEvent(
                event_type=PalletEventType.FLAG_DAMAGE,
                entity_id=sscc,
                store_id=store_id,
                operator_id=operator_id,
                probed_temperature=probed_temperature,
                damage_observed=True,
                notes=notes,
            )
        elif not is_compliant:
            inspection_event = PalletEvent(
                event_type=PalletEventType.FAIL_COLD_CHAIN,
                entity_id=sscc,
                store_id=store_id,
                operator_id=operator_id,
                probed_temperature=probed_temperature,
                damage_observed=False,
                notes=notes,
            )
        else:
            inspection_event = PalletEvent(
                event_type=PalletEventType.PASS_INSPECTION,
                entity_id=sscc,
                store_id=store_id,
                operator_id=operator_id,
                probed_temperature=probed_temperature,
                damage_observed=False,
                notes=notes,
            )

        final_res = self._state_machine.process_event(
            in_receiving_pallet, inspection_event
        )

        # Update pallet entity in repository
        updated_pallet = PalletEntity(
            sscc=target_pallet.sscc,
            asn_id=target_pallet.asn_id,
            temperature_regime=target_pallet.temperature_regime,
            state=final_res.to_state,
            lines=target_pallet.lines,
            probed_temperature=probed_temperature,
            received_at=datetime.now(timezone.utc),
            rejection_reason=violation_reason,
        )
        self._repo.update_pallet(store_id, asn_id, updated_pallet)

        return final_res, is_compliant

    def record_discrepancy(
        self,
        asn_id: str,
        store_id: str,
        discrepancy_type: str,
        reason_code: str,
        reported_by: str,
        affected_quantity: int = 1,
        sscc: str | None = None,
        sku: str | None = None,
        photo_evidence_url: str | None = None,
        notes: str | None = None,
    ) -> DiscrepancyClaimEntity:
        """Record an inbound discrepancy claim.

        Args:
            asn_id: ASN identifier.
            store_id: Store identifier.
            discrepancy_type: Type of discrepancy (OVERAGE, SHORTAGE, DAMAGE, COLD_CHAIN_BREACH).
            reason_code: Rejection/discrepancy reason code.
            reported_by: Reporter user ID.
            affected_quantity: Unit or pallet count affected.
            sscc: Optional SSCC barcode.
            sku: Optional SKU code.
            photo_evidence_url: Optional GCS URI of photographic evidence.
            notes: Optional explanatory notes.

        Returns:
            Recorded DiscrepancyClaimEntity.
        """
        # Validate that shipment exists
        self.get_asn(store_id, asn_id)

        claim_id = f"DISC-{uuid.uuid4().hex[:8].upper()}"
        claim = DiscrepancyClaimEntity(
            discrepancy_id=claim_id,
            asn_id=asn_id,
            store_id=store_id,
            discrepancy_type=discrepancy_type,
            reason_code=reason_code,
            reported_by=reported_by,
            affected_quantity=affected_quantity,
            status="LOGGED",
            created_at=datetime.now(timezone.utc),
            sscc=sscc,
            sku=sku,
            photo_evidence_url=photo_evidence_url,
            notes=notes,
        )
        self._repo.save_discrepancy(claim)
        return claim
