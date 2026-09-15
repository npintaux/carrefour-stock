"""In-memory adapter implementing InboundShipmentRepository."""

from __future__ import annotations

from src.modules.inbound_dock.domain.exceptions import (
    DuplicateShipmentError,
    PalletNotFoundError,
    ShipmentNotFoundError,
)
from src.modules.inbound_dock.domain.models import (
    AsnShipmentEntity,
    DiscrepancyClaimEntity,
    PalletEntity,
)
from src.modules.inbound_dock.domain.repository import InboundShipmentRepository


class InMemoryInboundShipmentRepository(InboundShipmentRepository):
    """In-memory storage implementation of InboundShipmentRepository port."""

    def __init__(self) -> None:
        """Initialize in-memory storage data structures."""
        # Key: (store_id, asn_id) -> AsnShipmentEntity
        self._shipments: dict[tuple[str, str], AsnShipmentEntity] = {}
        # Key: (store_id, asn_id) -> dict[sscc, PalletEntity]
        self._pallets: dict[tuple[str, str], dict[str, PalletEntity]] = {}
        # Key: discrepancy_id -> DiscrepancyClaimEntity
        self._discrepancies: dict[str, DiscrepancyClaimEntity] = {}
        # Key: idempotency_key -> payload_summary
        self._idempotency_store: dict[str, str] = {}

    def save_shipment(self, shipment: AsnShipmentEntity) -> None:
        """Persist a new inbound ASN shipment.

        Args:
            shipment: The ASN shipment entity to store.

        Raises:
            DuplicateShipmentError: If ASN already exists for the store.
        """
        key = (shipment.store_id, shipment.asn_id)
        if key in self._shipments:
            raise DuplicateShipmentError(
                f"Shipment '{shipment.asn_id}' already exists for store '{shipment.store_id}'"
            )

        self._shipments[key] = shipment
        self._pallets[key] = {p.sscc: p for p in shipment.pallets}

    def get_shipment(self, store_id: str, asn_id: str) -> AsnShipmentEntity | None:
        """Retrieve an ASN shipment by store identifier and ASN ID.

        Args:
            store_id: Destination store identifier.
            asn_id: Advance Shipping Notice identifier.

        Returns:
            The AsnShipmentEntity if found, None otherwise.
        """
        key = (store_id, asn_id)
        shipment = self._shipments.get(key)
        if shipment is None:
            return None

        # Reconstruct shipment with up-to-date pallet states
        pallets_dict = self._pallets.get(key, {})
        updated_pallets = tuple(pallets_dict.values())
        return AsnShipmentEntity(
            asn_id=shipment.asn_id,
            store_id=shipment.store_id,
            supplier_id=shipment.supplier_id,
            expected_delivery=shipment.expected_delivery,
            status=shipment.status,
            pallets=updated_pallets,
        )

    def update_pallet(self, store_id: str, asn_id: str, pallet: PalletEntity) -> None:
        """Update the state and probe details of an existing pallet.

        Args:
            store_id: Destination store identifier.
            asn_id: Advance Shipping Notice identifier.
            pallet: The updated pallet entity.

        Raises:
            ShipmentNotFoundError: If the shipment does not exist.
            PalletNotFoundError: If the pallet SSCC does not exist in the shipment.
        """
        key = (store_id, asn_id)
        if key not in self._shipments:
            raise ShipmentNotFoundError(
                f"Shipment '{asn_id}' not found for store '{store_id}'"
            )

        pallets_dict = self._pallets[key]
        if pallet.sscc not in pallets_dict:
            raise PalletNotFoundError(
                f"Pallet '{pallet.sscc}' not found in shipment '{asn_id}'"
            )

        pallets_dict[pallet.sscc] = pallet

    def save_discrepancy(self, claim: DiscrepancyClaimEntity) -> None:
        """Persist a discrepancy claim.

        Args:
            claim: The discrepancy claim domain entity.
        """
        self._discrepancies[claim.discrepancy_id] = claim

    def check_idempotency(self, key: str) -> bool:
        """Check if an idempotency key has already been processed.

        Args:
            key: UUID idempotency token.

        Returns:
            True if previously processed, False otherwise.
        """
        return key in self._idempotency_store

    def record_idempotency(self, key: str, payload_summary: str) -> None:
        """Record an idempotency key to prevent duplicate processing.

        Args:
            key: UUID idempotency token.
            payload_summary: Optional summary or hash of response payload.
        """
        self._idempotency_store[key] = payload_summary
