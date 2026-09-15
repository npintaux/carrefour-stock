"""Public HTTP API entrypoints for markdown_engine subsystem.

Traceability:
- [US-4][AC-4.1]: POST /v1/markdown/evaluate and POST /v1/markdown/print-label.
- [US-4][AC-4.2]: POST /v1/markdown/pos-feed.
- [US-4][AC-4.3]: POST /v1/markdown/donations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import FastAPI, Header, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..adapters.memory_donation_ledger_adapter import InMemoryDonationLedgerAdapter
from ..adapters.memory_pos_publisher_adapter import InMemoryPosPublisherAdapter
from ..adapters.memory_printer_adapter import InMemoryPrinterAdapter
from ..domain.engine import MarkdownEngine
from ..domain.exceptions import (
    IneligibleMarkdownError,
    MarkdownEngineError,
    PrinterCommunicationError,
    PubSubPublishError,
)
from ..domain.models import EvaluationRequest

app = FastAPI(
    title="Markdown Engine Service API",
    version="1.0.0",
    description="Machine-readable OpenAPI contract for Carrefour Stock Flow markdown_engine subsystem.",
)

# Shared domain services and adapters
_engine = MarkdownEngine()
_printer_adapter = InMemoryPrinterAdapter()
_pos_publisher_adapter = InMemoryPosPublisherAdapter()
_donation_ledger_adapter = InMemoryDonationLedgerAdapter()


from .models import (
    DonationSpoilageRequestSchema,
    DonationSpoilageResponseSchema,
    ErrorResponseSchema,
    MarkdownEvaluationRequestSchema,
    MarkdownEvaluationResponseSchema,
    PosFeedPublishRequestSchema,
    PosFeedPublishResponseSchema,
    PrintLabelRequestSchema,
    PrintLabelResponseSchema,
)


# Exception Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle FastAPI/Pydantic validation errors with HTTP 400."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "code": "INVALID_PAYLOAD",
            "message": "Validation failure in request payload.",
            "details": {"errors": exc.errors()},
        },
    )


@app.exception_handler(MarkdownEngineError)
async def domain_exception_handler(
    request: Request, exc: MarkdownEngineError
) -> JSONResponse:
    """Handle custom domain exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": dict(exc.details) if exc.details else {},
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected faults with generic 500 without leaking trace."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An internal service error occurred.",
            "details": {},
        },
    )


# Endpoints
@app.post(
    "/v1/markdown/evaluate",
    response_model=MarkdownEvaluationResponseSchema,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponseSchema},
        422: {"model": ErrorResponseSchema},
        500: {"model": ErrorResponseSchema},
    },
)
async def evaluate_markdown(
    payload: MarkdownEvaluationRequestSchema,
    x_simulate_fault: str | None = Header(default=None, alias="X-Simulate-Fault"),
) -> MarkdownEvaluationResponseSchema:
    """Evaluate markdown eligibility and calculate dynamic discount."""
    if x_simulate_fault:
        raise MarkdownEngineError("Datastore disconnected", status_code=500)

    domain_request = EvaluationRequest(
        request_id=payload.request_id,
        store_id=payload.store_id,
        sku_id=payload.sku_id,
        ean_barcode=payload.ean_barcode,
        lot_number=payload.lot_number,
        expiry_date=payload.expiry_date,
        original_price_cents=payload.original_price_cents,
        quantity=payload.quantity,
    )

    decision = _engine.evaluate(domain_request)
    evaluation_id = f"EVAL-{uuid.uuid4().hex[:12].upper()}"

    return MarkdownEvaluationResponseSchema(
        evaluation_id=evaluation_id,
        eligible=decision.eligible,
        discount_percentage=decision.discount_percentage,
        discounted_price_cents=decision.discounted_price_cents,
        status=decision.status.value,
        rule_applied=decision.rule_applied,
    )


