"""Day minus one (T-1) markdown discount rule applying 30% reduction.

Traceability:
- [US-4][AC-4.1]: If expiry_date - current_date == 1 day (T-1), calculate 30% dynamic markdown.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..models import Decision, EvaluationRequest, MarkdownStatus
from .base import Rule


class DayMinusOneDiscountRule(Rule):
    """Rule applying 30% discount to products expiring tomorrow."""

    @property
    def rule_id(self) -> str:
        """Unique identifier for this rule."""
        return "R4-DAY-MINUS-ONE-DISCOUNT-30"

    def evaluate(self, request: EvaluationRequest) -> Decision | None:
        """Evaluate if expiry date is tomorrow and apply 30% markdown.

        Args:
            request: Evaluation request to check.

        Returns:
            Decision with 30% markdown if matching, otherwise None.
        """
        ref_date = request.current_date or datetime.now(UTC).date()
        if request.expiry_date - ref_date == timedelta(days=1):
            discounted_price = round(request.original_price_cents * 0.70)
            return Decision(
                is_allowed=True,
                status_code=200,
                reason="Product expires tomorrow (T-1); 30% markdown applied.",
                eligible=True,
                discount_percentage=30,
                discounted_price_cents=discounted_price,
                status=MarkdownStatus.DISCOUNT_30,
                rule_applied=self.rule_id,
                details={
                    "expiry_date": request.expiry_date.isoformat(),
                    "current_date": ref_date.isoformat(),
                    "discount_rate": 0.30,
                },
            )
        return None
