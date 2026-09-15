"""Tests for DualKeyThresholdRule (R3)."""

from __future__ import annotations

from src.modules.stock_ledger.domain.models import (
    AdjustmentEvaluationRequest,
    ReasonCode,
    StockZone,
)
from src.modules.stock_ledger.domain.rules.dual_key_threshold_rule import (
    DualKeyThresholdRule,
)


def test_dual_key_threshold_rule_id() -> None:
    """[US-2][AC-2.1] Verify DualKeyThresholdRule rule_id."""
    rule = DualKeyThresholdRule()
    assert rule.rule_id == "R3_DUAL_KEY_THRESHOLD"


def test_adjustment_below_500_euros_auto_approved() -> None:
    """[US-2][AC-2.1] Total value < €500 is auto-approved with HTTP 200."""
    rule = DualKeyThresholdRule()
    # 4 units of €100.00 each = €400.00 (40000 cents)
    req = AdjustmentEvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-4,
        unit_price_cents=10000,
        reason_code=ReasonCode.BREAKAGE,
        initiator_id="chef_frais@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = rule.evaluate(req)
    assert decision.is_allowed is True
    assert decision.status_code == 200
    assert decision.action == "AUTO_APPROVE"
    assert decision.error_code is None


def test_adjustment_at_or_above_500_euros_held_for_approval() -> None:
    """[US-2][AC-2.1] Total value >= €500 is held for director approval with HTTP 202."""
    rule = DualKeyThresholdRule()
    # 10 units of €55.00 each = €550.00 (55000 cents)
    req = AdjustmentEvaluationRequest(
        request_id="req-2",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=5500,
        reason_code=ReasonCode.THEFT,
        initiator_id="chef_frais@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = rule.evaluate(req)
    assert decision.is_allowed is True
    assert decision.status_code == 202
    assert decision.action == "HOLD_FOR_APPROVAL"
    assert decision.error_code is None


def test_positive_delta_threshold_calculation() -> None:
    """[US-2][AC-2.1] Positive delta magnitude also respects threshold."""
    rule = DualKeyThresholdRule()
    # 5 units of €100.00 each = €500.00 exact threshold
    req = AdjustmentEvaluationRequest(
        request_id="req-3",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=5,
        unit_price_cents=10000,
        reason_code=ReasonCode.MISCOUNT,
        initiator_id="chef_frais@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = rule.evaluate(req)
    assert decision.is_allowed is True
    assert decision.status_code == 202
    assert decision.action == "HOLD_FOR_APPROVAL"
