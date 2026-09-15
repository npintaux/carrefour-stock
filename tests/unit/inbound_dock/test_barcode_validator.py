"""Unit tests for BarcodeValidator component."""

from __future__ import annotations

import pytest

from src.modules.inbound_dock.domain.barcode_validator import BarcodeValidator
from src.modules.inbound_dock.domain.exceptions import InvalidBarcodeError


def test_us3_ac3_2_barcode_validator_valid_sscc() -> None:
    """[US-3][AC-3.2] Verify valid 18-digit SSCC barcodes pass validation."""
    validator = BarcodeValidator()
    calculated = validator.calculate_sscc_check_digit("03760000000000001")
    valid_sscc = f"03760000000000001{calculated}"
    assert validator.validate_sscc(valid_sscc) is True


def test_us3_ac3_2_barcode_validator_invalid_sscc() -> None:
    """[US-3][AC-3.2] Verify invalid SSCC barcodes raise InvalidBarcodeError."""
    validator = BarcodeValidator()

    # Length != 18
    with pytest.raises(InvalidBarcodeError, match="SSCC must be exactly 18 digits"):
        validator.validate_sscc("12345")

    # Non numeric
    with pytest.raises(
        InvalidBarcodeError, match="SSCC must contain only numeric digits"
    ):
        validator.validate_sscc("03760000000000001A")


def test_us3_ac3_2_barcode_validator_ean13() -> None:
    """[US-3][AC-3.2] Verify EAN-13 validation."""
    validator = BarcodeValidator()
    valid_ean = "3560070000014"
    assert validator.validate_ean13(valid_ean) is True

    with pytest.raises(InvalidBarcodeError, match="EAN-13 must be exactly 13 digits"):
        validator.validate_ean13("1234")

    with pytest.raises(
        InvalidBarcodeError, match="EAN-13 must contain only numeric digits"
    ):
        validator.validate_ean13("356007000001A")
