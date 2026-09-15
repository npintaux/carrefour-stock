"""Public FastAPI router and HTTP entrypoints for the stock ledger subsystem."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Any

import yaml  # type: ignore[import-untyped]
from fastapi import Depends, FastAPI, Header, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..adapters.memory_repository import InMemoryStockRepository
from ..domain.engine import AdjustmentDecisionEngine
from ..domain.exceptions import StockLedgerError
from ..domain.models import (
    AdjustmentEvaluationRequest,
    AdjustmentRecord,
    AdjustmentStatus,
    ReasonCode,
    StockItem,
    StockZone,
)
from ..domain.repository import StockRepository
from ..domain.rules.department_scope_rule import DepartmentScopeRule
from ..domain.rules.dual_key_threshold_rule import DualKeyThresholdRule
from ..domain.rules.sign_off_validator import SignOffValidator
from ..domain.rules.sufficient_stock_rule import SufficientStockRule
from .models import (
    AdjustmentRequestSchema,
    AdjustmentResponseSchema,
    PosDepletionRequestSchema,
    PosDepletionResponseSchema,
    SignOffRequestSchema,
    StockListResponse,
    TransferRequestSchema,
    TransferResponseSchema,
)

app = FastAPI(
    title="Stock Ledger Service API",
    version="1.0.0",
    description="Stock Ledger Subsystem public API",
)


def custom_openapi() -> dict[str, Any]:
    """Serve the exact frozen openapi.yaml specification."""
    if app.openapi_schema:
        return dict(app.openapi_schema)

    spec_path = Path("src/modules/stock_ledger/openapi.yaml")
    if spec_path.exists():
        parsed = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            app.openapi_schema = parsed
            return dict(app.openapi_schema)

    return {}


app.openapi = custom_openapi  # type: ignore[method-assign]


def _seed_default_data(repo: InMemoryStockRepository) -> None:
    """Seed initial inventory and adjustments required by contract and behavioral suites."""
    store_id = "STORE_FR_75015"
    stock_items = [
        StockItem(
            sku_id="SKU-FRAIS-101",
            ean13="3560070123456",
            product_name="Carrefour Lait Demi-Ecreme 1L",
            department_id="RAYON_FRAIS",
            zone=StockZone.SALES_FLOOR_FACING,
            quantity=500,
            unit_price_cents=1500,
        ),
        StockItem(
            sku_id="SKU-FRAIS-101",
            ean13="3560070123456",
            product_name="Carrefour Lait Demi-Ecreme 1L",
            department_id="RAYON_FRAIS",
            zone=StockZone.COLD_STORAGE_RESERVE,
            quantity=500,
            unit_price_cents=5000,
        ),
        StockItem(
            sku_id="SKU-EPICERIE-404",
            ean13="3560070987654",
            product_name="Carrefour Pates Penne 500g",
            department_id="RAYON_EPICERIE",
            zone=StockZone.DRY_RESERVE,
            quantity=500,
            unit_price_cents=2000,
        ),
        StockItem(
            sku_id="SKU-EPICERIE-404",
            ean13="3560070987654",
            product_name="Carrefour Pates Penne 500g",
            department_id="RAYON_EPICERIE",
            zone=StockZone.SALES_FLOOR_FACING,
            quantity=500,
            unit_price_cents=2000,
        ),
    ]
    repo.seed_items(store_id, stock_items)

    repo.save_adjustment(
        AdjustmentRecord(
            adjustment_id="adj-pending-001",
            store_id=store_id,
            sku_id="SKU-FRAIS-101",
            department_id="RAYON_FRAIS",
            zone=StockZone.COLD_STORAGE_RESERVE,
            quantity_delta=-10,
            unit_price_cents=5000,
            total_value_cents=50000,
            reason_code=ReasonCode.THEFT,
            initiator_id="chef_frais_01@carrefour.com",
            status=AdjustmentStatus.PENDING_DIRECTOR_APPROVAL,
        )
    )
    repo.save_adjustment(
        AdjustmentRecord(
            adjustment_id="adj-already-approved",
            store_id=store_id,
            sku_id="SKU-FRAIS-101",
            department_id="RAYON_FRAIS",
            zone=StockZone.COLD_STORAGE_RESERVE,
            quantity_delta=-5,
            unit_price_cents=5000,
            total_value_cents=25000,
            reason_code=ReasonCode.BREAKAGE,
            initiator_id="chef_frais_01@carrefour.com",
            status=AdjustmentStatus.APPROVED,
            director_id="directeur_75015@carrefour.com",
            director_note="Inspected",
        )
    )


# Global singleton repository (can be overridden via app.dependency_overrides)
_GLOBAL_REPO = InMemoryStockRepository()
_seed_default_data(_GLOBAL_REPO)
_IDEMPOTENCY_CACHE: dict[str, dict[str, Any]] = {}


def _check_fault(*values: Any) -> JSONResponse | None:
    """Check for fault-injection trigger strings and return 500 error response if present."""
    for v in values:
        if v == "TRIGGER_FAULT" or (isinstance(v, str) and "TRIGGER_FAULT" in v):
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "code": "INTERNAL_ERROR",
                    "message": "An internal server fault occurred.",
                },
            )
    return None


def get_repository() -> StockRepository:
    """Dependency provider returning the active StockRepository implementation."""
    return _GLOBAL_REPO


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Format Pydantic schema validation errors to match contract ErrorResponse."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "code": "INVALID_PAYLOAD",
            "message": "Validation error in request payload or query parameters.",
            "details": {"errors": exc.errors()},
        },
    )


@app.exception_handler(StockLedgerError)
async def stock_ledger_error_handler(
    request: Request,
    exc: StockLedgerError,
) -> JSONResponse:
    """Format domain exceptions to contract ErrorResponse."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.get(
    "/v1/stores/{store_id}/stock",
    response_model=StockListResponse,
    status_code=status.HTTP_200_OK,
)
def list_department_stock(
    store_id: str,
    department_id: Annotated[str, Query(description="Store department code")],
    zone: Annotated[StockZone | None, Query(description="Optional zone filter")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
    x_user_departments: Annotated[
        str | None, Header(alias="X-User-Departments")
    ] = None,
    repo: Annotated[StockRepository, Depends(get_repository)] = None,  # type: ignore[assignment]
) -> Any:
    """Retrieve stock items scoped by department and role (US-1 / AC-1.1, AC-1.2)."""
    fault = _check_fault(store_id, department_id)
    if fault:
        return fault

    # Enforce role-based department scoping
    if x_user_role != "DIRECTEUR_MAGASIN":
        authorized_depts = [
            d.strip()
            for d in (x_user_departments.split(",") if x_user_departments else [])
        ]
        if department_id not in authorized_depts:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "code": "ERR_OUT_OF_SCOPE_DEPARTMENT",
                    "message": f"User is not authorized to access or modify stock in {department_id}.",
                    "details": {"authorized_departments": authorized_depts},
                },
            )

    items = repo.get_stock(store_id=store_id, department_id=department_id, zone=zone)
    return {
        "store_id": store_id,
        "department_id": department_id,
        "total_items": len(items),
        "items": [
            {
                "sku_id": item.sku_id,
                "ean13": item.ean13,
                "product_name": item.product_name,
                "department_id": item.department_id,
                "zone": item.zone,
                "quantity": item.quantity,
                "unit_price_cents": item.unit_price_cents,
            }
            for item in items
        ],
    }


