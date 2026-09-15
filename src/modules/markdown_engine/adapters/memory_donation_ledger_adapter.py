"""In-memory donation and spoilage ledger adapter.

Traceability:
- [US-4][AC-4.3]: French AGEC law compliant charity donation slips and bio-waste certificates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..domain.exceptions import InternalServiceError
from ..domain.models import DonationSpoilageRecord
from ..domain.ports.donation_ledger_port import DonationLedgerPort


class InMemoryDonationLedgerAdapter(DonationLedgerPort):
    """In-memory adapter simulating BigQuery/PostgreSQL AGEC donation ledger."""

    def __init__(self, simulate_fault: bool = False) -> None:
        """Initialize adapter.

        Args:
            simulate_fault: When True, simulates datastore error.
        """
        self.simulate_fault = simulate_fault
        self.records: list[DonationSpoilageRecord] = []

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
        """Record donation or spoilage write-off and return fiscal record.

        Args:
            request_id: Unique request identifier.
            store_id: Store identifier.
            sku_id: SKU identifier.
            lot_number: Lot identifier.
            action_type: CHARITY_DONATION or BIO_WASTE_REMOVAL.
            quantity: Number of units written off.
            original_value_cents: Original price value in cents.
            reason_code: AGEC disposal or donation reason code.
            beneficiary_name: Optional charity beneficiary.

        Returns:
            DonationSpoilageRecord confirming slip generation.

        Raises:
            InternalServiceError: If simulate_fault is active.
        """
        if self.simulate_fault:
            raise InternalServiceError(
                "Database transaction failed during donation logging."
            )

        now = datetime.now(UTC)
        record_id = f"REC-{uuid.uuid4().hex[:10].upper()}"
        slip_prefix = (
            "SLIP-DONATION-" if action_type == "CHARITY_DONATION" else "SLIP-WASTE-"
        )
        fiscal_slip_id = f"{slip_prefix}{uuid.uuid4().hex[:8].upper()}"

        record = DonationSpoilageRecord(
            record_id=record_id,
            fiscal_slip_id=fiscal_slip_id,
            action_type=action_type,
            store_id=store_id,
            sku_id=sku_id,
            lot_number=lot_number,
            quantity=quantity,
            original_value_cents=original_value_cents,
            reason_code=reason_code,
            beneficiary_name=beneficiary_name,
            stock_decremented=True,
            timestamp=now,
        )
        self.records.append(record)
        return record
