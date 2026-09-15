"""Tests for DepartmentScopeRule (R1)."""

from __future__ import annotations

from src.modules.stock_ledger.domain.models import (
    AdjustmentEvaluationRequest,
    ReasonCode,
    StockZone,
)
from src.modules.stock_ledger.domain.rules.department_scope_rule import (
    DepartmentScopeRule,
)


def test_department_scope_rule_id() -> None:
    """[US-1][AC-1.1] Verify DepartmentScopeRule rule_id."""
    rule = DepartmentScopeRule()
    assert rule.rule_id == "R1_DEPARTMENT_SCOPE"


def test_department_scope_allowed_for_matching_department() -> None:
    """[US-1][AC-1.1] Allow chef de rayon when department is within user_departments."""
    rule = DepartmentScopeRule()
    req = AdjustmentEvaluationRequest(
        request_id="req-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-5,
        unit_price_cents=200,
        reason_code=ReasonCode.BREAKAGE,
        initiator_id="chef_frais@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS", "RAYON_BOISSONS"),
    )
    decision = rule.evaluate(req)
    assert decision.is_allowed is True
    assert decision.status_code == 200
    assert decision.error_code is None


def test_department_scope_rejected_for_mismatched_department() -> None:
    """[US-1][AC-1.2] Reject chef de rayon when department is not within user_departments."""
    rule = DepartmentScopeRule()
    req = AdjustmentEvaluationRequest(
        request_id="req-2",
        store_id="STORE_FR_75015",
        sku_id="SKU-EPICERIE-1",
        department_id="RAYON_EPICERIE",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-5,
        unit_price_cents=200,
        reason_code=ReasonCode.BREAKAGE,
        initiator_id="chef_frais@carrefour.com",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    decision = rule.evaluate(req)
    assert decision.is_allowed is False
    assert decision.status_code == 403
    assert decision.error_code == "ERR_OUT_OF_SCOPE_DEPARTMENT"


def test_department_scope_allowed_for_store_director() -> None:
    """[US-1][AC-1.1] Allow store director regardless of user_departments."""
    rule = DepartmentScopeRule()
    req = AdjustmentEvaluationRequest(
        request_id="req-3",
        store_id="STORE_FR_75015",
        sku_id="SKU-EPICERIE-1",
        department_id="RAYON_EPICERIE",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-5,
        unit_price_cents=200,
        reason_code=ReasonCode.BREAKAGE,
        initiator_id="director@carrefour.com",
        initiator_role="DIRECTEUR_MAGASIN",
        user_departments=(),
    )
    decision = rule.evaluate(req)
    assert decision.is_allowed is True
    assert decision.status_code == 200