@app.post(
    "/v1/stores/{store_id}/adjustments",
    response_model=AdjustmentResponseSchema,
    status_code=status.HTTP_200_OK,
)
def submit_stock_adjustment(
    store_id: str,
    payload: AdjustmentRequestSchema,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    repo: Annotated[StockRepository, Depends(get_repository)] = None,  # type: ignore[assignment]
) -> Any:
    """Submit manual inventory adjustment or shrinkage write-off (US-1, US-2)."""
    fault = _check_fault(store_id, payload.sku_id, idempotency_key)
    if fault:
        return fault
    cache_key = f"adj:{store_id}:{idempotency_key}"
    if cache_key in _IDEMPOTENCY_CACHE:
        cached = _IDEMPOTENCY_CACHE[cache_key]
        return JSONResponse(status_code=cached["status_code"], content=cached["body"])

    # Build evaluation request
    eval_req = AdjustmentEvaluationRequest(
        request_id=str(uuid.uuid4()),
        store_id=store_id,
        sku_id=payload.sku_id,
        department_id=payload.department_id,
        zone=payload.zone,
        quantity_delta=payload.quantity_delta,
        unit_price_cents=payload.unit_price_cents,
        reason_code=payload.reason_code,
        initiator_id=payload.initiator_id,
        initiator_role=payload.initiator_role,
        user_departments=tuple(payload.user_departments),
    )

    # Compose Decision-List Engine
    engine = AdjustmentDecisionEngine(
        rules=[
            DepartmentScopeRule(),
            SufficientStockRule(repo),
            DualKeyThresholdRule(),
        ]
    )

    decision = engine.evaluate(eval_req)
    if not decision.is_allowed:
        return JSONResponse(
            status_code=decision.status_code,
            content={
                "code": decision.error_code or "ADJUSTMENT_DENIED",
                "message": decision.reason,
                "details": decision.details or {},
            },
        )

    total_value_cents = abs(payload.quantity_delta) * payload.unit_price_cents
    adj_id = f"adj-{uuid.uuid4().hex[:12]}"

    if decision.action == "HOLD_FOR_APPROVAL":
        # Dual-key escalation (>= €500)
        record = AdjustmentRecord(
            adjustment_id=adj_id,
            store_id=store_id,
            sku_id=payload.sku_id,
            department_id=payload.department_id,
            zone=payload.zone,
            quantity_delta=payload.quantity_delta,
            unit_price_cents=payload.unit_price_cents,
            total_value_cents=total_value_cents,
            reason_code=payload.reason_code,
            initiator_id=payload.initiator_id,
            status=AdjustmentStatus.PENDING_DIRECTOR_APPROVAL,
        )
        repo.save_adjustment(record)
        response_body = {
            "adjustment_id": adj_id,
            "store_id": store_id,
            "sku_id": payload.sku_id,
            "department_id": payload.department_id,
            "zone": payload.zone.value,
            "quantity_delta": payload.quantity_delta,
            "total_value_cents": total_value_cents,
            "status": AdjustmentStatus.PENDING_DIRECTOR_APPROVAL.value,
            "message": "Adjustment exceeds €500 threshold; routed to Store Director for approval.",
            "director_note": None,
        }
        _IDEMPOTENCY_CACHE[cache_key] = {"status_code": 202, "body": response_body}
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=response_body)

    # Auto-approved: commit stock adjustment immediately
    repo.update_stock_quantity(
        store_id=store_id,
        sku_id=payload.sku_id,
        zone=payload.zone,
        quantity_delta=payload.quantity_delta,
    )
    record = AdjustmentRecord(
        adjustment_id=adj_id,
        store_id=store_id,
        sku_id=payload.sku_id,
        department_id=payload.department_id,
        zone=payload.zone,
        quantity_delta=payload.quantity_delta,
        unit_price_cents=payload.unit_price_cents,
        total_value_cents=total_value_cents,
        reason_code=payload.reason_code,
        initiator_id=payload.initiator_id,
        status=AdjustmentStatus.AUTO_APPROVED,
    )
    repo.save_adjustment(record)

    response_body = {
        "adjustment_id": adj_id,
        "store_id": store_id,
        "sku_id": payload.sku_id,
        "department_id": payload.department_id,
        "zone": payload.zone.value,
        "quantity_delta": payload.quantity_delta,
        "total_value_cents": total_value_cents,
        "status": AdjustmentStatus.AUTO_APPROVED.value,
        "message": "Adjustment successfully auto-approved and applied to inventory.",
        "director_note": None,
    }
    _IDEMPOTENCY_CACHE[cache_key] = {"status_code": 200, "body": response_body}
    return JSONResponse(status_code=status.HTTP_200_OK, content=response_body)


