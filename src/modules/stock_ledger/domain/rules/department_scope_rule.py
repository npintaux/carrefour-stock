"""Department scope validation rule (R1)."""

from __future__ import annotations

from ..models import AdjustmentEvaluationRequest, Decision
from .base import Rule


class DepartmentScopeRule(Rule):
    """Validates that initiator is authorized to operate within the target department."""

    @property
    def rule_id(self) -> str:
        """Unique rule identifier."""
        return "R1_DEPARTMENT_SCOPE"

    def evaluate(self, request: AdjustmentEvaluationRequest) -> Decision:
        """Evaluate whether initiator has access to target department.

        Args:
            request: Adjustment evaluation request payload.

        Returns:
            Decision indicating whether department scope is valid.
        """
        # Store Directors have global department access
        if request.initiator_role == "DIRECTEUR_MAGASIN":
            return Decision(
                is_allowed=True,
                status_code=200,
                error_code=None,
                reason="Store Director has global store scope.",
            )

        # Check if target department is in user claims
        if request.department_id in request.user_departments:
            return Decision(
                is_allowed=True,
                status_code=200,
                error_code=None,
                reason="Department matches initiator authorized departments.",
            )

        return Decision(
            is_allowed=False,
            status_code=403,
            error_code="ERR_OUT_OF_SCOPE_DEPARTMENT",
            reason=(
                f"User is not authorized to access or modify stock in {request.department_id}."
            ),
        )
