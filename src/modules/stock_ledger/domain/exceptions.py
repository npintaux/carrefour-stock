"""Domain exceptions for the stock ledger subsystem."""

from __future__ import annotations

from typing import Any


class StockLedgerError(Exception):
    """Base exception for all stock ledger domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize base domain error.

        Args:
            message: Human readable error message.
            code: Domain response code string.
            status_code: Corresponding HTTP status code.
            details: Optional structured details dictionary.
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class DepartmentScopeViolationError(StockLedgerError):
    """Raised when user attempts to access or modify stock outside authorized departments."""

    def __init__(
        self,
        message: str = "User is not authorized to access or modify stock in this department.",
        code: str = "ERR_OUT_OF_SCOPE_DEPARTMENT",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize department scope violation error."""
        super().__init__(message, code=code, status_code=403, details=details)


class InsufficientStockError(StockLedgerError):
    """Raised when requested stock deduction exceeds available quantity in zone."""

    def __init__(
        self,
        message: str = "Source zone has insufficient stock for this operation.",
        code: str = "ERR_INSUFFICIENT_STOCK",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize insufficient stock error."""
        super().__init__(message, code=code, status_code=422, details=details)


class InvalidPayloadError(StockLedgerError):
    """Raised when request payload or parameters are invalid."""

    def __init__(
        self,
        message: str = "Invalid request payload.",
        code: str = "INVALID_PAYLOAD",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize invalid payload error."""
        super().__init__(message, code=code, status_code=400, details=details)


class AdjustmentNotFoundError(StockLedgerError):
    """Raised when targeted adjustment record cannot be found."""

    def __init__(
        self,
        message: str = "Adjustment record not found.",
        code: str = "ADJUSTMENT_NOT_FOUND",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize adjustment not found error."""
        super().__init__(message, code=code, status_code=404, details=details)


class InvalidTransitionError(StockLedgerError):
    """Raised when adjustment is not in PENDING_DIRECTOR_APPROVAL state during sign-off."""

    def __init__(
        self,
        message: str = "Adjustment is not in PENDING_DIRECTOR_APPROVAL state.",
        code: str = "STATE_CONFLICT",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize invalid transition error."""
        super().__init__(message, code=code, status_code=409, details=details)


class UnauthorizedDirectorError(StockLedgerError):
    """Raised when non-director attempts to sign off on pending adjustment."""

    def __init__(
        self,
        message: str = "User is not authorized as Store Director.",
        code: str = "ERR_UNAUTHORIZED_DIRECTOR",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize unauthorized director error."""
        super().__init__(message, code=code, status_code=403, details=details)


class InternalServiceError(StockLedgerError):
    """Raised when an internal error occurs."""

    def __init__(
        self,
        message: str = "Internal server error occurred.",
        code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize internal service error."""
        super().__init__(message, code=code, status_code=500, details=details)
