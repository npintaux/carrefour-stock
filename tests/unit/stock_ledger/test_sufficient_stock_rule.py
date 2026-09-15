"""Tests for SufficientStockRule (R2)."""

from __future__ import annotations

from unittest.mock import create_autospec

from src.modules.stock_ledger.domain.models import (
    AdjustmentEvaluationRequest,
    ReasonCode,
    StockItem,
    StockZone,
)
from src.modules.stock_ledger.domain.repository import StockRepository
from src.modules.stock_ledger.domain.rules.sufficient_stock_rule import (
    SufficientStockRule,
)


def test_sufficient_stock_rule_id() -> None:
    """[US-1][AC-1.2] Verify SufficientStockRule rule_id."""
    repo = create_autospec(StockRepository, instance=True)
    rule = SufficientStockRule(repository=repo)
    assert rule.rule_id == "R2_SUFFICIENT_STOCK"


def test_positive_delta_always_allowed() -> None:
    """[US-1][AC-1.2] Positive quantity delta (stock count increase) does not check source balance."""
    repo = create_autospec(StockRepository, instance=True)
    rule = SufficientStockRule(repository=repo)
    req = AdjustmentEvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=10,
        unit_price_cents=200,
        reason_code=ReasonCode.MISCOUNT,
        initiator_id="chef_frais@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = rule.evaluate(req)
    assert decision.is_allowed is True
    assert decision.status_code == 200
    repo.get_stock_item.assert_not_called()


def test_negative_delta_with_sufficient_stock_allowed() -> None:
    """[US-1][AC-1.2] Negative quantity delta within current available balance is allowed."""
    repo = create_autospec(StockRepository, instance=True)
    repo.get_stock_item.return_value = StockItem(
        sku_id="SKU-FRAIS-1",
        ean13="3560070123456",
        product_name="Milk",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity=20,
        unit_price_cents=200,
    )
    rule = SufficientStockRule(repository=repo)
    req = AdjustmentEvaluationRequest(
        request_id="req-2",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=200,
        reason_code=ReasonCode.BREAKAGE,
        initiator_id="chef_frais@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = rule.evaluate(req)
    assert decision.is_allowed is True
    assert decision.status_code == 200


def test_negative_delta_with_insufficient_stock_rejected() -> None:
    """[US-1][AC-1.2] Negative delta exceeding current balance returns 422 ERR_INSUFFICIENT_STOCK."""
    repo = create_autospec(StockRepository, instance=True)
    repo.get_stock_item.return_value = StockItem(
        sku_id="SKU-FRAIS-1",
        ean13="3560070123456",
        product_name="Milk",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity=5,
        unit_price_cents=200,
    )
    rule = SufficientStockRule(repository=repo)
    req = AdjustmentEvaluationRequest(
        request_id="req-3",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=200,
        reason_code=ReasonCode.THEFT,
        initiator_id="chef_frais@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = rule.evaluate(req)
    assert decision.is_allowed is False
    assert decision.status_code == 422
    assert decision.error_code == "ERR_INSUFFICIENT_STOCK"


def test_negative_delta_with_missing_item_rejected() -> None:
    """[US-1][AC-1.2] Negative delta on non-existent stock item returns 422 ERR_INSUFFICIENT_STOCK."""
    repo = create_autospec(StockRepository, instance=True)
    repo.get_stock_item.return_value = None
    rule = SufficientStockRule(repository=repo)
    req = AdjustmentEvaluationRequest(
        request_id="req-4",
        store_id="STORE_FR_75015",
        sku_id="SKU-UNKNOWN",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-1,
        unit_price_cents=200,
        reason_code=ReasonCode.THEFT,
        initiator_id="chef_frais@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = rule.evaluate(req)
    assert decision.is_allowed is False
    assert decision.status_code == 422
    assert decision.error_code == "ERR_INSUFFICIENT_STOCK"
