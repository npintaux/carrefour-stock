"""Unit tests for DayMinusOneDiscountRule in markdown_engine domain.

Traceability:
- [US-4][AC-4.1]: T-1 (expiry date tomorrow) calculates 30% discount.
"""

from datetime import date, timedelta

from src.modules.markdown_engine.domain.models import (
    EvaluationRequest,
    MarkdownStatus,
)
from src.modules.markdown_engine.domain.rules.day_minus_one_discount_rule import (
    DayMinusOneDiscountRule,
)


def test_day_minus_one_discount_rule_matches_tomorrow() -> None:
    """[US-4][AC-4.1] T-1 matches when expiry_date - current_date == 1 day and yields 30% discount."""
    rule = DayMinusOneDiscountRule()
    assert rule.rule_id == "R4-DAY-MINUS-ONE-DISCOUNT-30"

    ref_date = date(2026, 9, 15)
    expiry = ref_date + timedelta(days=1)
    req = EvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        ean_barcode="3560070123456",
        lot_number="LOT-01",
        expiry_date=expiry,
        original_price_cents=300,
        quantity=14,
        current_date=ref_date,
    )
    decision = rule.evaluate(req)
    assert decision is not None
    assert decision.is_allowed is True
    assert decision.status_code == 200
    assert decision.eligible is True
    assert decision.discount_percentage == 30
    assert decision.discounted_price_cents == 210  # 300 * 0.70
    assert decision.status == MarkdownStatus.DISCOUNT_30
    assert decision.rule_applied == "R4-DAY-MINUS-ONE-DISCOUNT-30"


def test_day_minus_one_discount_rule_does_not_match_other_deltas() -> None:
    """[US-4][AC-4.1] Rule yields None if delta is not 1 day."""
    rule = DayMinusOneDiscountRule()
    ref_date = date(2026, 9, 15)

    req_same_day = EvaluationRequest(
        request_id="req-2",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        ean_barcode="3560070123456",
        lot_number="LOT-01",
        expiry_date=ref_date,
        original_price_cents=300,
        quantity=14,
        current_date=ref_date,
    )
    assert rule.evaluate(req_same_day) is None

    req_two_days = EvaluationRequest(
        request_id="req-3",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        ean_barcode="3560070123456",
        lot_number="LOT-01",
        expiry_date=ref_date + timedelta(days=2),
        original_price_cents=300,
        quantity=14,
        current_date=ref_date,
    )
    assert rule.evaluate(req_two_days) is None
