"""Unit tests for adapters in markdown_engine.

Traceability:
- [US-4][AC-4.1]: InMemoryPrinterAdapter.
- [US-4][AC-4.2]: InMemoryPosPublisherAdapter.
- [US-4][AC-4.3]: InMemoryDonationLedgerAdapter.
"""

from datetime import datetime, timezone

import pytest

from src.modules.markdown_engine.adapters.memory_donation_ledger_adapter import (
    InMemoryDonationLedgerAdapter,
)
from src.modules.markdown_engine.adapters.memory_pos_publisher_adapter import (
    InMemoryPosPublisherAdapter,
)
from src.modules.markdown_engine.adapters.memory_printer_adapter import (
    InMemoryPrinterAdapter,
)
from src.modules.markdown_engine.domain.exceptions import (
    InternalServiceError,
    PrinterCommunicationError,
    PubSubPublishError,
)


def test_in_memory_printer_adapter() -> None:
    """[US-4][AC-4.1] InMemoryPrinterAdapter generates ESC/POS payload and promotional barcode."""
    adapter = InMemoryPrinterAdapter()
    res = adapter.print_label(
        request_id="req-1",
        evaluation_id="eval-1",
        ean_barcode="3560070123456",
        discounted_price_cents=210,
        quantity=5,
        printer_id="PRINTER_ZEBRA_01",
    )
    assert res.job_id.startswith("JOB-")
    assert len(res.promotional_barcode) >= 12
    assert res.escpos_payload_base64 != ""
    assert res.labels_printed == 5

    # Test error simulation
    adapter.simulate_fault = True
    with pytest.raises(
        PrinterCommunicationError, match="Printer hardware communication failed"
    ):
        adapter.print_label(
            request_id="req-2",
            evaluation_id="eval-2",
            ean_barcode="3560070123456",
            discounted_price_cents=210,
            quantity=1,
            printer_id="PRINTER_ZEBRA_01",
        )


def test_in_memory_pos_publisher_adapter() -> None:
    """[US-4][AC-4.2] InMemoryPosPublisherAdapter records and publishes feed messages."""
    adapter = InMemoryPosPublisherAdapter()
    now = datetime.now(timezone.utc)
    res = adapter.publish_pos_markdown(
        request_id="req-1",
        store_id="STORE_FR_75015",
        ean_barcode="3560070123456",
        promotional_barcode="2901234521005",
        discounted_price_cents=210,
        valid_until=now,
    )
    assert res.message_id.startswith("MSG-")
    assert res.topic == "pos-markdown-updates"
    assert len(adapter.published_messages) == 1

    # Test error simulation
    adapter.simulate_fault = True
    with pytest.raises(
        PubSubPublishError, match="Pub/Sub topic 'pos-markdown-updates' unreachable"
    ):
        adapter.publish_pos_markdown(
            request_id="req-2",
            store_id="STORE_FR_75015",
            ean_barcode="3560070123456",
            promotional_barcode="2901234521005",
            discounted_price_cents=210,
            valid_until=now,
        )


def test_in_memory_donation_ledger_adapter() -> None:
    """[US-4][AC-4.3] InMemoryDonationLedgerAdapter logs AGEC slip and decrements inventory."""
    adapter = InMemoryDonationLedgerAdapter()
    rec = adapter.record_donation_or_spoilage(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        lot_number="LOT-01",
        action_type="CHARITY_DONATION",
        quantity=10,
        original_value_cents=3500,
        reason_code="AGEC_DONATION_BANQUE_ALIMENTAIRE",
        beneficiary_name="Banques Alimentaires",
    )
    assert rec.record_id.startswith("REC-")
    assert rec.fiscal_slip_id.startswith("SLIP-")
    assert rec.action_type == "CHARITY_DONATION"
    assert rec.stock_decremented is True
    assert len(adapter.records) == 1

    # Test error simulation
    adapter.simulate_fault = True
    with pytest.raises(
        InternalServiceError,
        match="Database transaction failed during donation logging",
    ):
        adapter.record_donation_or_spoilage(
            request_id="req-2",
            store_id="STORE_FR_75015",
            sku_id="SKU-YOGURT",
            lot_number="LOT-01",
            action_type="CHARITY_DONATION",
            quantity=5,
            original_value_cents=1750,
            reason_code="AGEC_DONATION_BANQUE_ALIMENTAIRE",
        )
