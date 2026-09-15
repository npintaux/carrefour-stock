"""Sufficient stock verification rule (R2)."""

from __future__ import annotations

from ..models import AdjustmentEvaluationRequest, Decision
from ..repository import StockRepository
from .base import Rule


class SufficientStockRule(Rule):
    """Verifies that negative adjustments do not exceed available zone stock."""

    def __init__(self, repository: StockRepository) -> None:
        """Initialize sufficient stock rule with domain repository port.

        Args:
            repository: Domain repository port for reading stock balance.
        """
        self._repository = repository

    @property
    def rule_id(self) -> str:
        """Unique rule identifier."""
        return "R2_SUFFICIENT_STOCK"

    def evaluate(self, request: AdjustmentEvaluationRequest) -> Decision:
        """Evaluate whether sufficient stock exists for negative adjustment.

        Args:
            request: Adjustment evaluation request payload.

        Returns:
            Decision indicating whether inventory levels are sufficient.
        """
        # Positive adjustments increase stock and do not require balance validation
        if request.quantity_delta >= 0:
            return Decision(
                is_allowed=True,
                status_code=200,
                error_code=None,
                reason="Positive quantity delta does not require source stock validation.",
            )

        current_item = self._repository.get_stock_item(
            store_id=request.store_id,
            sku_id=request.sku_id,
            zone=request.zone,
        )

        required_qty = abs(request.quantity_delta)
        available_qty = current_item.quantity if current_item is not None else 0

        if available_qty < required_qty:
            return Decision(
                is_allowed=False,
                status_code=422,
                error_code="ERR_INSUFFICIENT_STOCK",
                reason=(
                    f"Insufficient stock balance in zone {request.zone.value}: "
                    f"available {available_qty}, requested {required_qty}."
                ),
            )

        return Decision(
            is_allowed=True,
            status_code=200,
            error_code=None,
            reason="Sufficient stock balance verified in source zone.",
        )
