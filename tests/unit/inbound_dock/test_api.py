"""Unit tests for FastAPI REST API endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.modules.inbound_dock.entrypoints.api import app, reset_state


@pytest.fixture(autouse=True)
def clean_state() -> None:
    """Reset repository and service state before each test."""
    reset_state()


def test_api_validation_error_and_helpers() -> None:
    """Test custom openapi, validation error handler, and edge cases."""
    client = TestClient(app)

    # Test reset_state
    reset_state()

    # Test invalid json payload schema causing RequestValidationError (e.g., missing header)
    resp = client.post("/v1/inbound-shipments", json="not a dict")
    assert resp.status_code == 400

    # Test missing mandatory field in ingest
    resp = client.post(
        "/v1/inbound-shipments",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"asn_id": "ASN-1"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST_PAYLOAD"

    # Test missing mandatory field in receive-pallet
    resp = client.post(
        "/v1/inbound-shipments/ASN-1/receive-pallet",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"store_id": "STORE_1"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST_PAYLOAD"

    # Test missing mandatory field in discrepancy
    resp = client.post(
        "/v1/inbound-shipments/ASN-1/discrepancies",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"store_id": "STORE_1"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST_PAYLOAD"

    # Test invalid reason_code in discrepancy
    resp = client.post(
        "/v1/inbound-shipments/ASN-1/discrepancies",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "store_id": "STORE_1",
            "discrepancy_type": "DAMAGE",
            "reason_code": "INVALID_REASON",
            "reported_by": "OP_1",
            "affected_quantity": 1,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REASON_CODE"

    # Test custom_openapi when spec_path does not exist and when cached
    app.openapi_schema = None
    with patch.object(Path, "exists", return_value=False):
        schema = app.openapi()
        assert schema == {}
    app.openapi_schema = {"cached": True}
    assert app.openapi() == {"cached": True}
    app.openapi_schema = None


def test_api_service_coverage() -> None:
    """Test service and cold chain evaluator edge cases."""
    from src.modules.inbound_dock.adapters.memory_repository import (
        InMemoryInboundShipmentRepository,
    )
    from src.modules.inbound_dock.adapters.service import InboundDockService
    from src.modules.inbound_dock.domain.cold_chain_evaluator import ColdChainEvaluator
    from src.modules.inbound_dock.domain.exceptions import PalletNotFoundError

    repo = InMemoryInboundShipmentRepository()
    service = InboundDockService(repository=repo)

    # Ingest a shipment with pallet
    service.ingest_asn(
        idempotency_key=str(uuid.uuid4()),
        asn_id="ASN-1",
        store_id="STORE_1",
        supplier_id="SUP-1",
        expected_delivery=datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc),
        pallets_data=[
            {
                "sscc": "037000123456789012",
                "temperature_regime": "AMBIENT",
                "lines": [],
            }
        ],
    )

    # receive_pallet with pallet not in shipment
    with pytest.raises(PalletNotFoundError):
        service.receive_pallet(
            asn_id="ASN-1",
            sscc="037000999999999999",
            store_id="STORE_1",
            operator_id="OP_1",
        )

    # ColdChainEvaluator unknown regime test
    evaluator = ColdChainEvaluator()
    # pass invalid regime cast to TemperatureRegime
    is_compliant, reason = evaluator.evaluate("UNKNOWN", 10.0)  # type: ignore[arg-type]
    assert is_compliant is False
    assert reason == "UNKNOWN_REGIME"


def test_domain_repository_abstract_methods() -> None:
    """Test InboundShipmentRepository base class raises NotImplementedError."""
    from src.modules.inbound_dock.domain.repository import InboundShipmentRepository

    class DummyRepo(InboundShipmentRepository):
        def save_shipment(self, shipment: Any) -> None:
            super().save_shipment(shipment)  # type: ignore[safe-super]

        def get_shipment(self, store_id: str, asn_id: str) -> Any:
            return super().get_shipment(store_id, asn_id)  # type: ignore[safe-super]

        def update_pallet(self, store_id: str, asn_id: str, pallet: Any) -> None:
            super().update_pallet(store_id, asn_id, pallet)  # type: ignore[safe-super]

        def save_discrepancy(self, claim: Any) -> None:
            super().save_discrepancy(claim)  # type: ignore[safe-super]

        def check_idempotency(self, key: str) -> bool:
            return super().check_idempotency(key)  # type: ignore[safe-super]

        def record_idempotency(self, key: str, payload_summary: str) -> None:
            super().record_idempotency(key, payload_summary)  # type: ignore[safe-super]

    dummy = DummyRepo()
    with pytest.raises(NotImplementedError):
        dummy.save_shipment(None)
    with pytest.raises(NotImplementedError):
        dummy.get_shipment("S", "A")
    with pytest.raises(NotImplementedError):
        dummy.update_pallet("S", "A", None)
    with pytest.raises(NotImplementedError):
        dummy.save_discrepancy(None)
    with pytest.raises(NotImplementedError):
        dummy.check_idempotency("key")
    with pytest.raises(NotImplementedError):
        dummy.record_idempotency("key", "val")


@pytest.mark.anyio
async def test_exception_handlers_direct() -> None:
    """Directly call exception handlers to verify status and body."""
    from starlette.requests import Request

    from src.modules.inbound_dock.domain.exceptions import (
        ColdChainViolationError,
        PalletNotFoundError,
    )
    from src.modules.inbound_dock.entrypoints.api import (
        cold_chain_violation_handler,
        pallet_not_found_handler,
    )

    scope = {"type": "http", "method": "GET", "path": "/"}
    req = Request(scope)

    resp1 = await pallet_not_found_handler(req, PalletNotFoundError("missing"))
    assert resp1.status_code == 404

    resp2 = await cold_chain_violation_handler(req, ColdChainViolationError("breach"))
    assert resp2.status_code == 422
