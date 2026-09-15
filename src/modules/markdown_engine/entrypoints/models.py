"""Pydantic schemas for markdown_engine HTTP API.

Traceability:
- [US-4][AC-4.1]: Evaluation and print label schemas.
- [US-4][AC-4.2]: POS feed schemas.
- [US-4][AC-4.3]: Donation schemas and error response schema.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class MarkdownEvaluationRequestSchema(BaseModel):
    """Schema for markdown evaluation request."""

    request_id: str
    store_id: str
    sku_id: str
    ean_barcode: str
    lot_number: str
    expiry_date: date
    original_price_cents: int = Field(..., ge=1)
    quantity: int = Field(..., ge=1)


class MarkdownEvaluationResponseSchema(BaseModel):
    """Schema for markdown evaluation response."""

    evaluation_id: str
    eligible: bool
    discount_percentage: int
    discounted_price_cents: int
    status: str
    rule_applied: str


class PrintLabelRequestSchema(BaseModel):
    """Schema for print label request."""

    request_id: str
    evaluation_id: str
    ean_barcode: str
    discounted_price_cents: int = Field(..., ge=1)
    quantity: int = Field(..., ge=1)
    printer_id: str


class PrintLabelResponseSchema(BaseModel):
    """Schema for print label response."""

    job_id: str
    promotional_barcode: str
    escpos_payload_base64: str
    labels_printed: int


class PosFeedPublishRequestSchema(BaseModel):
    """Schema for POS feed publish request."""

    request_id: str
    store_id: str
    ean_barcode: str
    promotional_barcode: str
    discounted_price_cents: int = Field(..., ge=1)
    valid_until: datetime


class PosFeedPublishResponseSchema(BaseModel):
    """Schema for POS feed publish response."""

    message_id: str
    topic: str
    published_at: str


class DonationSpoilageRequestSchema(BaseModel):
    """Schema for donation/spoilage request."""

    request_id: str
    store_id: str
    sku_id: str
    lot_number: str
    action_type: str
    quantity: int = Field(..., ge=1)
    original_value_cents: int = Field(..., ge=0)
    reason_code: str
    beneficiary_name: str | None = None


class DonationSpoilageResponseSchema(BaseModel):
    """Schema for donation/spoilage response."""

    record_id: str
    fiscal_slip_id: str
    action_type: str
    stock_decremented: bool
    timestamp: str


class ErrorResponseSchema(BaseModel):
    """Standardized error response schema."""

    code: str
    message: str
    details: dict[str, Any] | None = None
