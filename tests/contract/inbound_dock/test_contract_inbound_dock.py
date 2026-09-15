"""Canonical Contract Verification Test Suite for inbound_dock.

Validates that inbound_dock HTTP entrypoints strictly adhere to the frozen
openapi.yaml interface contract, including HTTP status codes, response schemas,
error structures, and header conventions.

This test suite is authored by the Independent Test Architect and executes
orthogonally to developer unit tests. It treats the subsystem as a black box:
it imports ONLY the public entrypoint app, never internal `domain/` or `adapters/` classes.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient

FROZEN_CONTRACT = Path("src/modules/inbound_dock/openapi.yaml")


class TestContractConformance:
    """Black-box contract compliance test suite for inbound_dock subsystem."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Instantiate test client for the inbound_dock public entrypoint."""
        from src.modules.inbound_dock.entrypoints.api import app

        return TestClient(app)

    @pytest.fixture
    def frozen_contract(self) -> Mapping[str, Any]:
        """Load the frozen openapi.yaml the running app must satisfy."""
        return yaml.safe_load(FROZEN_CONTRACT.read_text(encoding="utf-8"))

    def test_live_app_conforms_to_frozen_contract(
        self, client: TestClient, frozen_contract: Mapping[str, Any]
    ) -> None:
        """Verify every path/method/status in the frozen contract is served by the live app."""
        live: Mapping[str, Any] = client.get("/openapi.json").json()
        live_paths: Mapping[str, Any] = live.get("paths", {})

        for path, frozen_ops in frozen_contract.get("paths", {}).items():
            assert path in live_paths, f"Frozen contract path '{path}' is not served by the app."
            for method, frozen_op in frozen_ops.items():
                op = f"{method.upper()} {path}"
                live_op = live_paths[path].get(method)
                assert live_op is not None, f"Frozen operation '{op}' is missing."
                live_codes = {str(c) for c in live_op.get("responses", {})}
                for status_code in frozen_op.get("responses", {}):
                    assert str(status_code) in live_codes, (
                        f"Frozen status '{status_code}' for '{op}' is not served."
                    )

    def test_openapi_spec_route_versioning(self, frozen_contract: Mapping[str, Any]) -> None:
        """Verify that all exposed paths are versioned with /v<N>/ prefix."""
        for path in frozen_contract.get("paths", {}):
            assert path.startswith("/v"), f"Path '{path}' violates /v<N>/ versioning contract."

    # --- POST /v1/inbound-shipments ---

    def test_post_inbound_shipment_201_created(self, client: TestClient) -> None:
        """Verify 201 Created response and AsnResponse schema for valid ASN ingestion."""
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        payload = {
            "asn_id": "ASN-2026-0915-001",
            "store_id": "STORE_FR_75015",
            "supplier_id": "SUPPLIER_CENTRAL_DC_LILLE",
            "expected_delivery": "2026-09-15T08:00:00Z",
            "pallets": [
                {
                    "sscc": "037000123456789012",
                    "temperature_regime": "CHILLED",
                    "lines": [
                        {
                            "sku": "SKU-YOGURT-001",
                            "ean13": "3560070123456",
                            "expected_quantity": 48,
                            "lot_number": "LOT-202609-01",
                            "bbd": "2026-09-25",
                        }
                    ],
                }
            ],
        }
        response = client.post("/v1/inbound-shipments", headers=headers, json=payload)
        assert response.status_code == 201
        assert response.headers["content-type"].startswith("application/json")
        data: Mapping[str, Any] = response.json()
        assert data["asn_id"] == "ASN-2026-0915-001"
        assert data["store_id"] == "STORE_FR_75015"
        assert data["status"] in ["EXPECTED", "IN_RECEIVING", "COMPLETED", "DISCREPANCY_FLAGGED"]
        assert "total_pallets" in data
        assert "received_pallets" in data
        assert isinstance(data["pallets"], list)

    def test_post_inbound_shipment_400_bad_request(self, client: TestClient) -> None:
        """Verify 400 Bad Request when mandatory fields or headers are missing/malformed."""
        # Missing Idempotency-Key header and required fields
        response = client.post("/v1/inbound-shipments", json={"invalid_field": "data"})
        assert response.status_code == 400
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_inbound_shipment_409_conflict(self, client: TestClient) -> None:
        """Verify 409 Conflict when duplicate ASN ID or conflicting status is ingested."""
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        payload = {
            "asn_id": "ASN-EXISTING-DUPLICATE",
            "store_id": "STORE_FR_75015",
            "supplier_id": "SUPPLIER_CENTRAL_DC_LILLE",
            "expected_delivery": "2026-09-15T08:00:00Z",
            "pallets": [
                {
                    "sscc": "037000123456789012",
                    "temperature_regime": "AMBIENT",
                    "lines": [
                        {
                            "sku": "SKU-PASTA-001",
                            "ean13": "3560070987654",
                            "expected_quantity": 100,
                            "lot_number": "LOT-PASTA-99",
                            "bbd": "2027-12-31",
                        }
                    ],
                }
            ],
        }
        # First creation
        client.post("/v1/inbound-shipments", headers=headers, json=payload)
        # Duplicate creation with different idempotency key
        conflict_headers = {"Idempotency-Key": str(uuid.uuid4())}
        response = client.post(
            "/v1/inbound-shipments", headers=conflict_headers, json=payload
        )
        assert response.status_code == 409
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_inbound_shipment_422_unprocessable_entity(self, client: TestClient) -> None:
        """Verify 422 Unprocessable Entity on business rule violation in shipment details."""
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        invalid_business_payload = {
            "asn_id": "ASN-INVALID-BIZ",
            "store_id": "STORE_FR_75015",
            "supplier_id": "SUPPLIER_001",
            "expected_delivery": "2026-09-15T08:00:00Z",
            "pallets": [
                {
                    "sscc": "037000123456789012",
                    "temperature_regime": "INVALID_REGIME",
                    "lines": [],
                }
            ],
        }
        response = client.post(
            "/v1/inbound-shipments", headers=headers, json=invalid_business_payload
        )
        assert response.status_code == 422
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_inbound_shipment_500_internal_server_error(self, client: TestClient) -> None:
        """Verify 500 Internal Server Error returns structured error without stack traces."""
        headers = {
            "Idempotency-Key": str(uuid.uuid4()),
            "X-Simulate-Fault": "INTERNAL_DATASTORE_FAULT",
        }
        payload = {
            "asn_id": "ASN-TRIGGER-FAULT-500",
            "store_id": "STORE_FR_75015",
            "supplier_id": "SUPPLIER_001",
            "expected_delivery": "2026-09-15T08:00:00Z",
            "pallets": [],
        }
        response = client.post("/v1/inbound-shipments", headers=headers, json=payload)
        assert response.status_code == 500
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body
        assert "Traceback" not in response.text

    # --- GET /v1/stores/{storeId}/inbound-shipments/{asnId} ---

    def test_get_asn_shipment_200_ok(self, client: TestClient) -> None:
        """Verify 200 OK returns expected AsnResponse schema."""
        response = client.get("/v1/stores/STORE_FR_75015/inbound-shipments/ASN-2026-0915-001")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        data: Mapping[str, Any] = response.json()
        assert data["asn_id"] == "ASN-2026-0915-001"
        assert data["store_id"] == "STORE_FR_75015"
        assert "status" in data
        assert "total_pallets" in data
        assert "received_pallets" in data
        assert "pallets" in data

    def test_get_asn_shipment_400_bad_request(self, client: TestClient) -> None:
        """Verify 400 Bad Request for malformed store or ASN identifiers."""
        response = client.get("/v1/stores/!INVALID_STORE!/inbound-shipments/ASN-001")
        assert response.status_code == 400
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_get_asn_shipment_404_not_found(self, client: TestClient) -> None:
        """Verify 404 Not Found when shipment does not exist."""
        response = client.get(
            "/v1/stores/STORE_FR_75015/inbound-shipments/ASN-NONEXISTENT-999"
        )
        assert response.status_code == 404
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_get_asn_shipment_500_internal_server_error(self, client: TestClient) -> None:
        """Verify 500 Internal Server Error when querying shipment details under fault."""
        headers = {"X-Simulate-Fault": "STORAGE_UNAVAILABLE"}
        response = client.get(
            "/v1/stores/STORE_FR_75015/inbound-shipments/ASN-FAULT-500", headers=headers
        )
        assert response.status_code == 500
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body
        assert "Traceback" not in response.text

    # --- POST /v1/inbound-shipments/{asnId}/receive-pallet ---

    def test_post_receive_pallet_200_ok(self, client: TestClient) -> None:
        """Verify 200 OK returns ReceivePalletResponse on successful pallet scan and evaluation."""
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        payload = {
            "sscc": "037000123456789012",
            "store_id": "STORE_FR_75015",
            "operator_id": "OP_DOCK_42",
            "probed_temperature": 2.5,
            "damage_observed": False,
            "notes": "Compliant temperature and intact packaging",
        }
        response = client.post(
            "/v1/inbound-shipments/ASN-2026-0915-001/receive-pallet",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 200
        data: Mapping[str, Any] = response.json()
        assert data["asn_id"] == "ASN-2026-0915-001"
        assert data["sscc"] == "037000123456789012"
        assert data["status"] in ["BACKROOM_STAGING", "STATUS_QUARANTINE", "REJECTED_RTV"]
        assert data["target_location"] in [
            "BACKROOM_STAGING",
            "QUARANTINE_DAMAGED",
            "COLD_STORAGE_RESERVE",
        ]
        assert isinstance(data["is_compliant"], bool)
        assert "message" in data

    def test_post_receive_pallet_400_bad_request(self, client: TestClient) -> None:
        """Verify 400 Bad Request when SSCC barcode is malformed or required field missing."""
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        payload = {
            "sscc": "SHORT-BARCODE",  # Invalid SSCC-18
            "store_id": "STORE_FR_75015",
            "operator_id": "OP_DOCK_42",
        }
        response = client.post(
            "/v1/inbound-shipments/ASN-2026-0915-001/receive-pallet",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 400
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_receive_pallet_404_not_found(self, client: TestClient) -> None:
        """Verify 404 Not Found when ASN or SSCC does not exist."""
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        payload = {
            "sscc": "037000999999999999",
            "store_id": "STORE_FR_75015",
            "operator_id": "OP_DOCK_42",
            "probed_temperature": 3.0,
        }
        response = client.post(
            "/v1/inbound-shipments/ASN-NONEXISTENT/receive-pallet",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 404
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_receive_pallet_409_conflict(self, client: TestClient) -> None:
        """Verify 409 Conflict when pallet has already been received."""
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        payload = {
            "sscc": "037000123456789012",
            "store_id": "STORE_FR_75015",
            "operator_id": "OP_DOCK_42",
            "probed_temperature": 2.5,
        }
        # First receive
        client.post(
            "/v1/inbound-shipments/ASN-2026-0915-001/receive-pallet",
            headers=headers,
            json=payload,
        )
        # Attempt second receive
        second_headers = {"Idempotency-Key": str(uuid.uuid4())}
        response = client.post(
            "/v1/inbound-shipments/ASN-2026-0915-001/receive-pallet",
            headers=second_headers,
            json=payload,
        )
        assert response.status_code == 409
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_receive_pallet_422_unprocessable_entity(self, client: TestClient) -> None:
        """Verify 422 Unprocessable Entity when business rules are violated."""
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        payload = {
            "sscc": "037000123456789012",
            "store_id": "STORE_FR_75015",
            "operator_id": "OP_DOCK_42",
            "probed_temperature": None,  # Mandatory for chilled/frozen
        }
        response = client.post(
            "/v1/inbound-shipments/ASN-2026-0915-001/receive-pallet",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 422
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_receive_pallet_500_internal_server_error(self, client: TestClient) -> None:
        """Verify 500 Internal Server Error when adapter failure occurs during pallet receive."""
        headers = {
            "Idempotency-Key": str(uuid.uuid4()),
            "X-Simulate-Fault": "DATABASE_DEADLOCK",
        }
        payload = {
            "sscc": "037000123456789012",
            "store_id": "STORE_FR_75015",
            "operator_id": "OP_DOCK_42",
            "probed_temperature": 3.0,
        }
        response = client.post(
            "/v1/inbound-shipments/ASN-FAULT-500/receive-pallet",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 500
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body
        assert "Traceback" not in response.text

    # --- POST /v1/inbound-shipments/{asnId}/discrepancies ---

    def test_post_discrepancy_201_created(self, client: TestClient) -> None:
        """Verify 201 Created and DiscrepancyResponse schema on recording discrepancy claim."""
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        payload = {
            "store_id": "STORE_FR_75015",
            "sscc": "037000123456789012",
            "sku": "SKU-YOGURT-001",
            "discrepancy_type": "COLD_CHAIN_BREACH",
            "reason_code": "TEMP_ABOVE_4C",
            "affected_quantity": 48,
            "photo_evidence_url": "gs://carrefour-inbound-evidence/claims/claim_001.jpg",
            "reported_by": "OP_DOCK_42",
            "notes": "Probed temperature reached 7.5°C",
        }
        response = client.post(
            "/v1/inbound-shipments/ASN-2026-0915-001/discrepancies",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 201
        data: Mapping[str, Any] = response.json()
        assert "discrepancy_id" in data
        assert data["asn_id"] == "ASN-2026-0915-001"
        assert data["status"] in ["LOGGED", "CLAIM_DISPATCHED", "UNDER_REVIEW"]
        assert "created_at" in data

    def test_post_discrepancy_400_bad_request(self, client: TestClient) -> None:
        """Verify 400 Bad Request when discrepancy payload has invalid enum values."""
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        payload = {
            "store_id": "STORE_FR_75015",
            "discrepancy_type": "UNKNOWN_DISCREPANCY_TYPE",
            "reason_code": "INVALID_CODE",
            "reported_by": "OP_DOCK_42",
        }
        response = client.post(
            "/v1/inbound-shipments/ASN-2026-0915-001/discrepancies",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 400
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_discrepancy_404_not_found(self, client: TestClient) -> None:
        """Verify 404 Not Found when ASN does not exist for discrepancy claim."""
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        payload = {
            "store_id": "STORE_FR_75015",
            "discrepancy_type": "SHORTAGE",
            "reason_code": "MISSING_PALLET",
            "reported_by": "OP_DOCK_42",
        }
        response = client.post(
            "/v1/inbound-shipments/ASN-NONEXISTENT/discrepancies",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 404
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_discrepancy_422_unprocessable_entity(self, client: TestClient) -> None:
        """Verify 422 Unprocessable Entity when discrepancy claim violates business logic."""
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        payload = {
            "store_id": "STORE_FR_75015",
            "discrepancy_type": "DAMAGE",
            "reason_code": "DAMAGED_CRUSHED",
            "affected_quantity": 0,  # minimum is 1
            "reported_by": "OP_DOCK_42",
        }
        response = client.post(
            "/v1/inbound-shipments/ASN-2026-0915-001/discrepancies",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 422
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_discrepancy_500_internal_server_error(self, client: TestClient) -> None:
        """Verify 500 Internal Server Error when logging discrepancy encounters internal fault."""
        headers = {
            "Idempotency-Key": str(uuid.uuid4()),
            "X-Simulate-Fault": "GCS_UNREACHABLE",
        }
        payload = {
            "store_id": "STORE_FR_75015",
            "discrepancy_type": "DAMAGE",
            "reason_code": "DAMAGED_CRUSHED",
            "reported_by": "OP_DOCK_42",
        }
        response = client.post(
            "/v1/inbound-shipments/ASN-FAULT-500/discrepancies",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 500
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body
        assert "Traceback" not in response.text
