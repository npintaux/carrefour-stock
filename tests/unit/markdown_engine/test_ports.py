"""Unit tests for domain ports in markdown_engine.

Traceability:
- [US-4][AC-4.1]: PrinterPort interface.
- [US-4][AC-4.2]: PosPublisherPort interface.
- [US-4][AC-4.3]: DonationLedgerPort interface.
"""

from datetime import datetime, timezone

import pytest

from src.modules.markdown_engine.domain.models import (
    DonationSpoilageRecord,
    LabelPrintCommand,
    PosFeedMessage,
)
from src.modules.markdown_engine.domain.ports.donation_ledger_port import (
    DonationLedgerPort,
)
from src.modules.markdown_engine.domain.ports.pos_publisher_port import PosPublisherPort
from src.modules.markdown_engine.domain.ports.printer_port import PrinterPort


class DummyPrinterPort(PrinterPort):
    """Dummy printer port implementation for interface testing."""

    def print_label(
        self,
        request_id: str,
        evaluation_id: str,
        ean_barcode: str,
        discounted_price_cents: int,
        quantity: int,
        printer_id: str,
    ) -> LabelPrintCommand:
        """Generate label print command."""
        return LabelPrintCommand(
            job_id="job-1",
            promotional_barcode="2901234521005",
            escpos_payload_base64="RVNDL1BPUw==",
            labels_printed=quantity,
        )


class DummyPosPublisherPort(PosPublisherPort):
    """Dummy POS publisher port implementation for interface testing."""

    def publish_pos_markdown(
        self,
        request_id: str,
        store_id: str,
        ean_barcode: str,
        promotional_barcode: str,
        discounted_price_cents: int,
        valid_until: datetime,
    ) -> PosFeedMessage:
        """Publish POS feed message."""
        now = datetime.now(timezone.utc)
        return PosFeedMessage(
            message_id="msg-1",
            topic="pos-markdown-updates",
            store_id=store_id,
            ean_barcode=ean_barcode,
            promotional_barcode=promotional_barcode,
            discounted_price_cents=discounted_price_cents,
            valid_until=valid_until,
            published_at=now,
        )


class DummyDonationLedgerPort(DonationLedgerPort):
    """Dummy donation ledger port implementation for interface testing."""

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
        """Record donation or spoilage."""
        now = datetime.now(timezone.utc)
        return DonationSpoilageRecord(
            record_id="rec-1",
            fiscal_slip_id="SLIP-001",
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


def test_printer_port_abc() -> None:
    """[US-4][AC-4.1] PrinterPort cannot be instantiated directly."""
    with pytest.raises(TypeError):
        PrinterPort()  # type: ignore[abstract]

    dummy = DummyPrinterPort()
    cmd = dummy.print_label("req-1", "eval-1", "3560070123456", 210, 5, "PRINTER_1")
    assert cmd.labels_printed == 5


def test_pos_publisher_port_abc() -> None:
    """[US-4][AC-4.2] PosPublisherPort cannot be instantiated directly."""
    with pytest.raises(TypeError):
        PosPublisherPort()  # type: ignore[abstract]

    dummy = DummyPosPublisherPort()
    now = datetime.now(timezone.utc)
    msg = dummy.publish_pos_markdown(
        "req-1", "STORE_1", "3560070123456", "2901234521005", 210, now
    )
    assert msg.topic == "pos-markdown-updates"


def test_donation_ledger_port_abc() -> None:
    """[US-4][AC-4.3] DonationLedgerPort cannot be instantiated directly."""
    with pytest.raises(TypeError):
        DonationLedgerPort()  # type: ignore[abstract]

    dummy = DummyDonationLedgerPort()
    rec = dummy.record_donation_or_spoilage(
        "req-1", "STORE_1", "SKU-1", "LOT-1", "CHARITY_DONATION", 5, 1000, "REASON_1"
    )
    assert rec.stock_decremented is True