@app.post(
    "/v1/markdown/print-label",
    response_model=PrintLabelResponseSchema,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponseSchema},
        422: {"model": ErrorResponseSchema},
        500: {"model": ErrorResponseSchema},
    },
)
async def print_markdown_label(
    payload: PrintLabelRequestSchema,
    x_simulate_fault: str | None = Header(default=None, alias="X-Simulate-Fault"),
) -> PrintLabelResponseSchema:
    """Generate ESC/POS promotional markdown barcode label payload."""
    if x_simulate_fault == "PRINTER_SUBSYSTEM_ERROR":
        raise PrinterCommunicationError("Printer subsystem error simulated")

    # Business rule check: unauthorized or offline printer check
    if payload.printer_id.startswith("UNAUTHORIZED"):
        raise IneligibleMarkdownError(
            f"Printer '{payload.printer_id}' is unauthorized or in offline status."
        )

    print_cmd = _printer_adapter.print_label(
        request_id=payload.request_id,
        evaluation_id=payload.evaluation_id,
        ean_barcode=payload.ean_barcode,
        discounted_price_cents=payload.discounted_price_cents,
        quantity=payload.quantity,
        printer_id=payload.printer_id,
    )

    return PrintLabelResponseSchema(
        job_id=print_cmd.job_id,
        promotional_barcode=print_cmd.promotional_barcode,
        escpos_payload_base64=print_cmd.escpos_payload_base64,
        labels_printed=print_cmd.labels_printed,
    )


@app.post(
    "/v1/markdown/pos-feed",
    response_model=PosFeedPublishResponseSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponseSchema},
        422: {"model": ErrorResponseSchema},
        500: {"model": ErrorResponseSchema},
    },
)
async def publish_pos_markdown_event(
    payload: PosFeedPublishRequestSchema,
    x_simulate_fault: str | None = Header(default=None, alias="X-Simulate-Fault"),
) -> PosFeedPublishResponseSchema:
    """Broadcast markdown event to POS feed via Pub/Sub."""
    if x_simulate_fault:
        raise PubSubPublishError("Pub/Sub service unavailable simulated")

    # Business rule check: valid_until cannot be in the past
    now = datetime.now(UTC)
    if payload.valid_until < now:
        raise IneligibleMarkdownError("valid_until timestamp cannot be in the past.")

    msg = _pos_publisher_adapter.publish_pos_markdown(
        request_id=payload.request_id,
        store_id=payload.store_id,
        ean_barcode=payload.ean_barcode,
        promotional_barcode=payload.promotional_barcode,
        discounted_price_cents=payload.discounted_price_cents,
        valid_until=payload.valid_until,
    )

    return PosFeedPublishResponseSchema(
        message_id=msg.message_id,
        topic=msg.topic,
        published_at=msg.published_at.isoformat(),
    )


@app.post(
    "/v1/markdown/donations",
    response_model=DonationSpoilageResponseSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponseSchema},
        422: {"model": ErrorResponseSchema},
        500: {"model": ErrorResponseSchema},
    },
)
async def record_donation_or_spoilage(
    payload: DonationSpoilageRequestSchema,
    x_simulate_fault: str | None = Header(default=None, alias="X-Simulate-Fault"),
) -> DonationSpoilageResponseSchema:
    """Record AGEC charity donation or bio-waste spoilage write-off."""
    if x_simulate_fault:
        raise MarkdownEngineError("Datastore failure", status_code=500)

    allowed_actions = ("CHARITY_DONATION", "BIO_WASTE_REMOVAL")
    if payload.action_type not in allowed_actions:
        raise IneligibleMarkdownError(
            f"Action type '{payload.action_type}' is invalid. Allowed: {allowed_actions}"
        )

    rec = _donation_ledger_adapter.record_donation_or_spoilage(
        request_id=payload.request_id,
        store_id=payload.store_id,
        sku_id=payload.sku_id,
        lot_number=payload.lot_number,
        action_type=payload.action_type,
        quantity=payload.quantity,
        original_value_cents=payload.original_value_cents,
        reason_code=payload.reason_code,
        beneficiary_name=payload.beneficiary_name,
    )

    return DonationSpoilageResponseSchema(
        record_id=rec.record_id,
        fiscal_slip_id=rec.fiscal_slip_id,
        action_type=rec.action_type,
        stock_decremented=rec.stock_decremented,
        timestamp=rec.timestamp.isoformat(),
    )
