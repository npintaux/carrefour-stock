"""Standard freshness markdown rule keeping regular price for unexpired items.

Traceability:
- [US-4][AC-4.1]: If expiry_date - current_date >= 2 days, retain standard price (0% discount).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..models import Decision, EvaluationRequest, MarkdownStatus
from .base import Rule


class StandardFreshnessRule(Rule):
    """Rule maintaining standard retail pricing for goods with >= 2 days of shelf life."""

    @property
    def rule_id(self) -> str:
        """Unique identifier for this rule."""
        return "R5-STANDARD-FRESHNESS"

    def evaluate(self, request: EvaluationRequest) -> Decision | None:
        """Evaluate if expiry date is 2 or more days in future.

        Args:
            request: Evaluation request to check.

        Returns:
            Decision with 0% discount if matching, otherwise None.
        """
        ref_date = request.current_date or datetime.now(UTC).date()
        if request.expiry_date - ref_date >= timedelta(days=2):
            return Decision(
                is_allowed=True,
                status_code=200,
                reason="Product has sufficient shelf life (>= 2 days); standard price applies.",
                eligible=False,
                discount_percentage=0,
                discounted_price_cents=request.original_price_cents,
                status=MarkdownStatus.STANDARD_PRICE,
                rule_applied=self.rule_id,
                details={
                    "expiry_date": request.expiry_date.isoformat(),
                    "current_date": ref_date.isoformat(),
                    "days_remaining": (request.expiry_date - ref_date).days,
                },
            )
        return None
