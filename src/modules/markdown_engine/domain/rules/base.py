"""Abstract base class definition for decision rules in markdown engine.

Traceability:
- [US-4]: Base contract for ordered decision-list pattern.
"""

from __future__ import annotations

import abc

from ..models import Decision, EvaluationRequest


class Rule(abc.ABC):
    """Abstract base class for perishable stock markdown decision rules."""

    @property
    @abc.abstractmethod
    def rule_id(self) -> str:
        """Unique identifier for this business rule."""
        ...

    @abc.abstractmethod
    def evaluate(self, request: EvaluationRequest) -> Decision | None:
        """Evaluate business rule against incoming evaluation request.

        Args:
            request: Incoming perishable stock evaluation context.

        Returns:
            Decision instance if rule triggered, or None to yield to next rule.
        """
        ...
