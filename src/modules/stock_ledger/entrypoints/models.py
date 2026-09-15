"""FastAPI schemas and transfer objects for stock_ledger entrypoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..domain.models import AdjustmentStatus, ReasonCode, StockZone


class ErrorResponseSchema(BaseModel):
    """Standard error response matching openapi.yaml."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class StockItemResponse(BaseModel):
    """StockItem schema matching openapi.yaml."""

    sku_id: str
    ean13: str
    product_name: str
    department_id: str
    zone: StockZone
    quantity: int
    unit_price_cents: int


class StockListResponse(BaseModel):
    """StockListResponse schema matching openapi.yaml."""

    store_id: str
    department_id: str
    total_items: int
    items: list[StockItemResponse]


class AdjustmentRequestSchema(BaseModel):
    """AdjustmentRequest schema matching openapi.yaml."""

    sku_id: str
    department_id: str
    zone: StockZone
    quantity_delta: int
    unit_price_cents: int = Field(ge=0)
    reason_code: ReasonCode
    initiator_id: str
    initiator_role: str
    user_departments: list[str]


class AdjustmentResponseSchema(BaseModel):
    """AdjustmentResponse schema matching openapi.yaml."""

    adjustment_id: str
    store_id: str
    sku_id: str
    department_id: str
    zone: StockZone
    quantity_delta: int
    total_value_cents: int
    status: AdjustmentStatus
    message: str
    director_note: str | None = None


class SignOffRequestSchema(BaseModel):
    """SignOffRequest schema matching openapi.yaml."""

    director_id: str
    action: str
    note: str | None = None


class TransferRequestSchema(BaseModel):
    """TransferRequest schema matching openapi.yaml."""

    sku_id: str
    department_id: str
    source_zone: StockZone
    target_zone: StockZone
    quantity: int = Field(ge=1)
    operator_id: str


class TransferResponseSchema(BaseModel):
    """TransferResponse schema matching openapi.yaml."""

    transfer_id: str
    store_id: str
    sku_id: str
    source_zone: StockZone
    target_zone: StockZone
    quantity: int
    status: str


class PosDepletionItemSchema(BaseModel):
    """PosDepletionItem schema matching openapi.yaml."""

    ean13: str
    quantity: int = Field(ge=1)


class PosDepletionRequestSchema(BaseModel):
    """PosDepletionRequest schema matching openapi.yaml."""

    receipt_id: str
    till_id: str
    timestamp: str
    items: list[PosDepletionItemSchema]


class PosDepletionResponseSchema(BaseModel):
    """PosDepletionResponse schema matching openapi.yaml."""

    receipt_id: str
    store_id: str
    processed_items: int
    status: str