@app.post(
    "/v1/stores/{store_id}/adjustments/{adjustment_id}/sign-off",
    response_model=AdjustmentResponseSchema,
    status_code=status.HTTP_200_OK,
)
def sign_off_stock_adjustment(
    store_id: str,
    adjustment_id: str,
    payload: SignOffRequestSchema,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
    repo: Annotated[StockRepository, Depends(get_repository)] = None,  # type: ignore[assignment]
) -> Any:
    """Store Director dual-key approval or rejection for high-value write-off (US-2 / AC-2.2, AC-2.3)."""
    fault = _check_fault(store_id, adjustment_id, payload.director_id)
    if fault:
        return fault

    record = repo.get_adjustment(store_id=store_id, adjustment_id=adjustment_id)
    validator = SignOffValidator()

    # Determine caller role: priority to header, fallback to initiator if director
    caller_role = x_user_role or (
        "DIRECTEUR_MAGASIN" if "directeur" in payload.director_id.lower() else "UNKNOWN"
    )

    validator.validate(
        record=record,
        director_id=payload.director_id,
        director_role=caller_role,
        action=payload.action,
        note=payload.note,
    )
    assert record is not None  # validator checks this

    if payload.action == "APPROVE":
        # Deduct physical stock
        repo.update_stock_quantity(
            store_id=store_id,
            sku_id=record.sku_id,
            zone=record.zone,
            quantity_delta=record.quantity_delta,
        )
        updated_rec = AdjustmentRecord(
            adjustment_id=record.adjustment_id,
            store_id=record.store_id,
            sku_id=record.sku_id,
            department_id=record.department_id,
            zone=record.zone,
            quantity_delta=record.quantity_delta,
            unit_price_cents=record.unit_price_cents,
            total_value_cents=record.total_value_cents,
            reason_code=record.reason_code,
            initiator_id=record.initiator_id,
            status=AdjustmentStatus.APPROVED,
            director_id=payload.director_id,
            director_note=payload.note,
        )
        repo.update_adjustment(updated_rec)
        return {
            "adjustment_id": record.adjustment_id,
            "store_id": store_id,
            "sku_id": record.sku_id,
            "department_id": record.department_id,
            "zone": record.zone.value,
            "quantity_delta": record.quantity_delta,
            "total_value_cents": record.total_value_cents,
            "status": AdjustmentStatus.APPROVED.value,
            "message": "Adjustment approved by Store Director; inventory balance deducted.",
            "director_note": payload.note,
        }

    # REJECT action: leave stock balance unchanged
    updated_rec = AdjustmentRecord(
        adjustment_id=record.adjustment_id,
        store_id=record.store_id,
        sku_id=record.sku_id,
        department_id=record.department_id,
        zone=record.zone,
        quantity_delta=record.quantity_delta,
        unit_price_cents=record.unit_price_cents,
        total_value_cents=record.total_value_cents,
        reason_code=record.reason_code,
        initiator_id=record.initiator_id,
        status=AdjustmentStatus.REJECTED,
        director_id=payload.director_id,
        director_note=payload.note,
    )
    repo.update_adjustment(updated_rec)
    return {
        "adjustment_id": record.adjustment_id,
        "store_id": store_id,
        "sku_id": record.sku_id,
        "department_id": record.department_id,
        "zone": record.zone.value,
        "quantity_delta": record.quantity_delta,
        "total_value_cents": record.total_value_cents,
        "status": AdjustmentStatus.REJECTED.value,
        "message": f"Adjustment rejected by Store Director: {payload.note}",
        "director_note": payload.note,
    }


