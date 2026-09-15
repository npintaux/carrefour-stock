"""Unit tests for markdown engine domain models and exceptions.

Traceability:
- [US-4][AC-4.1]: EvaluationRequest and Decision domain structures.
- [US-4][AC-4.2]: PosFeedMessage data structure.
- [US-4][AC-4.3]: DonationSpoilageRecord domain audit structure.
"""

from datetime import date, datetime, timezone

from src.modules.markdown_engine.domain.exceptions import (
    IneligibleMarkdownError,
    InternalServiceError,
    InvalidMarkdownPayloadError,
    ItemAlreadyExpiredError,
    MarkdownEngineError,
    PrinterCommunicationError,
    PubSubPublishError,
)
from src.modules.markdown_engine.domain.models import (
    Decision,
    DonationSpoilageRecord,
    EvaluationRequest,
    LabelPrintCommand,
    MarkdownStatus,
    PosFeedMessage,
)


def test_markdown_status_enum_values() -> None:
    """Verify MarkdownStatus enum values align with domain specification."""
    assert MarkdownStatus.DISCOUNT_30 == "DISCOUNT_30"
    assert MarkdownStatus.DISCOUNT_50 == "DISCOUNT_50"
    assert MarkdownStatus.STANDARD_PRICE == "STANDARD_PRICE"
    assert MarkdownStatus.DONATION_CANDIDATE == "DONATION_CANDIDATE"
    assert MarkdownStatus.SPOILAGE_CANDIDATE == "SPOILAGE_CANDIDATE"


def test_evaluation_request_instantiation() -> None:
    """[US-4][AC-4.1] EvaluationRequest creates immutable value object."""
    req = EvaluationRequest(
        request_id="req-123",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        ean_barcode="3560070123456",
        lot_number="LOT-01",
        expiry_date=date(2026, 9, 16),
        original_price_cents=350,
        quantity=10,
        current_date=date(2026, 9, 15),
    )
    assert req.request_id == "req-123"
    assert req.store_id == "STORE_FR_75015"
    assert req.original_price_cents == 350
    assert req.quantity == 10
    assert req.current_date == date(2026, 9, 15)


def test_decision_instantiation() -> None:
    """[US-4][AC-4.1] Decision encapsulates markdown outcome."""
    dec = Decision(
        is_allowed=True,
        status_code=200,
        reason="T-1 30% discount applied",
        eligible=True,
        discount_percentage=30,
        discounted_price_cents=245,
        status=MarkdownStatus.DISCOUNT_30,
        rule_applied="R-DAY-MINUS-ONE",
        details={"saving": 105},
    )
    assert dec.is_allowed is True
    assert dec.status_code == 200
    assert dec.discount_percentage == 30
    assert dec.discounted_price_cents == 245
    assert dec.status == MarkdownStatus.DISCOUNT_30
    assert dec.rule_applied == "R-DAY-MINUS-ONE"
    assert dec.details == {"saving": 105}


def test_label_print_command_instantiation() -> None:
    """[US-4][AC-4.1] LabelPrintCommand encapsulates printer instructions."""
    cmd = LabelPrintCommand(
        job_id="job-001",
        promotional_barcode="2901234524508",
        escpos_payload_base64="RVNDL1BPUw==",
        labels_printed=5,
    )
    assert cmd.job_id == "job-001"
    assert cmd.labels_printed == 5


def test_pos_feed_message_instantiation() -> None:
    """[US-4][AC-4.2] PosFeedMessage encapsulates POS Pub/Sub broadcast payload."""
    now = datetime.now(timezone.utc)
    msg = PosFeedMessage(
        message_id="msg-1",
        topic="pos-markdown-updates",
        store_id="STORE_FR_75015",
        ean_barcode="3560070123456",
        promotional_barcode="2901234524508",
        discounted_price_cents=245,
        valid_until=now,
        published_at=now,
    )
    assert msg.message_id == "msg-1"
    assert msg.topic == "pos-markdown-updates"


def test_donation_spoilage_record_instantiation() -> None:
    """[US-4][AC-4.3] DonationSpoilageRecord encapsulates AGEC charity donation/bio-waste."""
    now = datetime.now(timezone.utc)
    rec = DonationSpoilageRecord(
        record_id="rec-1",
        fiscal_slip_id="SLIP-001",
        action_type="CHARITY_DONATION",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        lot_number="LOT-01",
        quantity=8,
        original_value_cents=2800,
        reason_code="AGEC_DONATION_BANQUE_ALIMENTAIRE",
        beneficiary_name="Banques Alimentaires",
        stock_decremented=True,
        timestamp=now,
    )
    assert rec.record_id == "rec-1"
    assert rec.fiscal_slip_id == "SLIP-001"
    assert rec.stock_decremented is True


def test_exceptions_hierarchy() -> None:
    """Test custom exception hierarchy and error codes."""
    err = InvalidMarkdownPayloadError("Invalid payload")
    assert isinstance(err, MarkdownEngineError)
    assert err.status_code == 400
    assert err.code == "INVALID_PAYLOAD"

    expired_err = ItemAlreadyExpiredError("Item expired")
    assert expired_err.status_code == 422
    assert expired_err.code == "ITEM_EXPIRED_DONATION_REQUIRED"

    inelig_err = IneligibleMarkdownError("Ineligible")
    assert inelig_err.status_code == 422
    assert inelig_err.code == "INELIGIBLE_FOR_MARKDOWN"

    print_err = PrinterCommunicationError("Printer down")
    assert print_err.status_code == 500
    assert print_err.code == "PRINTER_COMMUNICATION_ERROR"

    pubsub_err = PubSubPublishError("PubSub failed")
    assert pubsub_err.status_code == 500
    assert pubsub_err.code == "PUBSUB_BROADCAST_FAILURE"

    internal_err = InternalServiceError("Internal fault")
    assert internal_err.status_code == 500
    assert internal_err.code == "INTERNAL_ERROR"
