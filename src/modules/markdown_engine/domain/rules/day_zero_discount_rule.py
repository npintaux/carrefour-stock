"""Day zero (T-0) markdown discount rule applying 50% reduction.

Traceability:
- [US-4][AC-4.1]: If expiry_date == current_date (T-0), calculate 50% dynamic markdown.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import Decision, EvaluationRequest, MarkdownStatus
from .base import Rule


class DayZeroDiscountRule(Rule):
    """Rule applying 50% discount to products expiring on the current date."""

    @property
    def rule_id(self) -> str:
        """Unique identifier for this rule."""
        return "R3-DAY-ZERO-DISCOUNT-50"

    def evaluate(self, request: EvaluationRequest) -> Decision | None:
        """Evaluate if expiry date is today and apply 50% markdown.

        Args:
            request: Evaluation request to check.

        Returns:
            Decision with 50% markdown if matching, otherwise None.
        """
        ref_date = request.current_date or datetime.now(UTC).date()
        if request.expiry_date == ref_date:
            discounted_price = round(request.original_price_cents * 0.50)
            return Decision(
                is_allowed=True,
                status_code=200,
                reason="Product expires today (T-0); 50% markdown applied.",
                eligible=True,
                discount_percentage=50,
                discounted_price_cents=discounted_price,
                status=MarkdownStatus.DISCOUNT_50,
                rule_applied=self.rule_id,
                details={
                    "expiry_date": request.expiry_date.isoformat(),
                    "current_date": ref_date.isoformat(),
                    "discount_rate": 0.50,
                },
            )
        return None
