"""Decision engine orchestrator evaluating an ordered sequence of markdown rules.

Traceability:
- [US-4][AC-4.1]: Composite coordinator executing ordered decision list.
"""

from __future__ import annotations

from collections.abc import Sequence

from .models import Decision, EvaluationRequest, MarkdownStatus
from .rules.base import Rule
from .rules.day_minus_one_discount_rule import DayMinusOneDiscountRule
from .rules.day_zero_discount_rule import DayZeroDiscountRule
from .rules.expired_donation_gating_rule import ExpiredDonationGatingRule
from .rules.payload_validation_rule import PayloadValidationRule
from .rules.standard_freshness_rule import StandardFreshnessRule


class MarkdownEngine:
    """Ordered rules engine executing markdown decision rules sequentially.

    Evaluates rules in prioritized sequence and returns the first matching Decision.
    If no rule matches, returns a default fallback Decision.
    """

    def __init__(self, rules: Sequence[Rule] | None = None) -> None:
        """Initialize decision engine with ordered rules.

        Args:
            rules: Optional custom sequence of Rule instances.
                   If None, uses default ordered rule set:
                   [PayloadValidationRule, ExpiredDonationGatingRule,
                    DayZeroDiscountRule, DayMinusOneDiscountRule,
                    StandardFreshnessRule].
        """
        if rules is None:
            self._rules: tuple[Rule, ...] = (
                PayloadValidationRule(),
                ExpiredDonationGatingRule(),
                DayZeroDiscountRule(),
                DayMinusOneDiscountRule(),
                StandardFreshnessRule(),
            )
        else:
            self._rules = tuple(rules)

    @property
    def rules(self) -> tuple[Rule, ...]:
        """Return registered sequence of rules."""
        return self._rules

    def evaluate(self, request: EvaluationRequest) -> Decision:
        """Evaluate request across registered rules in order.

        Args:
            request: Evaluation request to evaluate.

        Returns:
            Decision from the first matching rule, or fallback Decision.
        """
        for rule in self._rules:
            decision = rule.evaluate(request)
            if decision is not None:
                return decision

        return Decision(
            is_allowed=True,
            status_code=200,
            reason="No explicit markdown rule matched; retained at standard price.",
            eligible=False,
            discount_percentage=0,
            discounted_price_cents=request.original_price_cents,
            status=MarkdownStatus.STANDARD_PRICE,
            rule_applied="DEFAULT_FALLBACK",
        )
