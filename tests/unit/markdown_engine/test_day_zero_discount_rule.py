"""Unit tests for DayZeroDiscountRule in markdown_engine domain.

Traceability:
- [US-4][AC-4.1]: T-0 (expiry date today) calculates 50% discount.
"""

from datetime import date

from src.modules.markdown_engine.domain.models import (
    EvaluationRequest,
    MarkdownStatus,
)
from src.modules.markdown_engine.domain.rules.day_zero_discount_rule import (
    DayZeroDiscountRule,
)


def test_day_zero_discount_rule_matches_today() -> None:
    """[US-4][AC-4.1] T-0 matches when expiry_date == current_date and yields 50% discount."""
    rule = DayZeroDiscountRule()
    assert rule.rule_id == "R3-DAY-ZERO-DISCOUNT-50"

    req = EvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-CHICKEN",
        ean_barcode="3560070654321",
        lot_number="LOT-02",
        expiry_date=date(2026, 9, 15),
        original_price_cents=450,
        quantity=6,
        current_date=date(2026, 9, 15),
    )
    decision = rule.evaluate(req)
    assert decision is not None
    assert decision.is_allowed is True
    assert decision.status_code == 200
    assert decision.eligible is True
    assert decision.discount_percentage == 50
    assert decision.discounted_price_cents == 225
    assert decision.status == MarkdownStatus.DISCOUNT_50
    assert decision.rule_applied == "R3-DAY-ZERO-DISCOUNT-50"


def test_day_zero_discount_rule_does_not_match_other_dates() -> None:
    """[US-4][AC-4.1] Rule yields None if expiry_date != current_date."""
    rule = DayZeroDiscountRule()

    req_tomorrow = EvaluationRequest(
        request_id="req-2",
        store_id="STORE_FR_75015",
        sku_id="SKU-CHICKEN",
        ean_barcode="3560070654321",
        lot_number="LOT-02",
        expiry_date=date(2026, 9, 16),
        original_price_cents=450,
        quantity=6,
        current_date=date(2026, 9, 15),
    )
    assert rule.evaluate(req_tomorrow) is None
