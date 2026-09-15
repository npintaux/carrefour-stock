"""Unit tests for PayloadValidationRule in markdown_engine domain.

Traceability:
- [US-4][AC-4.1]: Rejection of invalid payload attributes (negative price, zero quantity, empty identifiers).
"""

from datetime import date

import pytest

from src.modules.markdown_engine.domain.exceptions import InvalidMarkdownPayloadError
from src.modules.markdown_engine.domain.models import EvaluationRequest
from src.modules.markdown_engine.domain.rules.payload_validation_rule import (
    PayloadValidationRule,
)


def test_payload_validation_rule_valid_passes() -> None:
    """[US-4][AC-4.1] Valid evaluation payload returns None (yields to next rule)."""
    rule = PayloadValidationRule()
    assert rule.rule_id == "R1-PAYLOAD-VALIDATION"

    req = EvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        ean_barcode="3560070123456",
        lot_number="LOT-01",
        expiry_date=date(2026, 9, 16),
        original_price_cents=350,
        quantity=5,
    )
    assert rule.evaluate(req) is None


def test_payload_validation_rule_rejects_empty_fields() -> None:
    """[US-4][AC-4.1] Empty string identifiers raise InvalidMarkdownPayloadError."""
    rule = PayloadValidationRule()

    # Empty request_id
    with pytest.raises(InvalidMarkdownPayloadError, match="request_id cannot be empty"):
        rule.evaluate(
            EvaluationRequest(
                request_id="",
                store_id="STORE_FR_75015",
                sku_id="SKU-YOGURT",
                ean_barcode="3560070123456",
                lot_number="LOT-01",
                expiry_date=date(2026, 9, 16),
                original_price_cents=350,
                quantity=5,
            )
        )

    # Empty store_id
    with pytest.raises(InvalidMarkdownPayloadError, match="store_id cannot be empty"):
        rule.evaluate(
            EvaluationRequest(
                request_id="req-1",
                store_id="   ",
                sku_id="SKU-YOGURT",
                ean_barcode="3560070123456",
                lot_number="LOT-01",
                expiry_date=date(2026, 9, 16),
                original_price_cents=350,
                quantity=5,
            )
        )

    # Empty sku_id
    with pytest.raises(InvalidMarkdownPayloadError, match="sku_id cannot be empty"):
        rule.evaluate(
            EvaluationRequest(
                request_id="req-1",
                store_id="STORE-1",
                sku_id="",
                ean_barcode="3560070123456",
                lot_number="LOT-01",
                expiry_date=date(2026, 9, 16),
                original_price_cents=350,
                quantity=5,
            )
        )

    # Empty ean_barcode
    with pytest.raises(
        InvalidMarkdownPayloadError, match="ean_barcode cannot be empty"
    ):
        rule.evaluate(
            EvaluationRequest(
                request_id="req-1",
                store_id="STORE-1",
                sku_id="SKU-1",
                ean_barcode="",
                lot_number="LOT-01",
                expiry_date=date(2026, 9, 16),
                original_price_cents=350,
                quantity=5,
            )
        )

    # Empty lot_number
    with pytest.raises(InvalidMarkdownPayloadError, match="lot_number cannot be empty"):
        rule.evaluate(
            EvaluationRequest(
                request_id="req-1",
                store_id="STORE-1",
                sku_id="SKU-1",
                ean_barcode="3560070123456",
                lot_number="",
                expiry_date=date(2026, 9, 16),
                original_price_cents=350,
                quantity=5,
            )
        )


def test_payload_validation_rule_rejects_non_positive_price() -> None:
    """[US-4][AC-4.1] Non-positive original price raises InvalidMarkdownPayloadError."""
    rule = PayloadValidationRule()

    req_zero = EvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        ean_barcode="3560070123456",
        lot_number="LOT-01",
        expiry_date=date(2026, 9, 16),
        original_price_cents=0,
        quantity=5,
    )
    with pytest.raises(
        InvalidMarkdownPayloadError,
        match="original_price_cents must be strictly positive",
    ):
        rule.evaluate(req_zero)

    req_neg = EvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        ean_barcode="3560070123456",
        lot_number="LOT-01",
        expiry_date=date(2026, 9, 16),
        original_price_cents=-100,
        quantity=5,
    )
    with pytest.raises(
        InvalidMarkdownPayloadError,
        match="original_price_cents must be strictly positive",
    ):
        rule.evaluate(req_neg)


def test_payload_validation_rule_rejects_non_positive_quantity() -> None:
    """[US-4][AC-4.1] Zero or negative quantity raises InvalidMarkdownPayloadError."""
    rule = PayloadValidationRule()

    req_zero = EvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        ean_barcode="3560070123456",
        lot_number="LOT-01",
        expiry_date=date(2026, 9, 16),
        original_price_cents=350,
        quantity=0,
    )
    with pytest.raises(
        InvalidMarkdownPayloadError, match="quantity must be strictly positive"
    ):
        rule.evaluate(req_zero)
