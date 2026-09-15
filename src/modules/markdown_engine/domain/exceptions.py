"""Domain exception hierarchy for the markdown engine subsystem.

Traceability:
- [US-4][AC-4.1]: InvalidMarkdownPayloadError, ItemAlreadyExpiredError, IneligibleMarkdownError.
- [US-4][AC-4.2]: PubSubPublishError.
- [US-4][AC-4.3]: InternalServiceError, PrinterCommunicationError.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class MarkdownEngineError(Exception):
    """Base exception for all markdown engine domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize domain exception.

        Args:
            message: Human-readable error message.
            code: Domain error code string.
            status_code: Corresponding HTTP status code.
            details: Optional diagnostic attributes.
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class InvalidMarkdownPayloadError(MarkdownEngineError):
    """Raised when an incoming request payload fails structural validation."""

    def __init__(
        self,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize invalid payload error with HTTP 400."""
        super().__init__(
            message=message,
            code="INVALID_PAYLOAD",
            status_code=400,
            details=details,
        )


class ItemAlreadyExpiredError(MarkdownEngineError):
    """Raised when an item is past its expiration date and ineligible for retail sale markdown."""

    def __init__(
        self,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize expired item error with HTTP 422."""
        super().__init__(
            message=message,
            code="ITEM_EXPIRED_DONATION_REQUIRED",
            status_code=422,
            details=details,
        )


class IneligibleMarkdownError(MarkdownEngineError):
    """Raised when a lot or item is ineligible for markdown discount."""

    def __init__(
        self,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize ineligible error with HTTP 422."""
        super().__init__(
            message=message,
            code="INELIGIBLE_FOR_MARKDOWN",
            status_code=422,
            details=details,
        )


class PrinterCommunicationError(MarkdownEngineError):
    """Raised when communication with a thermal label printer fails."""

    def __init__(
        self,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize printer failure error with HTTP 500."""
        super().__init__(
            message=message,
            code="PRINTER_COMMUNICATION_ERROR",
            status_code=500,
            details=details,
        )


class PubSubPublishError(MarkdownEngineError):
    """Raised when dispatching an event to Cloud Pub/Sub fails."""

    def __init__(
        self,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize pubsub publish error with HTTP 500."""
        super().__init__(
            message=message,
            code="PUBSUB_BROADCAST_FAILURE",
            status_code=500,
            details=details,
        )


class InternalServiceError(MarkdownEngineError):
    """Raised when an unrecoverable internal error occurs."""

    def __init__(
        self,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize internal error with HTTP 500."""
        super().__init__(
            message=message,
            code="INTERNAL_ERROR",
            status_code=500,
            details=details,
        )
