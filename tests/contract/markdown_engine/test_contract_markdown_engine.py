"""Orthogonal Contract Verification Test Suite for markdown_engine Subsystem.

Validates that markdown_engine HTTP entrypoints strictly adhere to the frozen
src/modules/markdown_engine/openapi.yaml contract, including HTTP status codes,
response schemas, error structures, and header conventions.

This test suite is authored by the Independent Test Architect and executes
orthogonally to developer unit tests. It treats the subsystem as a black box:
it imports ONLY the public entrypoint app, never internal `domain/` or `adapters/` classes.
"""

from collections.abc import Mapping
from pathlib import Path
import sys
from typing import Any
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FROZEN_CONTRACT = Path("src/modules/markdown_engine/openapi.yaml")


class TestMarkdownEngineContractConformance:
    """Black-box OpenAPI contract compliance test suite for markdown_engine."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Instantiate test client for the markdown_engine public entrypoint."""
        from src.modules.markdown_engine.entrypoints.api import app

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
        """Verify that all exposed paths start with /v<N>/ version prefix."""
        for path in frozen_contract.get("paths", {}):
            assert path.startswith("/v"), f"Path '{path}' violates /v<N>/ versioning contract."

    # =========================================================================
    # POST /v1/markdown/evaluate
    # Documented status codes: 200, 400, 422, 500
    # =========================================================================

    def test_post_evaluate_returns_200_and_valid_schema(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/evaluate returns status_code 200 and MarkdownEvaluationResponse schema."""
        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "sku_id": "SKU-YOGURT-BIO-01",
            "ean_barcode": "3560070123456",
            "lot_number": "LOT-2026-09-A",
            "expiry_date": "2026-09-16",
            "original_price_cents": 350,
            "quantity": 12,
        }
        response = client.post("/v1/markdown/evaluate", json=payload)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        data: Mapping[str, Any] = response.json()
        assert "evaluation_id" in data
        assert isinstance(data["eligible"], bool)
        assert isinstance(data["discount_percentage"], int)
        assert isinstance(data["discounted_price_cents"], int)
        assert data["status"] in [
            "DISCOUNT_30",
            "DISCOUNT_50",
            "STANDARD_PRICE",
            "DONATION_CANDIDATE",
            "SPOILAGE_CANDIDATE",
        ]
        assert "rule_applied" in data

    def test_post_evaluate_missing_required_fields_returns_400(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/evaluate returns status_code 400 when required fields are missing."""
        invalid_payload = {
            "request_id": str(uuid.uuid4()),
            # missing store_id, sku_id, ean_barcode, etc.
            "quantity": 5,
        }
        response = client.post("/v1/markdown/evaluate", json=invalid_payload)
        assert response.status_code == 400
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_evaluate_business_rule_violation_returns_422(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/evaluate returns status_code 422 on domain rule violation."""
        violating_payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "sku_id": "SKU-EXPIRED-LOCKED",
            "ean_barcode": "3560070123456",
            "lot_number": "LOT-EXPIRED-99",
            "expiry_date": "2020-01-01",  # Past expiry threshold not eligible for dynamic markdown
            "original_price_cents": 350,
            "quantity": 10,
        }
        response = client.post("/v1/markdown/evaluate", json=violating_payload)
        assert response.status_code == 422
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_evaluate_adapter_failure_returns_500(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/evaluate returns status_code 500 on internal fault without leaking trace."""
        headers = {"X-Simulate-Fault": "DATASTORE_DISCONNECTED"}
        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "sku_id": "SKU-FAULT-SIM",
            "ean_barcode": "3560070123456",
            "lot_number": "LOT-FAULT",
            "expiry_date": "2026-09-16",
            "original_price_cents": 350,
            "quantity": 1,
        }
        response = client.post("/v1/markdown/evaluate", headers=headers, json=payload)
        assert response.status_code == 500
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body
        assert "Traceback" not in response.text

    # =========================================================================
    # POST /v1/markdown/print-label
    # Documented status codes: 200, 400, 422, 500
    # =========================================================================

    def test_post_print_label_returns_200_and_valid_schema(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/print-label returns status_code 200 and PrintLabelResponse schema."""
        payload = {
            "request_id": str(uuid.uuid4()),
            "evaluation_id": "EVAL-20260915-001",
            "ean_barcode": "3560070123456",
            "discounted_price_cents": 245,
            "quantity": 12,
            "printer_id": "PRINTER_ZEBRA_BT_01",
        }
        response = client.post("/v1/markdown/print-label", json=payload)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        data: Mapping[str, Any] = response.json()
        assert "job_id" in data
        assert "promotional_barcode" in data
        assert "escpos_payload_base64" in data
        assert isinstance(data["labels_printed"], int)
        assert data["labels_printed"] == 12

    def test_post_print_label_missing_required_fields_returns_400(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/print-label returns status_code 400 when required fields are missing."""
        invalid_payload = {
            "request_id": str(uuid.uuid4()),
            "evaluation_id": "EVAL-20260915-001",
            # missing ean_barcode, discounted_price_cents, quantity, printer_id
        }
        response = client.post("/v1/markdown/print-label", json=invalid_payload)
        assert response.status_code == 400
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_print_label_business_rule_violation_returns_422(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/print-label returns status_code 422 on business rule violation."""
        violating_payload = {
            "request_id": str(uuid.uuid4()),
            "evaluation_id": "EVAL-INVALID-PRINTER",
            "ean_barcode": "3560070123456",
            "discounted_price_cents": 245,
            "quantity": 12,
            "printer_id": "UNAUTHORIZED_OFFLINE_PRINTER",
        }
        response = client.post("/v1/markdown/print-label", json=violating_payload)
        assert response.status_code == 422
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_print_label_adapter_failure_returns_500(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/print-label returns status_code 500 when printing adapter fails."""
        headers = {"X-Simulate-Fault": "PRINTER_SUBSYSTEM_ERROR"}
        payload = {
            "request_id": str(uuid.uuid4()),
            "evaluation_id": "EVAL-FAULT",
            "ean_barcode": "3560070123456",
            "discounted_price_cents": 245,
            "quantity": 1,
            "printer_id": "PRINTER_ZEBRA_BT_01",
        }
        response = client.post("/v1/markdown/print-label", headers=headers, json=payload)
        assert response.status_code == 500
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body
        assert "Traceback" not in response.text

    # =========================================================================
    # POST /v1/markdown/pos-feed
    # Documented status codes: 201, 400, 422, 500
    # =========================================================================

    def test_post_pos_feed_returns_201_and_valid_schema(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/pos-feed returns status_code 201 and PosFeedPublishResponse schema."""
        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "ean_barcode": "3560070123456",
            "promotional_barcode": "2901234524508",
            "discounted_price_cents": 245,
            "valid_until": "2026-09-16T22:00:00Z",
        }
        response = client.post("/v1/markdown/pos-feed", json=payload)
        assert response.status_code == 201
        assert response.headers["content-type"].startswith("application/json")
        data: Mapping[str, Any] = response.json()
        assert "message_id" in data
        assert data["topic"] == "pos-markdown-updates"
        assert "published_at" in data

    def test_post_pos_feed_missing_required_fields_returns_400(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/pos-feed returns status_code 400 when required fields are missing."""
        invalid_payload = {
            "request_id": str(uuid.uuid4()),
            # missing store_id, barcodes, discounted_price_cents, valid_until
        }
        response = client.post("/v1/markdown/pos-feed", json=invalid_payload)
        assert response.status_code == 400
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_pos_feed_business_rule_violation_returns_422(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/pos-feed returns status_code 422 when payload violates business constraints."""
        violating_payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "ean_barcode": "3560070123456",
            "promotional_barcode": "2901234524508",
            "discounted_price_cents": 245,
            "valid_until": "2020-01-01T00:00:00Z",  # validity window expired in past
        }
        response = client.post("/v1/markdown/pos-feed", json=violating_payload)
        assert response.status_code == 422
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_pos_feed_pubsub_fault_returns_500(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/pos-feed returns status_code 500 when Pub/Sub publishing encounters internal error."""
        headers = {"X-Simulate-Fault": "PUBSUB_UNAVAILABLE"}
        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "ean_barcode": "3560070123456",
            "promotional_barcode": "2901234524508",
            "discounted_price_cents": 245,
            "valid_until": "2026-09-16T22:00:00Z",
        }
        response = client.post("/v1/markdown/pos-feed", headers=headers, json=payload)
        assert response.status_code == 500
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body
        assert "Traceback" not in response.text

    # =========================================================================
    # POST /v1/markdown/donations
    # Documented status codes: 201, 400, 422, 500
    # =========================================================================

    def test_post_donations_returns_201_and_valid_schema(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/donations returns status_code 201 and DonationSpoilageResponse schema."""
        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "sku_id": "SKU-YOGURT-BIO-01",
            "lot_number": "LOT-2026-09-A",
            "action_type": "CHARITY_DONATION",
            "quantity": 10,
            "original_value_cents": 3500,
            "reason_code": "AGEC_DONATION_BANQUE_ALIMENTAIRE",
            "beneficiary_name": "Banques Alimentaires Paris 15",
        }
        response = client.post("/v1/markdown/donations", json=payload)
        assert response.status_code == 201
        assert response.headers["content-type"].startswith("application/json")
        data: Mapping[str, Any] = response.json()
        assert "record_id" in data
        assert "fiscal_slip_id" in data
        assert data["action_type"] == "CHARITY_DONATION"
        assert isinstance(data["stock_decremented"], bool)
        assert data["stock_decremented"] is True
        assert "timestamp" in data

    def test_post_donations_missing_required_fields_returns_400(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/donations returns status_code 400 when required fields are missing."""
        invalid_payload = {
            "request_id": str(uuid.uuid4()),
            # missing store_id, sku_id, action_type, quantity, etc.
        }
        response = client.post("/v1/markdown/donations", json=invalid_payload)
        assert response.status_code == 400
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_donations_business_rule_violation_returns_422(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/donations returns status_code 422 on business rule violation."""
        violating_payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "sku_id": "SKU-YOGURT-BIO-01",
            "lot_number": "LOT-2026-09-A",
            "action_type": "INVALID_ACTION_TYPE",  # not in enum
            "quantity": 10,
            "original_value_cents": 3500,
            "reason_code": "AGEC_DONATION_BANQUE_ALIMENTAIRE",
        }
        response = client.post("/v1/markdown/donations", json=violating_payload)
        assert response.status_code == 422
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body

    def test_post_donations_adapter_fault_returns_500(self, client: TestClient) -> None:
        """Assert POST /v1/markdown/donations returns status_code 500 when database transaction fails."""
        headers = {"X-Simulate-Fault": "BIGQUERY_AUDIT_ERROR"}
        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "sku_id": "SKU-YOGURT-BIO-01",
            "lot_number": "LOT-2026-09-A",
            "action_type": "CHARITY_DONATION",
            "quantity": 5,
            "original_value_cents": 1750,
            "reason_code": "AGEC_DONATION_BANQUE_ALIMENTAIRE",
        }
        response = client.post("/v1/markdown/donations", headers=headers, json=payload)
        assert response.status_code == 500
        error_body: Mapping[str, Any] = response.json()
        assert "code" in error_body
        assert "message" in error_body
        assert "Traceback" not in response.text
