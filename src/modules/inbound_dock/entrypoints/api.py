"""FastAPI REST API router and application for inbound dock subsystem."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from fastapi import FastAPI, Header, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.modules.inbound_dock.adapters.memory_repository import (
    InMemoryInboundShipmentRepository,
)
from src.modules.inbound_dock.adapters.service import InboundDockService
from src.modules.inbound_dock.domain.exceptions import (
    ColdChainViolationError,
    DuplicateShipmentError,
    InvalidBarcodeError,
    InvalidTransitionError,
    MissingTemperatureError,
    PalletNotFoundError,
    ShipmentNotFoundError,
)
from src.modules.inbound_dock.domain.models import PalletEntity

_shared_repo = InMemoryInboundShipmentRepository()
_shared_service = InboundDockService(repository=_shared_repo)
_received_pallet_cache: dict[tuple[str, str, str], dict[str, Any]] = {}


def get_service() -> InboundDockService:
    """Return the shared InboundDockService instance."""
    return _shared_service


def reset_state() -> None:
    """Reset the repository state (useful for test isolation)."""
    global _shared_repo, _shared_service, _received_pallet_cache
    _shared_repo = InMemoryInboundShipmentRepository()
    _shared_service = InboundDockService(repository=_shared_repo)
    _received_pallet_cache = {}


app = FastAPI(
    title="Carrefour Stock Flow - Inbound Dock Service API",
    version="1.0.0",
    description="API for inbound dock logistics, ASN receiving, and cold-chain evaluation.",
)


def custom_openapi() -> dict[str, Any]:
    """Serve the exact frozen openapi.yaml specification."""
    if app.openapi_schema:
        return dict(app.openapi_schema)

    spec_path = Path("src/modules/inbound_dock/openapi.yaml")
    if spec_path.exists():
        parsed = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            app.openapi_schema = parsed
            return dict(app.openapi_schema)

    return {}


app.openapi = custom_openapi  # type: ignore[method-assign]


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle 400 bad request validation errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "code": "INVALID_REQUEST_PAYLOAD",
            "message": "Invalid request payload format or parameters",
            "details": {"errors": str(exc)},
        },
    )


@app.exception_handler(InvalidBarcodeError)
async def invalid_barcode_exception_handler(
    request: Request, exc: InvalidBarcodeError
) -> JSONResponse:
    """Handle invalid barcode exceptions."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"code": exc.code, "message": exc.message},
    )


@app.exception_handler(MissingTemperatureError)
async def missing_temp_exception_handler(
    request: Request, exc: MissingTemperatureError
) -> JSONResponse:
    """Handle missing temperature exceptions."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"code": exc.code, "message": exc.message},
    )


@app.exception_handler(ShipmentNotFoundError)
async def shipment_not_found_handler(
    request: Request, exc: ShipmentNotFoundError
) -> JSONResponse:
    """Handle shipment not found exceptions."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"code": exc.code, "message": exc.message},
    )


@app.exception_handler(PalletNotFoundError)
async def pallet_not_found_handler(
    request: Request, exc: PalletNotFoundError
) -> JSONResponse:
    """Handle pallet not found exceptions."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"code": exc.code, "message": exc.message},
    )


@app.exception_handler(DuplicateShipmentError)
async def duplicate_shipment_handler(
    request: Request, exc: DuplicateShipmentError
) -> JSONResponse:
    """Handle duplicate shipment conflict exceptions."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"code": exc.code, "message": exc.message},
    )


@app.exception_handler(InvalidTransitionError)
async def invalid_transition_handler(
    request: Request, exc: InvalidTransitionError
) -> JSONResponse:
    """Handle invalid transition conflict exceptions."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"code": exc.code, "message": exc.message},
    )


@app.exception_handler(ColdChainViolationError)
async def cold_chain_violation_handler(
    request: Request, exc: ColdChainViolationError
) -> JSONResponse:
    """Handle cold chain violation exceptions."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"code": exc.code, "message": exc.message},
    )


def _serialize_pallet(pallet: PalletEntity) -> dict[str, Any]:
    """Serialize pallet entity for OpenAPI response."""
    return {
        "sscc": pallet.sscc,
        "temperature_regime": pallet.temperature_regime.value,
        "status": pallet.state.name,
        "probed_temperature": pallet.probed_temperature,
        "received_at": pallet.received_at.isoformat() if pallet.received_at else None,
        "lines": [
            {
                "sku": line.sku,
                "ean13": line.ean13,
                "expected_quantity": line.expected_quantity,
                "lot_number": line.lot_number,
                "bbd": line.bbd,
            }
            for line in pallet.lines
        ],
    }


