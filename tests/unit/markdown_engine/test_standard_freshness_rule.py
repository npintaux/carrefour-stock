"""Unit tests for StandardFreshnessRule in markdown_engine domain.

Traceability:
- [US-4][AC-4.1]: Fresh products (>= 2 days to expiry) retain standard price (0% discount).
"""

from datetime import date, timedelta

from src.modules.markdown_engine.domain.models import (
    EvaluationRequest,
    MarkdownStatus,
)
from src.modules.markdown_engine.domain.rules.standard_freshness_rule import (
    StandardFreshnessRule,
)


def test_standard_freshness_rule_matches_two_or_more_days() -> None:
    """[US-4][AC-4.1] Products with >= 2 days to expiry remain at standard price."""
    rule = StandardFreshnessRule()
    assert rule.rule_id == "R5-STANDARD-FRESHNESS"

    ref_date = date(2026, 9, 15)
    expiry = ref_date + timedelta(days=5)
    req = EvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-CHEESE",
        ean_barcode="3560070987654",
        lot_number="LOT-03",
        expiry_date=expiry,
        original_price_cents=500,
        quantity=8,
        current_date=ref_date,
    )
    decision = rule.evaluate(req)
    assert decision is not None
    assert decision.is_allowed is True
    assert decision.status_code == 200
    assert decision.eligible is False
    assert decision.discount_percentage == 0
    assert decision.discounted_price_cents == 500
    assert decision.status == MarkdownStatus.STANDARD_PRICE
    assert decision.rule_applied == "R5-STANDARD-FRESHNESS"


def test_standard_freshness_rule_does_not_match_less_than_two_days() -> None:
    """[US-4][AC-4.1] Returns None if delta is less than 2 days."""
    rule = StandardFreshnessRule()
    ref_date = date(2026, 9, 15)

    req_one_day = EvaluationRequest(
        request_id="req-2",
        store_id="STORE_FR_75015",
        sku_id="SKU-CHEESE",
        ean_barcode="3560070987654",
        lot_number="LOT-03",
        expiry_date=ref_date + timedelta(days=1),
        original_price_cents=500,
        quantity=8,
        current_date=ref_date,
    )
    assert rule.evaluate(req_one_day) is None
