"""Payload validation rule ensuring required fields and positive values.

Traceability:
- [US-4][AC-4.1]: Rejection of invalid payload attributes (negative price, zero quantity, empty identifiers).
"""

from __future__ import annotations

from ..exceptions import InvalidMarkdownPayloadError
from ..models import Decision, EvaluationRequest
from .base import Rule


class PayloadValidationRule(Rule):
    """Rule validating evaluation payload structural constraints and invariants."""

    @property
    def rule_id(self) -> str:
        """Unique identifier for this rule."""
        return "R1-PAYLOAD-VALIDATION"

    def evaluate(self, request: EvaluationRequest) -> Decision | None:
        """Validate required fields, string non-emptiness, and positive values.

        Args:
            request: Evaluation request to validate.

        Returns:
            None if payload is valid, yielding to subsequent rules.

        Raises:
            InvalidMarkdownPayloadError: If any structural constraint is violated.
        """
        if not request.request_id or not request.request_id.strip():
            raise InvalidMarkdownPayloadError("request_id cannot be empty")
        if not request.store_id or not request.store_id.strip():
            raise InvalidMarkdownPayloadError("store_id cannot be empty")
        if not request.sku_id or not request.sku_id.strip():
            raise InvalidMarkdownPayloadError("sku_id cannot be empty")
        if not request.ean_barcode or not request.ean_barcode.strip():
            raise InvalidMarkdownPayloadError("ean_barcode cannot be empty")
        if not request.lot_number or not request.lot_number.strip():
            raise InvalidMarkdownPayloadError("lot_number cannot be empty")
        if request.original_price_cents <= 0:
            raise InvalidMarkdownPayloadError(
                "original_price_cents must be strictly positive"
            )
        if request.quantity <= 0:
            raise InvalidMarkdownPayloadError("quantity must be strictly positive")
        return None
