"""Tests for base Rule ABC and StockRepository ABC."""

from __future__ import annotations

import pytest

from src.modules.stock_ledger.domain.models import (
    AdjustmentEvaluationRequest,
    AdjustmentRecord,
    Decision,
    ReasonCode,
    StockItem,
    StockZone,
)
from src.modules.stock_ledger.domain.repository import StockRepository
from src.modules.stock_ledger.domain.rules.base import Rule


class DummyRule(Rule):
    """Dummy rule implementation for testing Rule ABC."""

    @property
    def rule_id(self) -> str:
        """Return dummy rule id."""
        return "R_DUMMY"

    def evaluate(self, request: AdjustmentEvaluationRequest) -> Decision:
        """Return dummy decision."""
        return Decision(
            is_allowed=True,
            status_code=200,
            error_code=None,
            reason="Dummy passed",
        )


class DummyRepo(StockRepository):
    """Dummy repository implementation for testing StockRepository ABC."""

    def get_stock(
        self,
        store_id: str,
        department_id: str,
        zone: StockZone | None = None,
    ) -> list[StockItem]:
        """Return empty stock list."""
        return []

    def get_stock_item(
        self,
        store_id: str,
        sku_id: str,
        zone: StockZone,
    ) -> StockItem | None:
        """Return None."""
        return None

    def update_stock_quantity(
        self,
        store_id: str,
        sku_id: str,
        zone: StockZone,
        quantity_delta: int,
    ) -> StockItem:
        """Return dummy updated item."""
        return StockItem(
            sku_id=sku_id,
            ean13="1234567890123",
            product_name="Dummy",
            department_id="RAYON_FRAIS",
            zone=zone,
            quantity=10,
            unit_price_cents=100,
        )

    def save_adjustment(self, record: AdjustmentRecord) -> AdjustmentRecord:
        """Return record."""
        return record

    def get_adjustment(
        self,
        store_id: str,
        adjustment_id: str,
    ) -> AdjustmentRecord | None:
        """Return None."""
        return None

    def update_adjustment(self, record: AdjustmentRecord) -> AdjustmentRecord:
        """Return record."""
        return record

    def check_and_set_idempotency(self, key: str) -> bool:
        """Return True."""
        return True

    def get_stock_item_by_ean(
        self,
        store_id: str,
        ean13: str,
        zone: StockZone,
    ) -> StockItem | None:
        """Return None."""
        return None


def test_rule_abc_instantiation() -> None:
    """[US-1][AC-1.2] Verify Rule ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
        Rule()  # type: ignore[abstract]

    rule = DummyRule()
    assert rule.rule_id == "R_DUMMY"
    req = AdjustmentEvaluationRequest(
        request_id="req-1",
        store_id="STORE_1",
        sku_id="SKU-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-1,
        unit_price_cents=100,
        reason_code=ReasonCode.BREAKAGE,
        initiator_id="user-1",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = rule.evaluate(req)
    assert decision.is_allowed is True


def test_stock_repository_abc_instantiation() -> None:
    """[US-1][AC-1.1] Verify StockRepository ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
        StockRepository()  # type: ignore[abstract]

    repo = DummyRepo()
    assert repo.get_stock("S1", "D1") == []
