"""Unit tests for ExpiredDonationGatingRule in markdown_engine domain.

Traceability:
- [US-4][AC-4.3]: Items with expiry date in the past raise ItemAlreadyExpiredError with HTTP 422.
"""

from datetime import date

import pytest

from src.modules.markdown_engine.domain.exceptions import ItemAlreadyExpiredError
from src.modules.markdown_engine.domain.models import EvaluationRequest
from src.modules.markdown_engine.domain.rules.expired_donation_gating_rule import (
    ExpiredDonationGatingRule,
)


def test_expired_donation_gating_rule_unexpired_passes() -> None:
    """[US-4][AC-4.3] Item with expiry today or in future passes through."""
    rule = ExpiredDonationGatingRule()
    assert rule.rule_id == "R2-EXPIRED-DONATION-GATING"

    req_future = EvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        ean_barcode="3560070123456",
        lot_number="LOT-01",
        expiry_date=date(2026, 9, 16),
        original_price_cents=350,
        quantity=5,
        current_date=date(2026, 9, 15),
    )
    assert rule.evaluate(req_future) is None

    req_today = EvaluationRequest(
        request_id="req-2",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        ean_barcode="3560070123456",
        lot_number="LOT-01",
        expiry_date=date(2026, 9, 15),
        original_price_cents=350,
        quantity=5,
        current_date=date(2026, 9, 15),
    )
    assert rule.evaluate(req_today) is None


def test_expired_donation_gating_rule_expired_raises_422() -> None:
    """[US-4][AC-4.3] Item with current_date > expiry_date raises ItemAlreadyExpiredError."""
    rule = ExpiredDonationGatingRule()

    req_expired = EvaluationRequest(
        request_id="req-3",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        ean_barcode="3560070123456",
        lot_number="LOT-01",
        expiry_date=date(2026, 9, 14),
        original_price_cents=350,
        quantity=5,
        current_date=date(2026, 9, 15),
    )
    with pytest.raises(
        ItemAlreadyExpiredError, match="past expiry threshold"
    ) as exc_info:
        rule.evaluate(req_expired)

    assert exc_info.value.code == "ITEM_EXPIRED_DONATION_REQUIRED"
    assert exc_info.value.status_code == 422
