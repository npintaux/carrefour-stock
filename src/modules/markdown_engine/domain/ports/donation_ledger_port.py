"""Port definition for AGEC charity donations and bio-waste spoilage records.

Traceability:
- [US-4][AC-4.3]: Audit ledger port for French AGEC anti-waste law compliance.
"""

from __future__ import annotations

import abc

from ..models import DonationSpoilageRecord


class DonationLedgerPort(abc.ABC):
    """Abstract port for AGEC fiscal donation logging and stock write-offs."""

    @abc.abstractmethod
    def record_donation_or_spoilage(
        self,
        request_id: str,
        store_id: str,
        sku_id: str,
        lot_number: str,
        action_type: str,
        quantity: int,
        original_value_cents: int,
        reason_code: str,
        beneficiary_name: str | None = None,
    ) -> DonationSpoilageRecord:
        """Record donation or spoilage and decrement stock.

        Args:
            request_id: Unique request identifier.
            store_id: Store identifier.
            sku_id: SKU identifier.
            lot_number: Lot identifier.
            action_type: CHARITY_DONATION or BIO_WASTE_REMOVAL.
            quantity: Number of units written off.
            original_value_cents: Value of products in cents.
            reason_code: AGEC disposal/donation reason code.
            beneficiary_name: Optional charity beneficiary.

        Returns:
            DonationSpoilageRecord confirming slip generation and stock decrement.
        """
        ...
