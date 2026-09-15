"""Dual-key authorization threshold verification rule (R3)."""

from __future__ import annotations

from ..models import AdjustmentEvaluationRequest, Decision
from .base import Rule


class DualKeyThresholdRule(Rule):
    """Evaluates whether an adjustment requires dual-key Store Director authorization."""

    @property
    def rule_id(self) -> str:
        """Unique rule identifier."""
        return "R3_DUAL_KEY_THRESHOLD"

    def evaluate(self, request: AdjustmentEvaluationRequest) -> Decision:
        """Evaluate financial impact against the dual-key authorization threshold.

        Args:
            request: Adjustment evaluation request payload.

        Returns:
            Decision indicating whether auto-approval or director escalation is needed.
        """
        total_value_cents = abs(request.quantity_delta) * request.unit_price_cents

        if total_value_cents >= request.threshold_cents:
            return Decision(
                is_allowed=True,
                status_code=202,
                error_code=None,
                action="HOLD_FOR_APPROVAL",
                reason=(
                    f"Adjustment value ({total_value_cents} cents) reaches or exceeds "
                    f"threshold ({request.threshold_cents} cents); routed to Store Director."
                ),
            )

        return Decision(
            is_allowed=True,
            status_code=200,
            error_code=None,
            action="AUTO_APPROVE",
            reason=(
                f"Adjustment value ({total_value_cents} cents) is below approval "
                f"threshold ({request.threshold_cents} cents); auto-approved."
            ),
        )
