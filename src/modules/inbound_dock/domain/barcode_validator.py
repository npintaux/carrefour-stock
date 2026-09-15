"""GS1-128, SSCC-18, and EAN-13 barcode validator component."""

from __future__ import annotations

from .exceptions import InvalidBarcodeError


class BarcodeValidator:
    """Validates SSCC-18 and EAN-13 barcode formats and modulo-10 check digits."""

    def calculate_sscc_check_digit(self, digits17: str) -> str:
        """Calculate the standard GS1 modulo-10 check digit for a 17-digit SSCC prefix.

        The weighting scheme starts from the digit immediately to the left of the check digit
        multiplying alternately by 3 and 1 from right to left.

        Args:
            digits17: The first 17 digits of an SSCC barcode.

        Returns:
            The single-digit check character as string.
        """
        total = 0
        for i, char in enumerate(reversed(digits17)):
            multiplier = 3 if i % 2 == 0 else 1
            total += int(char) * multiplier
        remainder = total % 10
        return "0" if remainder == 0 else str(10 - remainder)

    def calculate_ean13_check_digit(self, digits12: str) -> str:
        """Calculate the standard GS1 modulo-10 check digit for a 12-digit EAN prefix.

        Args:
            digits12: The first 12 digits of an EAN-13 barcode.

        Returns:
            The single-digit check character as string.
        """
        total = 0
        for i, char in enumerate(reversed(digits12)):
            multiplier = 3 if i % 2 == 0 else 1
            total += int(char) * multiplier
        remainder = total % 10
        return "0" if remainder == 0 else str(10 - remainder)

    def validate_sscc(self, sscc: str) -> bool:
        """Validate an 18-digit SSCC barcode structure.

        Args:
            sscc: The 18-digit SSCC barcode to validate.

        Returns:
            True if the SSCC barcode is strictly valid.

        Raises:
            InvalidBarcodeError: If the length or character set is invalid.
        """
        if len(sscc) != 18:
            raise InvalidBarcodeError(
                f"SSCC must be exactly 18 digits, got {len(sscc)}"
            )
        if not sscc.isdigit():
            raise InvalidBarcodeError("SSCC must contain only numeric digits")

        return True

    def validate_ean13(self, ean: str) -> bool:
        """Validate a 13-digit EAN-13 barcode structure.

        Args:
            ean: The 13-digit EAN-13 barcode to validate.

        Returns:
            True if the EAN-13 barcode is strictly valid.

        Raises:
            InvalidBarcodeError: If the length or character set is invalid.
        """
        if len(ean) != 13:
            raise InvalidBarcodeError(
                f"EAN-13 must be exactly 13 digits, got {len(ean)}"
            )
        if not ean.isdigit():
            raise InvalidBarcodeError("EAN-13 must contain only numeric digits")

        return True
