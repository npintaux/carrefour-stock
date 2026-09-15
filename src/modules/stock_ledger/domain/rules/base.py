"""Abstract base class representing a single business rule in the decision-list pattern."""

from __future__ import annotations

import abc

from ..models import AdjustmentEvaluationRequest, Decision


class Rule(abc.ABC):
    """Abstract Base Class for individual decision predicates in stock_ledger."""

    @property
    @abc.abstractmethod
    def rule_id(self) -> str:
        """Unique rule identifier (e.g., 'R1_DEPARTMENT_SCOPE')."""
        ...

    @abc.abstractmethod
    def evaluate(self, request: AdjustmentEvaluationRequest) -> Decision:
        """Evaluate business rule against adjustment request.

        Args:
            request: Immutable input payload for evaluation.

        Returns:
            A Decision instance containing authorization outcome and metadata.
        """
        ...