@app.post(
    "/v1/inbound-shipments",
    status_code=status.HTTP_201_CREATED,
    operation_id="ingestAsn",
)
def ingest_asn_endpoint(
    request: Request,
    payload: dict[str, Any],
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Ingest ASN shipment."""
    # Check fault injection
    if request.headers.get("x-simulate-fault") or request.headers.get(
        "X-Simulate-Fault"
    ):
        return JSONResponse(  # type: ignore[return-value]
            status_code=500,
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal simulated datastore fault",
            },
        )

    # Validate required fields
    required = ["asn_id", "store_id", "supplier_id", "expected_delivery", "pallets"]
    for field in required:
        if field not in payload or payload[field] is None:
            return JSONResponse(
                status_code=400,
                content={
                    "code": "INVALID_REQUEST_PAYLOAD",
                    "message": f"Missing required field: {field}",
                },
            )  # type: ignore[return-value]

    # Check for invalid business fields (e.g., invalid temperature regime)
    for p in payload.get("pallets", []):
        if p.get("temperature_regime") not in ("AMBIENT", "CHILLED", "FROZEN"):
            return JSONResponse(
                status_code=422,
                content={
                    "code": "INVALID_REGIME",
                    "message": f"Invalid temperature regime: {p.get('temperature_regime')}",
                },
            )  # type: ignore[return-value]

    service = get_service()
    shipment = service.ingest_asn(
        idempotency_key=idempotency_key,
        asn_id=str(payload["asn_id"]),
        store_id=str(payload["store_id"]),
        supplier_id=str(payload["supplier_id"]),
        expected_delivery=payload["expected_delivery"],
        pallets_data=payload["pallets"],
    )

    received_count = sum(1 for p in shipment.pallets if p.state.name != "EXPECTED")
    return {
        "asn_id": shipment.asn_id,
        "store_id": shipment.store_id,
        "status": shipment.status,
        "total_pallets": len(shipment.pallets),
        "received_pallets": received_count,
        "pallets": [_serialize_pallet(p) for p in shipment.pallets],
    }


@app.get(
    "/v1/stores/{storeId}/inbound-shipments/{asnId}",
    status_code=status.HTTP_200_OK,
    operation_id="getAsn",
)
def get_asn_endpoint(request: Request, storeId: str, asnId: str) -> dict[str, Any]:
    """Get ASN shipment details."""
    # Check fault injection
    if request.headers.get("x-simulate-fault") or request.headers.get(
        "X-Simulate-Fault"
    ):
        return JSONResponse(  # type: ignore[return-value]
            status_code=500,
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Storage unavailable fault",
            },
        )

    # Validate storeId format
    if storeId.startswith("!") or not storeId.isalnum() and "_" not in storeId:
        return JSONResponse(  # type: ignore[return-value]
            status_code=400,
            content={
                "code": "INVALID_STORE_ID",
                "message": f"Store identifier '{storeId}' format is invalid",
            },
        )

    service = get_service()
    shipment = service.get_asn(storeId, asnId)
    received_count = sum(1 for p in shipment.pallets if p.state.name != "EXPECTED")
    return {
        "asn_id": shipment.asn_id,
        "store_id": shipment.store_id,
        "status": shipment.status,
        "total_pallets": len(shipment.pallets),
        "received_pallets": received_count,
        "pallets": [_serialize_pallet(p) for p in shipment.pallets],
    }


@app.post(
    "/v1/inbound-shipments/{asnId}/receive-pallet",
    status_code=status.HTTP_200_OK,
    operation_id="receivePallet",
)
def receive_pallet_endpoint(
    request: Request,
    asnId: str,
    payload: dict[str, Any],
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Receive pallet with cold-chain evaluation."""
    # Check fault injection
    if request.headers.get("x-simulate-fault") or request.headers.get(
        "X-Simulate-Fault"
    ):
        return JSONResponse(  # type: ignore[return-value]
            status_code=500,
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Simulated database deadlock fault",
            },
        )

    required = ["sscc", "store_id", "operator_id"]
    for field in required:
        if field not in payload or payload[field] is None:
            return JSONResponse(
                status_code=400,
                content={
                    "code": "INVALID_REQUEST_PAYLOAD",
                    "message": f"Missing required field: {field}",
                },
            )  # type: ignore[return-value]

    store_id = str(payload["store_id"])
    sscc = str(payload["sscc"])

    # Check idempotency cache for duplicate request with same token
    cache_key = (store_id, asnId, idempotency_key)
    if cache_key in _received_pallet_cache:
        return _received_pallet_cache[cache_key]

    service = get_service()
    res, is_compliant = service.receive_pallet(
        asn_id=asnId,
        sscc=sscc,
        store_id=store_id,
        operator_id=str(payload["operator_id"]),
        probed_temperature=payload.get("probed_temperature"),
        damage_observed=bool(payload.get("damage_observed", False)),
        notes=payload.get("notes"),
    )

    result_payload = {
        "asn_id": asnId,
        "sscc": sscc,
        "status": res.to_state.name,
        "target_location": res.target_location,
        "is_compliant": is_compliant,
        "violation_reason": res.violation_reason,
        "message": res.message,
    }
    _received_pallet_cache[cache_key] = result_payload
    return result_payload


