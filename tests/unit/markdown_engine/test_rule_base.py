"""Unit tests for Rule base class in markdown_engine domain.

Traceability:
- [US-4]: Abstract base class defining rule contract.
"""

from datetime import date

import pytest

from src.modules.markdown_engine.domain.models import (
    Decision,
    EvaluationRequest,
    MarkdownStatus,
)
from src.modules.markdown_engine.domain.rules.base import Rule


class DummyRule(Rule):
    """Concrete dummy rule for testing abstract base class contract."""

    @property
    def rule_id(self) -> str:
        """Return dummy rule id."""
        return "R-DUMMY"

    def evaluate(self, request: EvaluationRequest) -> Decision | None:
        """Evaluate dummy condition."""
        if request.quantity > 5:
            return Decision(
                is_allowed=True,
                status_code=200,
                reason="Dummy matched",
                eligible=True,
                discount_percentage=10,
                discounted_price_cents=90,
                status=MarkdownStatus.STANDARD_PRICE,
                rule_applied=self.rule_id,
            )
        return None


def test_rule_abc_instantiation() -> None:
    """[US-4] Cannot instantiate abstract Rule directly."""
    with pytest.raises(TypeError):
        Rule()  # type: ignore[abstract]


def test_concrete_rule_behavior() -> None:
    """[US-4] Concrete rule evaluates request and returns decision or None."""
    rule = DummyRule()
    assert rule.rule_id == "R-DUMMY"

    req_match = EvaluationRequest(
        request_id="req-1",
        store_id="STORE-1",
        sku_id="SKU-1",
        ean_barcode="1234567890123",
        lot_number="LOT-1",
        expiry_date=date(2026, 9, 20),
        original_price_cents=100,
        quantity=10,
    )
    decision = rule.evaluate(req_match)
    assert decision is not None
    assert decision.is_allowed is True
    assert decision.rule_applied == "R-DUMMY"

    req_no_match = EvaluationRequest(
        request_id="req-2",
        store_id="STORE-1",
        sku_id="SKU-1",
        ean_barcode="1234567890123",
        lot_number="LOT-1",
        expiry_date=date(2026, 9, 20),
        original_price_cents=100,
        quantity=2,
    )
    assert rule.evaluate(req_no_match) is None
