"""Unit tests for DecisionEngine in markdown_engine domain.

Traceability:
- [US-4][AC-4.1]: Decision engine coordinates ordered rules (Validation -> Gating -> T-0 -> T-1 -> Freshness).
"""

from datetime import date, timedelta

import pytest

from src.modules.markdown_engine.domain.engine import MarkdownEngine
from src.modules.markdown_engine.domain.exceptions import (
    InvalidMarkdownPayloadError,
    ItemAlreadyExpiredError,
)
from src.modules.markdown_engine.domain.models import (
    EvaluationRequest,
    MarkdownStatus,
)


def test_markdown_engine_default_rules_order() -> None:
    """[US-4] MarkdownEngine instantiates default rules when none provided."""
    engine = MarkdownEngine()
    assert len(engine.rules) == 5
    rule_ids = [r.rule_id for r in engine.rules]
    assert rule_ids == [
        "R1-PAYLOAD-VALIDATION",
        "R2-EXPIRED-DONATION-GATING",
        "R3-DAY-ZERO-DISCOUNT-50",
        "R4-DAY-MINUS-ONE-DISCOUNT-30",
        "R5-STANDARD-FRESHNESS",
    ]


def test_markdown_engine_evaluates_t_minus_zero() -> None:
    """[US-4][AC-4.1] T-0 expiry date evaluates to 50% discount."""
    engine = MarkdownEngine()
    ref_date = date(2026, 9, 15)
    req = EvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-CHICKEN",
        ean_barcode="3560070654321",
        lot_number="LOT-02",
        expiry_date=ref_date,
        original_price_cents=450,
        quantity=6,
        current_date=ref_date,
    )
    decision = engine.evaluate(req)
    assert decision.eligible is True
    assert decision.discount_percentage == 50
    assert decision.discounted_price_cents == 225
    assert decision.status == MarkdownStatus.DISCOUNT_50
    assert decision.rule_applied == "R3-DAY-ZERO-DISCOUNT-50"


def test_markdown_engine_evaluates_t_minus_one() -> None:
    """[US-4][AC-4.1] T-1 expiry date evaluates to 30% discount."""
    engine = MarkdownEngine()
    ref_date = date(2026, 9, 15)
    req = EvaluationRequest(
        request_id="req-2",
        store_id="STORE_FR_75015",
        sku_id="SKU-YOGURT",
        ean_barcode="3560070123456",
        lot_number="LOT-01",
        expiry_date=ref_date + timedelta(days=1),
        original_price_cents=300,
        quantity=14,
        current_date=ref_date,
    )
    decision = engine.evaluate(req)
    assert decision.eligible is True
    assert decision.discount_percentage == 30
    assert decision.discounted_price_cents == 210
    assert decision.status == MarkdownStatus.DISCOUNT_30
    assert decision.rule_applied == "R4-DAY-MINUS-ONE-DISCOUNT-30"


def test_markdown_engine_evaluates_standard_freshness() -> None:
    """[US-4][AC-4.1] Product with >= 2 days shelf life retains standard price."""
    engine = MarkdownEngine()
    ref_date = date(2026, 9, 15)
    req = EvaluationRequest(
        request_id="req-3",
        store_id="STORE_FR_75015",
        sku_id="SKU-CHEESE",
        ean_barcode="3560070987654",
        lot_number="LOT-03",
        expiry_date=ref_date + timedelta(days=4),
        original_price_cents=500,
        quantity=8,
        current_date=ref_date,
    )
    decision = engine.evaluate(req)
    assert decision.eligible is False
    assert decision.discount_percentage == 0
    assert decision.discounted_price_cents == 500
    assert decision.status == MarkdownStatus.STANDARD_PRICE
    assert decision.rule_applied == "R5-STANDARD-FRESHNESS"


def test_markdown_engine_propagates_validation_error() -> None:
    """[US-4][AC-4.1] Invalid payload raises InvalidMarkdownPayloadError."""
    engine = MarkdownEngine()
    req = EvaluationRequest(
        request_id="",
        store_id="STORE_FR_75015",
        sku_id="SKU-CHEESE",
        ean_barcode="3560070987654",
        lot_number="LOT-03",
        expiry_date=date(2026, 9, 20),
        original_price_cents=500,
        quantity=8,
    )
    with pytest.raises(InvalidMarkdownPayloadError):
        engine.evaluate(req)


def test_markdown_engine_propagates_expired_gating_error() -> None:
    """[US-4][AC-4.3] Expired product raises ItemAlreadyExpiredError."""
    engine = MarkdownEngine()
    ref_date = date(2026, 9, 15)
    req = EvaluationRequest(
        request_id="req-4",
        store_id="STORE_FR_75015",
        sku_id="SKU-CHEESE",
        ean_barcode="3560070987654",
        lot_number="LOT-03",
        expiry_date=date(2026, 9, 10),
        original_price_cents=500,
        quantity=8,
        current_date=ref_date,
    )
    with pytest.raises(ItemAlreadyExpiredError):
        engine.evaluate(req)


def test_markdown_engine_custom_rules_fallback() -> None:
    """[US-4] MarkdownEngine fallback decision when custom rules do not match."""
    engine = MarkdownEngine(rules=[])
    req = EvaluationRequest(
        request_id="req-5",
        store_id="STORE_FR_75015",
        sku_id="SKU-CHEESE",
        ean_barcode="3560070987654",
        lot_number="LOT-03",
        expiry_date=date(2026, 9, 20),
        original_price_cents=500,
        quantity=8,
    )
    decision = engine.evaluate(req)
    assert decision.eligible is False
    assert decision.rule_applied == "DEFAULT_FALLBACK"
