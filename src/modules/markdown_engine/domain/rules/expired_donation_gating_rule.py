"""Gating rule prohibiting retail markdown for expired perishable stock.

Traceability:
- [US-4][AC-4.3]: Checks if current_date > expiry_date and raises ItemAlreadyExpiredError (HTTP 422).
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..exceptions import ItemAlreadyExpiredError
from ..models import Decision, EvaluationRequest
from .base import Rule


class ExpiredDonationGatingRule(Rule):
    """Rule preventing expired inventory markdown and routing to donation/spoilage."""

    @property
    def rule_id(self) -> str:
        """Unique identifier for this rule."""
        return "R2-EXPIRED-DONATION-GATING"

    def evaluate(self, request: EvaluationRequest) -> Decision | None:
        """Evaluate if product expiry date has passed.

        Args:
            request: Evaluation request to check.

        Returns:
            None if product is not expired, yielding to subsequent rules.

        Raises:
            ItemAlreadyExpiredError: If expiry_date < current_date.
        """
        ref_date = request.current_date or datetime.now(UTC).date()
        if request.expiry_date < ref_date:
            raise ItemAlreadyExpiredError(
                f"Lot '{request.lot_number}' expiry date {request.expiry_date} "
                f"is past expiry threshold relative to {ref_date}. Markdown prohibited.",
                details={
                    "lot_number": request.lot_number,
                    "expiry_date": request.expiry_date.isoformat(),
                    "current_date": ref_date.isoformat(),
                },
            )
        return None
