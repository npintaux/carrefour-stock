"""Tests for AdjustmentDecisionEngine."""

from __future__ import annotations

from unittest.mock import create_autospec

from src.modules.stock_ledger.domain.engine import AdjustmentDecisionEngine
from src.modules.stock_ledger.domain.models import (
    AdjustmentEvaluationRequest,
    ReasonCode,
    StockItem,
    StockZone,
)
from src.modules.stock_ledger.domain.repository import StockRepository
from src.modules.stock_ledger.domain.rules.department_scope_rule import (
    DepartmentScopeRule,
)
from src.modules.stock_ledger.domain.rules.dual_key_threshold_rule import (
    DualKeyThresholdRule,
)
from src.modules.stock_ledger.domain.rules.sufficient_stock_rule import (
    SufficientStockRule,
)


def test_engine_short_circuits_on_department_scope_failure() -> None:
    """[US-1][AC-1.2] Engine halts immediately if department scope rule fails."""
    repo = create_autospec(StockRepository, instance=True)
    engine = AdjustmentDecisionEngine(
        rules=[
            DepartmentScopeRule(),
            SufficientStockRule(repo),
            DualKeyThresholdRule(),
        ]
    )
    req = AdjustmentEvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-1",
        department_id="RAYON_EPICERIE",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-5,
        unit_price_cents=100,
        reason_code=ReasonCode.BREAKAGE,
        initiator_id="chef@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = engine.evaluate(req)
    assert decision.is_allowed is False
    assert decision.status_code == 403
    assert decision.error_code == "ERR_OUT_OF_SCOPE_DEPARTMENT"
    # Sufficient stock rule was never consulted
    repo.get_stock_item.assert_not_called()


def test_engine_short_circuits_on_insufficient_stock_failure() -> None:
    """[US-1][AC-1.2] Engine halts on insufficient stock failure before evaluating dual key."""
    repo = create_autospec(StockRepository, instance=True)
    repo.get_stock_item.return_value = StockItem(
        sku_id="SKU-1",
        ean13="12345",
        product_name="P",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity=2,
        unit_price_cents=10000,
    )
    engine = AdjustmentDecisionEngine(
        rules=[
            DepartmentScopeRule(),
            SufficientStockRule(repo),
            DualKeyThresholdRule(),
        ]
    )
    req = AdjustmentEvaluationRequest(
        request_id="req-2",
        store_id="STORE_FR_75015",
        sku_id="SKU-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,  # 10 units requested, only 2 available
        unit_price_cents=10000,
        reason_code=ReasonCode.THEFT,
        initiator_id="chef@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = engine.evaluate(req)
    assert decision.is_allowed is False
    assert decision.status_code == 422
    assert decision.error_code == "ERR_INSUFFICIENT_STOCK"


def test_engine_returns_hold_for_approval_when_threshold_exceeded() -> None:
    """[US-2][AC-2.1] Engine returns HOLD_FOR_APPROVAL (202) when all rules pass and value >= €500."""
    repo = create_autospec(StockRepository, instance=True)
    repo.get_stock_item.return_value = StockItem(
        sku_id="SKU-1",
        ean13="12345",
        product_name="P",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity=20,
        unit_price_cents=5500,
    )
    engine = AdjustmentDecisionEngine(
        rules=[
            DepartmentScopeRule(),
            SufficientStockRule(repo),
            DualKeyThresholdRule(),
        ]
    )
    req = AdjustmentEvaluationRequest(
        request_id="req-3",
        store_id="STORE_FR_75015",
        sku_id="SKU-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=5500,  # 10 * 55 = €550 >= €500
        reason_code=ReasonCode.THEFT,
        initiator_id="chef@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = engine.evaluate(req)
    assert decision.is_allowed is True
    assert decision.status_code == 202
    assert decision.action == "HOLD_FOR_APPROVAL"


def test_engine_returns_auto_approve_when_value_under_threshold() -> None:
    """[US-2][AC-2.1] Engine returns AUTO_APPROVE (200) when all rules pass and value < €500."""
    repo = create_autospec(StockRepository, instance=True)
    repo.get_stock_item.return_value = StockItem(
        sku_id="SKU-1",
        ean13="12345",
        product_name="P",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity=20,
        unit_price_cents=1000,
    )
    engine = AdjustmentDecisionEngine(
        rules=[
            DepartmentScopeRule(),
            SufficientStockRule(repo),
            DualKeyThresholdRule(),
        ]
    )
    req = AdjustmentEvaluationRequest(
        request_id="req-4",
        store_id="STORE_FR_75015",
        sku_id="SKU-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-2,
        unit_price_cents=1000,  # 2 * 10 = €20 < €500
        reason_code=ReasonCode.BREAKAGE,
        initiator_id="chef@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = engine.evaluate(req)
    assert decision.is_allowed is True
    assert decision.status_code == 200
    assert decision.action == "AUTO_APPROVE"


def test_engine_empty_rules_fallback() -> None:
    """[US-1][AC-1.1] Engine returns fallback auto-approve when rule list is empty."""
    engine = AdjustmentDecisionEngine(rules=[])
    req = AdjustmentEvaluationRequest(
        request_id="req-5",
        store_id="STORE_FR_75015",
        sku_id="SKU-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=0,
        unit_price_cents=0,
        reason_code=ReasonCode.OTHER,
        initiator_id="chef@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = engine.evaluate(req)
    assert decision.is_allowed is True
    assert decision.status_code == 200
    assert decision.action == "AUTO_APPROVE"
    assert len(engine.rules) == 0