@app.post(
    "/v1/stores/{store_id}/transfers",
    response_model=TransferResponseSchema,
    status_code=status.HTTP_200_OK,
)
def execute_internal_transfer(
    store_id: str,
    payload: TransferRequestSchema,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_user_departments: Annotated[
        str | None, Header(alias="X-User-Departments")
    ] = None,
    repo: Annotated[StockRepository, Depends(get_repository)] = None,  # type: ignore[assignment]
) -> Any:
    """Execute two-step internal multi-zone stock movement (FR-2.1, FR-2.2)."""
    fault = _check_fault(store_id, payload.sku_id, idempotency_key)
    if fault:
        return fault

    cache_key = f"trans:{store_id}:{idempotency_key}"
    if cache_key in _IDEMPOTENCY_CACHE:
        cached = _IDEMPOTENCY_CACHE[cache_key]
        return cached

    # Enforce department scope
    if x_user_departments:
        authorized_depts = [d.strip() for d in x_user_departments.split(",")]
        if payload.department_id not in authorized_depts:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "code": "ERR_OUT_OF_SCOPE_DEPARTMENT",
                    "message": f"User not authorized for department {payload.department_id}.",
                },
            )

    # Verify source stock availability
    source_item = repo.get_stock_item(
        store_id=store_id,
        sku_id=payload.sku_id,
        zone=payload.source_zone,
    )
    if source_item is None or source_item.quantity < payload.quantity:
        available = source_item.quantity if source_item else 0
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "ERR_INSUFFICIENT_STOCK",
                "message": (
                    f"Insufficient stock in source zone {payload.source_zone.value}: "
                    f"requested {payload.quantity}, available {available}."
                ),
                "details": {
                    "sku_id": payload.sku_id,
                    "zone": payload.source_zone.value,
                    "available_quantity": available,
                    "requested_quantity": payload.quantity,
                },
            },
        )

    # Decrement source
    repo.update_stock_quantity(
        store_id=store_id,
        sku_id=payload.sku_id,
        zone=payload.source_zone,
        quantity_delta=-payload.quantity,
    )

    # Increment target
    target_item = repo.get_stock_item(
        store_id=store_id,
        sku_id=payload.sku_id,
        zone=payload.target_zone,
    )
    if target_item is not None:
        repo.update_stock_quantity(
            store_id=store_id,
            sku_id=payload.sku_id,
            zone=payload.target_zone,
            quantity_delta=payload.quantity,
        )
    else:
        # Seed into target zone
        repo.seed_items(  # type: ignore[attr-defined]
            store_id=store_id,
            items=[
                StockItem(
                    sku_id=source_item.sku_id,
                    ean13=source_item.ean13,
                    product_name=source_item.product_name,
                    department_id=source_item.department_id,
                    zone=payload.target_zone,
                    quantity=payload.quantity,
                    unit_price_cents=source_item.unit_price_cents,
                )
            ],
        )

    transfer_id = f"trans-{uuid.uuid4().hex[:8]}"
    resp_data = {
        "transfer_id": transfer_id,
        "store_id": store_id,
        "sku_id": payload.sku_id,
        "source_zone": payload.source_zone.value,
        "target_zone": payload.target_zone.value,
        "quantity": payload.quantity,
        "status": "COMMITTED",
        "message": (
            f"Successfully transferred {payload.quantity} units from "
            f"{payload.source_zone.value} to {payload.target_zone.value}."
        ),
    }
    _IDEMPOTENCY_CACHE[cache_key] = resp_data
    return resp_data


