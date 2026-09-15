"""Tests for domain models and exceptions in stock_ledger."""

from __future__ import annotations

import pytest

from src.modules.stock_ledger.domain.exceptions import (
    AdjustmentNotFoundError,
    DepartmentScopeViolationError,
    InsufficientStockError,
    InternalServiceError,
    InvalidPayloadError,
    InvalidTransitionError,
    StockLedgerError,
    UnauthorizedDirectorError,
)
from src.modules.stock_ledger.domain.models import (
    AdjustmentEvaluationRequest,
    AdjustmentRecord,
    AdjustmentStatus,
    Decision,
    ReasonCode,
    StockItem,
    StockZone,
)


def test_stock_zone_values() -> None:
    """[US-1][AC-1.1] Verify stock zone enum members and values."""
    assert StockZone.RECEIVING_DOCK.value == "RECEIVING_DOCK"
    assert StockZone.COLD_STORAGE_RESERVE.value == "COLD_STORAGE_RESERVE"
    assert StockZone.DRY_RESERVE.value == "DRY_RESERVE"
    assert StockZone.IN_TRANSIT_FLOOR.value == "IN_TRANSIT_FLOOR"
    assert StockZone.SALES_FLOOR_FACING.value == "SALES_FLOOR_FACING"
    assert StockZone.QUARANTINE_DAMAGED.value == "QUARANTINE_DAMAGED"
    assert (
        StockZone.CUSTOMER_CLICK_COLLECT_STAGED.value == "CUSTOMER_CLICK_COLLECT_STAGED"
    )


def test_adjustment_status_values() -> None:
    """[US-2][AC-2.1] Verify adjustment status enum members."""
    assert AdjustmentStatus.AUTO_APPROVED.value == "AUTO_APPROVED"
    assert (
        AdjustmentStatus.PENDING_DIRECTOR_APPROVAL.value == "PENDING_DIRECTOR_APPROVAL"
    )
    assert AdjustmentStatus.APPROVED.value == "APPROVED"
    assert AdjustmentStatus.REJECTED.value == "REJECTED"


def test_reason_code_values() -> None:
    """[US-2][AC-2.1] Verify reason code enum members."""
    assert ReasonCode.THEFT.value == "THEFT"
    assert ReasonCode.BREAKAGE.value == "BREAKAGE"
    assert ReasonCode.INTERNAL_CONSUMPTION.value == "INTERNAL_CONSUMPTION"
    assert ReasonCode.MISCOUNT.value == "MISCOUNT"
    assert ReasonCode.EXPIRY_SPOILAGE.value == "EXPIRY_SPOILAGE"
    assert ReasonCode.OTHER.value == "OTHER"


def test_stock_item_immutability() -> None:
    """[US-1][AC-1.1] Verify StockItem is an immutable dataclass."""
    item = StockItem(
        sku_id="SKU-1",
        ean13="3560070123456",
        product_name="Milk",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity=50,
        unit_price_cents=120,
    )
    assert item.sku_id == "SKU-1"
    assert item.quantity == 50
    with pytest.raises(AttributeError):
        # dataclass is frozen
        item.quantity = 60  # type: ignore[misc]


def test_adjustment_evaluation_request_defaults() -> None:
    """[US-2][AC-2.1] Verify default threshold in AdjustmentEvaluationRequest."""
    req = AdjustmentEvaluationRequest(
        request_id="req-1",
        store_id="STORE_1",
        sku_id="SKU-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-5,
        unit_price_cents=1000,
        reason_code=ReasonCode.THEFT,
        initiator_id="user-1",
        initiator_role="CHEF_DE_RAYON",
        user_departments=("RAYON_FRAIS",),
    )
    assert req.threshold_cents == 50000
    assert req.quantity_delta == -5


def test_decision_and_record_dataclasses() -> None:
    """[US-2][AC-2.2] Verify Decision and AdjustmentRecord models."""
    dec = Decision(
        is_allowed=True,
        status_code=200,
        error_code=None,
        reason="Approved",
        action="AUTO_APPROVE",
    )
    assert dec.is_allowed is True
    assert dec.action == "AUTO_APPROVE"

    rec = AdjustmentRecord(
        adjustment_id="adj-1",
        store_id="STORE_1",
        sku_id="SKU-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=5500,
        total_value_cents=55000,
        reason_code=ReasonCode.BREAKAGE,
        initiator_id="user-1",
        status=AdjustmentStatus.PENDING_DIRECTOR_APPROVAL,
    )
    assert rec.total_value_cents == 55000
    assert rec.director_id is None


def test_custom_exceptions_inheritance_and_fields() -> None:
    """[US-1][AC-1.2] Verify exception hierarchy and custom attributes."""
    err = DepartmentScopeViolationError(
        "Scope violation", code="ERR_OUT_OF_SCOPE_DEPARTMENT"
    )
    assert isinstance(err, StockLedgerError)
    assert err.code == "ERR_OUT_OF_SCOPE_DEPARTMENT"
    assert str(err) == "Scope violation"

    insuf = InsufficientStockError("Out of stock")
    assert insuf.code == "ERR_INSUFFICIENT_STOCK"

    inv_pay = InvalidPayloadError("Bad payload")
    assert inv_pay.code == "INVALID_PAYLOAD"

    not_found = AdjustmentNotFoundError("Adjustment missing")
    assert not_found.code == "ADJUSTMENT_NOT_FOUND"

    trans_err = InvalidTransitionError("Cannot sign off")
    assert trans_err.code == "STATE_CONFLICT"

    unauth_dir = UnauthorizedDirectorError("Only director")
    assert unauth_dir.code == "ERR_UNAUTHORIZED_DIRECTOR"

    internal_err = InternalServiceError("DB down")
    assert internal_err.code == "INTERNAL_ERROR"
