"""Orthogonal Contract Verification Test Suite for stock_ledger Subsystem.

Validates that subsystem HTTP entrypoints strictly adhere to the frozen
src/modules/stock_ledger/openapi.yaml contract, including HTTP status codes,
response schemas, error structures, and header conventions.

This test suite is authored by the Independent Test Architect and executes
orthogonally to developer unit tests. It treats the subsystem as a black box:
it imports ONLY the public entrypoint app, never internal `domain/` or `adapters/` classes.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

FROZEN_CONTRACT = Path("src/modules/stock_ledger/openapi.yaml")


class TestStockLedgerContractConformance:
    """Black-box OpenAPI contract compliance test suite for stock_ledger."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Instantiate test client for the subsystem public entrypoint."""
        from src.modules.stock_ledger.entrypoints.api import app

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
    # GET /v1/stores/{store_id}/stock
    # Status codes: 200, 400, 403, 500
    # =========================================================================

    def test_get_stock_returns_200_with_valid_schema(self, client: TestClient) -> None:
        """Assert GET /v1/stores/{store_id}/stock returns status_code 200 with StockListResponse."""
        response = client.get(
            "/v1/stores/STORE_FR_75015/stock?department_id=RAYON_FRAIS&zone=SALES_FLOOR_FACING",
            headers={"X-User-Role": "CHEF_DE_RAYON", "X-User-Departments": "RAYON_FRAIS"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        data: Mapping[str, Any] = response.json()
        assert "store_id" in data
        assert "department_id" in data
        assert "total_items" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        if data["items"]:
            item = data["items"][0]
            assert "sku_id" in item
            assert "ean13" in item
            assert "product_name" in item
            assert "department_id" in item
            assert "zone" in item
            assert "quantity" in item
            assert "unit_price_cents" in item

    def test_get_stock_missing_department_returns_400_bad_request(
        self, client: TestClient
    ) -> None:
        """Assert GET /v1/stores/{store_id}/stock returns status_code 400 when required param is missing."""
        response = client.get("/v1/stores/STORE_FR_75015/stock")
        assert response.status_code == 400
        data: Mapping[str, Any] = response.json()
        assert "code" in data
        assert "message" in data

    def test_get_stock_out_of_scope_department_returns_403_forbidden(
        self, client: TestClient
    ) -> None:
        """Assert GET /v1/stores/{store_id}/stock returns status_code 403 for out-of-scope department."""
        response = client.get(
            "/v1/stores/STORE_FR_75015/stock?department_id=RAYON_EPICERIE",
            headers={"X-User-Role": "CHEF_DE_RAYON", "X-User-Departments": "RAYON_FRAIS"},
        )
        assert response.status_code == 403
        data: Mapping[str, Any] = response.json()
        assert "code" in data
        assert data["code"] == "ERR_OUT_OF_SCOPE_DEPARTMENT"
        assert "message" in data

    def test_get_stock_internal_server_error_returns_500(self, client: TestClient) -> None:
        """Assert GET /v1/stores/{store_id}/stock returns status_code 500 on internal fault without leaking internals."""
        response = client.get(
            "/v1/stores/TRIGGER_FAULT/stock?department_id=RAYON_FRAIS",
            headers={"X-User-Role": "CHEF_DE_RAYON", "X-User-Departments": "RAYON_FRAIS"},
        )
        assert response.status_code == 500
        data: Mapping[str, Any] = response.json()
        assert "code" in data
        assert "message" in data
        assert "Traceback" not in response.text

    # =========================================================================
    # POST /v1/stores/{store_id}/adjustments
    # Status codes: 200, 202, 400, 403, 422, 500
    # =========================================================================

    def test_post_adjustment_low_value_auto_approved_returns_200(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/adjustments returns status_code 200 for adjustments < 500 EUR."""
        payload = {
            "sku_id": "SKU-FRAIS-101",
            "department_id": "RAYON_FRAIS",
            "zone": "SALES_FLOOR_FACING",
            "quantity_delta": -2,
            "unit_price_cents": 1500,  # 30 EUR total (< 500 EUR)
            "reason_code": "BREAKAGE",
            "initiator_id": "chef_frais_01@carrefour.com",
            "initiator_role": "CHEF_DE_RAYON",
            "user_departments": ["RAYON_FRAIS"],
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/adjustments",
            json=payload,
            headers={"Idempotency-Key": "a0000000-0000-0000-0000-000000000001"},
        )
        assert response.status_code == 200
        data: Mapping[str, Any] = response.json()
        assert "adjustment_id" in data
        assert "store_id" in data
        assert "sku_id" in data
        assert "department_id" in data
        assert "zone" in data
        assert "quantity_delta" in data
        assert "total_value_cents" in data
        assert "status" in data
        assert data["status"] == "AUTO_APPROVED"
        assert "message" in data

    def test_post_adjustment_high_value_returns_202_accepted(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/adjustments returns status_code 202 for adjustments >= 500 EUR."""
        payload = {
            "sku_id": "SKU-FRAIS-101",
            "department_id": "RAYON_FRAIS",
            "zone": "COLD_STORAGE_RESERVE",
            "quantity_delta": -10,
            "unit_price_cents": 5500,  # 550 EUR total (>= 500 EUR)
            "reason_code": "THEFT",
            "initiator_id": "chef_frais_01@carrefour.com",
            "initiator_role": "CHEF_DE_RAYON",
            "user_departments": ["RAYON_FRAIS"],
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/adjustments",
            json=payload,
            headers={"Idempotency-Key": "a0000000-0000-0000-0000-000000000002"},
        )
        assert response.status_code == 202
        data: Mapping[str, Any] = response.json()
        assert "adjustment_id" in data
        assert data["status"] == "PENDING_DIRECTOR_APPROVAL"
        assert data["total_value_cents"] == 55000

    def test_post_adjustment_malformed_payload_returns_400_bad_request(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/adjustments returns status_code 400 for malformed payload or missing Idempotency-Key."""
        response = client.post(
            "/v1/stores/STORE_FR_75015/adjustments",
            json={"invalid_field": "xyz"},
        )
        assert response.status_code == 400
        data: Mapping[str, Any] = response.json()
        assert "code" in data
        assert "message" in data

    def test_post_adjustment_out_of_scope_department_returns_403_forbidden(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/adjustments returns status_code 403 when user is not authorized for target department."""
        payload = {
            "sku_id": "SKU-EPICERIE-404",
            "department_id": "RAYON_EPICERIE",
            "zone": "DRY_RESERVE",
            "quantity_delta": -5,
            "unit_price_cents": 2000,
            "reason_code": "MISCOUNT",
            "initiator_id": "chef_frais_01@carrefour.com",
            "initiator_role": "CHEF_DE_RAYON",
            "user_departments": ["RAYON_FRAIS"],  # Does not have RAYON_EPICERIE
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/adjustments",
            json=payload,
            headers={"Idempotency-Key": "a0000000-0000-0000-0000-000000000003"},
        )
        assert response.status_code == 403
        data: Mapping[str, Any] = response.json()
        assert "code" in data
        assert data["code"] == "ERR_OUT_OF_SCOPE_DEPARTMENT"

    def test_post_adjustment_insufficient_stock_returns_422_unprocessable(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/adjustments returns status_code 422 for insufficient stock balance or invalid zone."""
        payload = {
            "sku_id": "SKU-FRAIS-101",
            "department_id": "RAYON_FRAIS",
            "zone": "SALES_FLOOR_FACING",
            "quantity_delta": -999999,  # Impossible deduction
            "unit_price_cents": 100,
            "reason_code": "THEFT",
            "initiator_id": "chef_frais_01@carrefour.com",
            "initiator_role": "CHEF_DE_RAYON",
            "user_departments": ["RAYON_FRAIS"],
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/adjustments",
            json=payload,
            headers={"Idempotency-Key": "a0000000-0000-0000-0000-000000000004"},
        )
        assert response.status_code == 422
        data: Mapping[str, Any] = response.json()
        assert "code" in data
        assert "message" in data

    def test_post_adjustment_internal_server_error_returns_500(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/adjustments returns status_code 500 on unexpected failure."""
        payload = {
            "sku_id": "TRIGGER_FAULT",
            "department_id": "RAYON_FRAIS",
            "zone": "SALES_FLOOR_FACING",
            "quantity_delta": -1,
            "unit_price_cents": 100,
            "reason_code": "OTHER",
            "initiator_id": "chef_frais_01@carrefour.com",
            "initiator_role": "CHEF_DE_RAYON",
            "user_departments": ["RAYON_FRAIS"],
        }
        response = client.post(
            "/v1/stores/TRIGGER_FAULT/adjustments",
            json=payload,
            headers={"Idempotency-Key": "a0000000-0000-0000-0000-000000000005"},
        )
        assert response.status_code == 500
        data: Mapping[str, Any] = response.json()
        assert "code" in data
        assert "message" in data
        assert "Traceback" not in response.text

    # =========================================================================
    # POST /v1/stores/{store_id}/adjustments/{adjustment_id}/sign-off
    # Status codes: 200, 400, 403, 404, 409, 500
    # =========================================================================

    def test_post_sign_off_approve_returns_200(self, client: TestClient) -> None:
        """Assert POST /v1/stores/{store_id}/adjustments/{adjustment_id}/sign-off returns status_code 200 on APPROVE decision."""
        payload = {
            "director_id": "directeur_75015@carrefour.com",
            "action": "APPROVE",
            "note": "Approved after physical inspection of cold storage.",
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/adjustments/adj-pending-001/sign-off",
            json=payload,
            headers={"X-User-Role": "DIRECTEUR_MAGASIN"},
        )
        assert response.status_code == 200
        data: Mapping[str, Any] = response.json()
        assert "adjustment_id" in data
        assert data["status"] == "APPROVED"

    def test_post_sign_off_reject_missing_note_returns_400_bad_request(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/adjustments/{adjustment_id}/sign-off returns status_code 400 when REJECT note is missing."""
        payload = {
            "director_id": "directeur_75015@carrefour.com",
            "action": "REJECT",
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/adjustments/adj-pending-001/sign-off",
            json=payload,
            headers={"X-User-Role": "DIRECTEUR_MAGASIN"},
        )
        assert response.status_code == 400
        data: Mapping[str, Any] = response.json()
        assert "code" in data
        assert "message" in data

    def test_post_sign_off_non_director_role_returns_403_forbidden(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/adjustments/{adjustment_id}/sign-off returns status_code 403 when role is not DIRECTEUR_MAGASIN."""
        payload = {
            "director_id": "chef_frais_01@carrefour.com",
            "action": "APPROVE",
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/adjustments/adj-pending-001/sign-off",
            json=payload,
            headers={"X-User-Role": "CHEF_DE_RAYON"},
        )
        assert response.status_code == 403
        data: Mapping[str, Any] = response.json()
        assert "code" in data

    def test_post_sign_off_nonexistent_adjustment_returns_404_not_found(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/adjustments/{adjustment_id}/sign-off returns status_code 404 for unknown adjustment ID."""
        payload = {
            "director_id": "directeur_75015@carrefour.com",
            "action": "APPROVE",
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/adjustments/non-existent-adj-id/sign-off",
            json=payload,
            headers={"X-User-Role": "DIRECTEUR_MAGASIN"},
        )
        assert response.status_code == 404
        data: Mapping[str, Any] = response.json()
        assert "code" in data

    def test_post_sign_off_not_pending_state_returns_409_conflict(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/adjustments/{adjustment_id}/sign-off returns status_code 409 if adjustment is not in PENDING state."""
        payload = {
            "director_id": "directeur_75015@carrefour.com",
            "action": "APPROVE",
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/adjustments/adj-already-approved/sign-off",
            json=payload,
            headers={"X-User-Role": "DIRECTEUR_MAGASIN"},
        )
        assert response.status_code == 409
        data: Mapping[str, Any] = response.json()
        assert "code" in data

    def test_post_sign_off_internal_error_returns_500(self, client: TestClient) -> None:
        """Assert POST /v1/stores/{store_id}/adjustments/{adjustment_id}/sign-off returns status_code 500 on unexpected fault."""
        payload = {
            "director_id": "directeur_75015@carrefour.com",
            "action": "APPROVE",
        }
        response = client.post(
            "/v1/stores/TRIGGER_FAULT/adjustments/TRIGGER_FAULT/sign-off",
            json=payload,
            headers={"X-User-Role": "DIRECTEUR_MAGASIN"},
        )
        assert response.status_code == 500
        data: Mapping[str, Any] = response.json()
        assert "code" in data
        assert "Traceback" not in response.text

    # =========================================================================
    # POST /v1/stores/{store_id}/transfers
    # Status codes: 200, 400, 403, 422, 500
    # =========================================================================

    def test_post_transfer_valid_movement_returns_200(self, client: TestClient) -> None:
        """Assert POST /v1/stores/{store_id}/transfers returns status_code 200 and TransferResponse."""
        payload = {
            "sku_id": "SKU-EPICERIE-404",
            "department_id": "RAYON_EPICERIE",
            "source_zone": "DRY_RESERVE",
            "target_zone": "IN_TRANSIT_FLOOR",
            "quantity": 24,
            "operator_id": "els_jean@carrefour.com",
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/transfers",
            json=payload,
            headers={
                "Idempotency-Key": "b0000000-0000-0000-0000-000000000001",
                "X-User-Departments": "RAYON_EPICERIE",
            },
        )
        assert response.status_code == 200
        data: Mapping[str, Any] = response.json()
        assert "transfer_id" in data
        assert "store_id" in data
        assert "sku_id" in data
        assert "source_zone" in data
        assert "target_zone" in data
        assert "quantity" in data
        assert "status" in data
        assert data["status"] == "COMMITTED"

    def test_post_transfer_invalid_payload_returns_400_bad_request(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/transfers returns status_code 400 on malformed input."""
        response = client.post(
            "/v1/stores/STORE_FR_75015/transfers",
            json={"quantity": -5},
        )
        assert response.status_code == 400
        data: Mapping[str, Any] = response.json()
        assert "code" in data

    def test_post_transfer_department_mismatch_returns_403_forbidden(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/transfers returns status_code 403 for unauthorized department movement."""
        payload = {
            "sku_id": "SKU-EPICERIE-404",
            "department_id": "RAYON_EPICERIE",
            "source_zone": "DRY_RESERVE",
            "target_zone": "SALES_FLOOR_FACING",
            "quantity": 10,
            "operator_id": "els_jean@carrefour.com",
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/transfers",
            json=payload,
            headers={
                "Idempotency-Key": "b0000000-0000-0000-0000-000000000002",
                "X-User-Departments": "RAYON_FRAIS",
            },
        )
        assert response.status_code == 403
        data: Mapping[str, Any] = response.json()
        assert "code" in data

    def test_post_transfer_insufficient_source_balance_returns_422_unprocessable(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/transfers returns status_code 422 when source zone lacks stock."""
        payload = {
            "sku_id": "SKU-EPICERIE-404",
            "department_id": "RAYON_EPICERIE",
            "source_zone": "DRY_RESERVE",
            "target_zone": "SALES_FLOOR_FACING",
            "quantity": 999999,
            "operator_id": "els_jean@carrefour.com",
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/transfers",
            json=payload,
            headers={
                "Idempotency-Key": "b0000000-0000-0000-0000-000000000003",
                "X-User-Departments": "RAYON_EPICERIE",
            },
        )
        assert response.status_code == 422
        data: Mapping[str, Any] = response.json()
        assert "code" in data

    def test_post_transfer_internal_error_returns_500(self, client: TestClient) -> None:
        """Assert POST /v1/stores/{store_id}/transfers returns status_code 500 on unexpected fault."""
        payload = {
            "sku_id": "TRIGGER_FAULT",
            "department_id": "RAYON_EPICERIE",
            "source_zone": "DRY_RESERVE",
            "target_zone": "SALES_FLOOR_FACING",
            "quantity": 1,
            "operator_id": "els_jean@carrefour.com",
        }
        response = client.post(
            "/v1/stores/TRIGGER_FAULT/transfers",
            json=payload,
            headers={"Idempotency-Key": "b0000000-0000-0000-0000-000000000004"},
        )
        assert response.status_code == 500
        data: Mapping[str, Any] = response.json()
        assert "code" in data
        assert "Traceback" not in response.text

    # =========================================================================
    # POST /v1/stores/{store_id}/pos-depletions
    # Status codes: 200, 400, 422, 500
    # =========================================================================

    def test_post_pos_depletion_valid_basket_returns_200(self, client: TestClient) -> None:
        """Assert POST /v1/stores/{store_id}/pos-depletions returns status_code 200 and PosDepletionResponse."""
        payload = {
            "receipt_id": "REC-20260915-00129",
            "till_id": "TILL-04",
            "timestamp": "2026-09-15T11:45:00Z",
            "items": [
                {"ean13": "3560070123456", "quantity": 2},
                {"ean13": "3560070987654", "quantity": 1},
            ],
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/pos-depletions",
            json=payload,
            headers={"Idempotency-Key": "REC-20260915-00129"},
        )
        assert response.status_code == 200
        data: Mapping[str, Any] = response.json()
        assert "receipt_id" in data
        assert "store_id" in data
        assert "processed_items" in data
        assert "status" in data
        assert data["status"] == "DEPLETED"

    def test_post_pos_depletion_malformed_receipt_returns_400_bad_request(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/pos-depletions returns status_code 400 for malformed payload."""
        response = client.post(
            "/v1/stores/STORE_FR_75015/pos-depletions",
            json={"invalid": True},
        )
        assert response.status_code == 400
        data: Mapping[str, Any] = response.json()
        assert "code" in data

    def test_post_pos_depletion_unknown_sku_returns_422_unprocessable(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/pos-depletions returns status_code 422 for unknown SKU/EAN."""
        payload = {
            "receipt_id": "REC-20260915-00130",
            "till_id": "TILL-04",
            "timestamp": "2026-09-15T11:46:00Z",
            "items": [{"ean13": "0000000000000", "quantity": 1}],
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/pos-depletions",
            json=payload,
            headers={"Idempotency-Key": "REC-20260915-00130"},
        )
        assert response.status_code == 422
        data: Mapping[str, Any] = response.json()
        assert "code" in data

    def test_post_pos_depletion_internal_error_returns_500(
        self, client: TestClient
    ) -> None:
        """Assert POST /v1/stores/{store_id}/pos-depletions returns status_code 500 on unexpected fault."""
        payload = {
            "receipt_id": "TRIGGER_FAULT",
            "till_id": "TILL-04",
            "timestamp": "2026-09-15T11:47:00Z",
            "items": [{"ean13": "3560070123456", "quantity": 1}],
        }
        response = client.post(
            "/v1/stores/TRIGGER_FAULT/pos-depletions",
            json=payload,
            headers={"Idempotency-Key": "REC-FAULT"},
        )
        assert response.status_code == 500
        data: Mapping[str, Any] = response.json()
        assert "code" in data
        assert "Traceback" not in response.text
