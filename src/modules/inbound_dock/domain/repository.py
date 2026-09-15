"""Domain port for inbound shipment persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import AsnShipmentEntity, DiscrepancyClaimEntity, PalletEntity


class InboundShipmentRepository(ABC):
    """Abstract repository port for persisting ASNs, pallets, and discrepancy claims."""

    @abstractmethod
    def save_shipment(self, shipment: AsnShipmentEntity) -> None:
        """Persist a new inbound ASN shipment.

        Args:
            shipment: The ASN shipment entity to store.
        """
        raise NotImplementedError

    @abstractmethod
    def get_shipment(self, store_id: str, asn_id: str) -> AsnShipmentEntity | None:
        """Retrieve an ASN shipment by store identifier and ASN ID.

        Args:
            store_id: Destination store identifier.
            asn_id: Advance Shipping Notice identifier.

        Returns:
            The AsnShipmentEntity if found, None otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def update_pallet(self, store_id: str, asn_id: str, pallet: PalletEntity) -> None:
        """Update the state and probe details of an existing pallet.

        Args:
            store_id: Destination store identifier.
            asn_id: Advance Shipping Notice identifier.
            pallet: The updated pallet entity.
        """
        raise NotImplementedError

    @abstractmethod
    def save_discrepancy(self, claim: DiscrepancyClaimEntity) -> None:
        """Persist a discrepancy claim.

        Args:
            claim: The discrepancy claim domain entity.
        """
        raise NotImplementedError

    @abstractmethod
    def check_idempotency(self, key: str) -> bool:
        """Check if an idempotency key has already been processed.

        Args:
            key: UUID idempotency token.

        Returns:
            True if previously processed, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def record_idempotency(self, key: str, payload_summary: str) -> None:
        """Record an idempotency key to prevent duplicate processing.

        Args:
            key: UUID idempotency token.
            payload_summary: Optional summary or hash of response payload.
        """
        raise NotImplementedError
