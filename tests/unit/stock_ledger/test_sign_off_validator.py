"""Tests for SignOffValidator (S1)."""

from __future__ import annotations

import pytest

from src.modules.stock_ledger.domain.exceptions import (
    AdjustmentNotFoundError,
    InvalidPayloadError,
    InvalidTransitionError,
    UnauthorizedDirectorError,
)
from src.modules.stock_ledger.domain.models import (
    AdjustmentRecord,
    AdjustmentStatus,
    ReasonCode,
    StockZone,
)
from src.modules.stock_ledger.domain.rules.sign_off_validator import SignOffValidator


def test_sign_off_validator_approve_success() -> None:
    """[US-2][AC-2.2] Store Director can approve pending adjustment."""
    validator = SignOffValidator()
    record = AdjustmentRecord(
        adjustment_id="adj-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=5500,
        total_value_cents=55000,
        reason_code=ReasonCode.THEFT,
        initiator_id="chef@carrefour.com",
        status=AdjustmentStatus.PENDING_DIRECTOR_APPROVAL,
    )
    result = validator.validate(
        record=record,
        director_id="director@carrefour.com",
        director_role="DIRECTEUR_MAGASIN",
        action="APPROVE",
        note=None,
    )
    assert result is True


def test_sign_off_validator_reject_success_with_note() -> None:
    """[US-2][AC-2.3] Store Director can reject pending adjustment when note is provided."""
    validator = SignOffValidator()
    record = AdjustmentRecord(
        adjustment_id="adj-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=5500,
        total_value_cents=55000,
        reason_code=ReasonCode.THEFT,
        initiator_id="chef@carrefour.com",
        status=AdjustmentStatus.PENDING_DIRECTOR_APPROVAL,
    )
    result = validator.validate(
        record=record,
        director_id="director@carrefour.com",
        director_role="DIRECTEUR_MAGASIN",
        action="REJECT",
        note="Physical items found in backup storage shelf.",
    )
    assert result is True


def test_sign_off_validator_missing_record() -> None:
    """[US-2][AC-2.2] Missing adjustment record raises AdjustmentNotFoundError (404)."""
    validator = SignOffValidator()
    with pytest.raises(AdjustmentNotFoundError):
        validator.validate(
            record=None,
            director_id="director@carrefour.com",
            director_role="DIRECTEUR_MAGASIN",
            action="APPROVE",
            note=None,
        )


def test_sign_off_validator_unauthorized_role() -> None:
    """[US-2][AC-2.2] Non-director role raises UnauthorizedDirectorError (403)."""
    validator = SignOffValidator()
    record = AdjustmentRecord(
        adjustment_id="adj-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=5500,
        total_value_cents=55000,
        reason_code=ReasonCode.THEFT,
        initiator_id="chef@carrefour.com",
        status=AdjustmentStatus.PENDING_DIRECTOR_APPROVAL,
    )
    with pytest.raises(UnauthorizedDirectorError):
        validator.validate(
            record=record,
            director_id="chef@carrefour.com",
            director_role="CHEF_DE_RAYON",
            action="APPROVE",
            note=None,
        )


def test_sign_off_validator_invalid_transition() -> None:
    """[US-2][AC-2.2] Record not in PENDING_DIRECTOR_APPROVAL raises InvalidTransitionError (409)."""
    validator = SignOffValidator()
    record = AdjustmentRecord(
        adjustment_id="adj-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=5500,
        total_value_cents=55000,
        reason_code=ReasonCode.THEFT,
        initiator_id="chef@carrefour.com",
        status=AdjustmentStatus.APPROVED,
    )
    with pytest.raises(InvalidTransitionError):
        validator.validate(
            record=record,
            director_id="director@carrefour.com",
            director_role="DIRECTEUR_MAGASIN",
            action="APPROVE",
            note=None,
        )


def test_sign_off_validator_invalid_action() -> None:
    """[US-2][AC-2.2] Invalid action raises InvalidPayloadError (400)."""
    validator = SignOffValidator()
    record = AdjustmentRecord(
        adjustment_id="adj-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=5500,
        total_value_cents=55000,
        reason_code=ReasonCode.THEFT,
        initiator_id="chef@carrefour.com",
        status=AdjustmentStatus.PENDING_DIRECTOR_APPROVAL,
    )
    with pytest.raises(InvalidPayloadError, match="Action must be APPROVE or REJECT"):
        validator.validate(
            record=record,
            director_id="director@carrefour.com",
            director_role="DIRECTEUR_MAGASIN",
            action="UNKNOWN",
            note=None,
        )


def test_sign_off_validator_reject_missing_note() -> None:
    """[US-2][AC-2.3] REJECT action without explanation note raises InvalidPayloadError (400)."""
    validator = SignOffValidator()
    record = AdjustmentRecord(
        adjustment_id="adj-1",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=5500,
        total_value_cents=55000,
        reason_code=ReasonCode.THEFT,
        initiator_id="chef@carrefour.com",
        status=AdjustmentStatus.PENDING_DIRECTOR_APPROVAL,
    )
    with pytest.raises(InvalidPayloadError, match="Mandatory justification note"):
        validator.validate(
            record=record,
            director_id="director@carrefour.com",
            director_role="DIRECTEUR_MAGASIN",
            action="REJECT",
            note="   ",
        )