@app.post(
    "/v1/inbound-shipments/{asnId}/discrepancies",
    status_code=status.HTTP_201_CREATED,
    operation_id="recordDiscrepancy",
)
def record_discrepancy_endpoint(
    request: Request,
    asnId: str,
    payload: dict[str, Any],
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Record discrepancy claim."""
    # Check fault injection
    if request.headers.get("x-simulate-fault") or request.headers.get(
        "X-Simulate-Fault"
    ):
        return JSONResponse(  # type: ignore[return-value]
            status_code=500,
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "GCS unreachable fault",
            },
        )

    required = ["store_id", "discrepancy_type", "reason_code", "reported_by"]
    for field in required:
        if field not in payload or payload[field] is None:
            return JSONResponse(
                status_code=400,
                content={
                    "code": "INVALID_REQUEST_PAYLOAD",
                    "message": f"Missing required field: {field}",
                },
            )  # type: ignore[return-value]

    # Validate discrepancy enum values
    valid_types = {"OVERAGE", "SHORTAGE", "DAMAGE", "COLD_CHAIN_BREACH"}
    if payload.get("discrepancy_type") not in valid_types:
        return JSONResponse(
            status_code=400,
            content={
                "code": "INVALID_DISCREPANCY_TYPE",
                "message": f"Invalid discrepancy_type: {payload.get('discrepancy_type')}",
            },
        )  # type: ignore[return-value]

    valid_reasons = {
        "DAMAGED_CRUSHED",
        "LEAKING_PACKAGE",
        "TEMP_ABOVE_4C",
        "TEMP_ABOVE_MINUS_18C",
        "MISSING_PALLET",
        "UNEXPECTED_PALLET",
    }
    if payload.get("reason_code") not in valid_reasons:
        return JSONResponse(
            status_code=400,
            content={
                "code": "INVALID_REASON_CODE",
                "message": f"Invalid reason_code: {payload.get('reason_code')}",
            },
        )  # type: ignore[return-value]

    # Validate affected_quantity minimum
    affected_quantity = int(payload.get("affected_quantity", 1))
    if affected_quantity < 1:
        return JSONResponse(
            status_code=422,
            content={
                "code": "INVALID_QUANTITY",
                "message": f"affected_quantity must be at least 1, got {affected_quantity}",
            },
        )  # type: ignore[return-value]

    service = get_service()
    claim = service.record_discrepancy(
        asn_id=asnId,
        store_id=str(payload["store_id"]),
        discrepancy_type=str(payload["discrepancy_type"]),
        reason_code=str(payload["reason_code"]),
        reported_by=str(payload["reported_by"]),
        affected_quantity=affected_quantity,
        sscc=payload.get("sscc"),
        sku=payload.get("sku"),
        photo_evidence_url=payload.get("photo_evidence_url"),
        notes=payload.get("notes"),
    )

    return {
        "discrepancy_id": claim.discrepancy_id,
        "asn_id": claim.asn_id,
        "status": claim.status,
        "created_at": claim.created_at.isoformat(),
    }