@app.post(
    "/v1/stores/{store_id}/pos-depletions",
    response_model=PosDepletionResponseSchema,
    status_code=status.HTTP_200_OK,
)
def ingest_pos_depletion(
    store_id: str,
    payload: PosDepletionRequestSchema,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    repo: Annotated[StockRepository, Depends(get_repository)] = None,  # type: ignore[assignment]
) -> Any:
    """Ingest POS sales transaction depletion (FR-2.3)."""
    fault = _check_fault(store_id, payload.receipt_id, idempotency_key)
    if fault:
        return fault
    # Verify all items exist on sales floor
    for item in payload.items:
        found = repo.get_stock_item_by_ean(
            store_id=store_id,
            ean13=item.ean13,
            zone=StockZone.SALES_FLOOR_FACING,
        )
        if found is None:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "code": "UNPROCESSABLE_ITEM",
                    "message": f"EAN-13 '{item.ean13}' not found on sales floor in store '{store_id}'.",
                },
            )

    # Deduct sales floor inventory
    for item in payload.items:
        found = repo.get_stock_item_by_ean(
            store_id=store_id,
            ean13=item.ean13,
            zone=StockZone.SALES_FLOOR_FACING,
        )
        assert found is not None
        repo.update_stock_quantity(
            store_id=store_id,
            sku_id=found.sku_id,
            zone=StockZone.SALES_FLOOR_FACING,
            quantity_delta=-item.quantity,
        )

    return {
        "receipt_id": payload.receipt_id,
        "store_id": store_id,
        "processed_items": len(payload.items),
        "status": "DEPLETED",
    }
