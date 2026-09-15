"""Domain exceptions for inbound dock receiving and cold-chain evaluation."""

from __future__ import annotations


class InboundDockError(Exception):
    """Base exception for inbound dock domain errors."""

    def __init__(self, message: str, code: str = "INBOUND_DOCK_ERROR") -> None:
        """Initialize domain error with message and machine-readable error code.

        Args:
            message: Human-readable error description.
            code: Machine-readable error code identifier.
        """
        super().__init__(message)
        self.message = message
        self.code = code


class InvalidBarcodeError(InboundDockError):
    """Raised when an SSCC-18 or EAN-13 barcode is invalid or malformed."""

    def __init__(self, message: str) -> None:
        """Initialize InvalidBarcodeError with code INVALID_SSCC_BARCODE.

        Args:
            message: Human-readable error description.
        """
        super().__init__(message, code="INVALID_SSCC_BARCODE")


class MissingTemperatureError(InboundDockError):
    """Raised when probed temperature is omitted for chilled or frozen intake."""

    def __init__(self, message: str) -> None:
        """Initialize MissingTemperatureError with code MISSING_PROBE_TEMPERATURE.

        Args:
            message: Human-readable error description.
        """
        super().__init__(message, code="MISSING_PROBE_TEMPERATURE")


class ShipmentNotFoundError(InboundDockError):
    """Raised when referenced ASN shipment does not exist."""

    def __init__(self, message: str) -> None:
        """Initialize ShipmentNotFoundError with code SHIPMENT_NOT_FOUND.

        Args:
            message: Human-readable error description.
        """
        super().__init__(message, code="SHIPMENT_NOT_FOUND")


class PalletNotFoundError(InboundDockError):
    """Raised when referenced pallet SSCC does not exist in the shipment."""

    def __init__(self, message: str) -> None:
        """Initialize PalletNotFoundError with code PALLET_NOT_FOUND.

        Args:
            message: Human-readable error description.
        """
        super().__init__(message, code="PALLET_NOT_FOUND")


class InvalidTransitionError(InboundDockError):
    """Raised when a state transition is forbidden from the pallet's current state."""

    def __init__(self, message: str) -> None:
        """Initialize InvalidTransitionError with code STATE_CONFLICT.

        Args:
            message: Human-readable error description.
        """
        super().__init__(message, code="STATE_CONFLICT")


class ColdChainViolationError(InboundDockError):
    """Raised when probed temperature exceeds cold-chain regulatory bounds."""

    def __init__(self, message: str) -> None:
        """Initialize ColdChainViolationError with code COLD_CHAIN_VIOLATION.

        Args:
            message: Human-readable error description.
        """
        super().__init__(message, code="COLD_CHAIN_VIOLATION")


class DuplicateShipmentError(InboundDockError):
    """Raised when an ASN shipment with the same ID already exists."""

    def __init__(self, message: str) -> None:
        """Initialize DuplicateShipmentError with code DUPLICATE_SHIPMENT.

        Args:
            message: Human-readable error description.
        """
        super().__init__(message, code="DUPLICATE_SHIPMENT")


class DatabaseAdapterError(InboundDockError):
    """Raised when a persistence or database adapter operation fails."""

    def __init__(self, message: str) -> None:
        """Initialize DatabaseAdapterError with code INTERNAL_DATABASE_ERROR.

        Args:
            message: Human-readable error description.
        """
        super().__init__(message, code="INTERNAL_DATABASE_ERROR")
