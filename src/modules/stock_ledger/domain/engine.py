"""Decision engine coordinating ordered rule evaluation for stock adjustments."""

from __future__ import annotations

from collections.abc import Sequence

from .models import AdjustmentEvaluationRequest, Decision
from .rules.base import Rule


class AdjustmentDecisionEngine:
    """Composed dispatcher executing ordered rule sequence for stock adjustments."""

    def __init__(self, rules: Sequence[Rule]) -> None:
        """Initialize the decision engine with an ordered sequence of rules.

        Args:
            rules: Ordered sequence of Rule instances to evaluate.
        """
        self._rules = tuple(rules)

    @property
    def rules(self) -> tuple[Rule, ...]:
        """Return the tuple of configured rules in priority order."""
        return self._rules

    def evaluate(self, request: AdjustmentEvaluationRequest) -> Decision:
        """Evaluate incoming adjustment request sequentially against rules.

        Short-circuits immediately if a rule denies the adjustment or if a rule
        escalates to dual-key director hold.

        Args:
            request: Adjustment evaluation request payload.

        Returns:
            The final Decision outcome.
        """
        for rule in self._rules:
            decision = rule.evaluate(request)
            if not decision.is_allowed:
                return decision
            if decision.action == "HOLD_FOR_APPROVAL":
                return decision

        return Decision(
            is_allowed=True,
            status_code=200,
            error_code=None,
            action="AUTO_APPROVE",
            reason="All adjustment policy rules passed.",
        )
