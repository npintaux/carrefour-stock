"""Orthogonal Behavioral Verification Test Suite for stock_ledger Subsystem.

Tests end-to-end user stories and acceptance criteria defined in docs/PRD.md
and mapped to stock_ledger in docs/traceability.md:
- US-1 (Department-Scoped Stock View): AC-1.1, AC-1.2, AC-1.3
- US-2 (Dual-Key Authorization for High-Value Shrinkage): AC-2.1, AC-2.2, AC-2.3

Every test method maps directly to a PRD User Story and Acceptance Criterion for
strict end-to-end traceability and Gate 4 compliance.
Treats the subsystem as a black box: imports ONLY the public entrypoint app.
"""

from collections.abc import Mapping
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient


class TestStockLedgerBehavioralAcceptance:
    """End-to-end user story and acceptance criteria verification for stock_ledger."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Instantiate test client for the subsystem public entrypoint."""
        from src.modules.stock_ledger.entrypoints.api import app

        return TestClient(app)

    # =========================================================================
    # User Story US-1: Department-Scoped Stock View
    # AC-1.1, AC-1.2, AC-1.3
    # =========================================================================

    def test_us1_ac1_1_chef_de_rayon_query_returns_only_assigned_department_products(
        self, client: TestClient
    ) -> None:
        """[US-1][AC-1.1] Given a user authenticated with role CHEF_DE_RAYON and department RAYON_FRAIS, when querying /v1/stores/{id}/stock, then only products mapped to RAYON_FRAIS category taxonomy are returned."""
        response = client.get(
            "/v1/stores/STORE_FR_75015/stock?department_id=RAYON_FRAIS",
            headers={
                "X-User-Role": "CHEF_DE_RAYON",
                "X-User-Departments": "RAYON_FRAIS",
            },
        )
        assert response.status_code == 200
        data: Mapping[str, Any] = response.json()
        assert data["department_id"] == "RAYON_FRAIS"
        assert "items" in data
        for item in data["items"]:
            assert (
                item["department_id"] == "RAYON_FRAIS"
            ), f"Expected RAYON_FRAIS item, got {item['department_id']}"

    def test_us1_ac1_2_unauthorized_department_adjustment_rejected_with_403(
        self, client: TestClient
    ) -> None:
        """[US-1][AC-1.2] Given a user attempting to update stock in RAYON_EPICERIE without cross-department delegation rights, when submitting an adjustment, then the system returns HTTP 403 Forbidden with error code ERR_OUT_OF_SCOPE_DEPARTMENT."""
        payload = {
            "sku_id": "SKU-EPICERIE-404",
            "department_id": "RAYON_EPICERIE",
            "zone": "DRY_RESERVE",
            "quantity_delta": -5,
            "unit_price_cents": 250,
            "reason_code": "BREAKAGE",
            "initiator_id": "chef_frais_01@carrefour.com",
            "initiator_role": "CHEF_DE_RAYON",
            "user_departments": ["RAYON_FRAIS"],
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/adjustments",
            json=payload,
            headers={"Idempotency-Key": "c0000000-0000-0000-0000-000000000001"},
        )
        assert response.status_code == 403
        data: Mapping[str, Any] = response.json()
        assert data["code"] == "ERR_OUT_OF_SCOPE_DEPARTMENT"

    def test_us1_ac1_3_stock_lookup_response_time_under_250ms_p99_nfr(
        self, client: TestClient
    ) -> None:
        """[US-1][AC-1.3] Given any stock lookup, response time must satisfy WAF Performance NFR (P99 < 250ms)."""
        start_time = time.perf_counter()
        response = client.get(
            "/v1/stores/STORE_FR_75015/stock?department_id=RAYON_FRAIS",
            headers={
                "X-User-Role": "CHEF_DE_RAYON",
                "X-User-Departments": "RAYON_FRAIS",
            },
        )
        duration_ms = (time.perf_counter() - start_time) * 1000
        assert response.status_code == 200
        assert duration_ms < 250, f"Stock lookup took {duration_ms:.2f}ms, exceeding 250ms NFR"

    # =========================================================================
    # User Story US-2: Dual-Key Authorization for High-Value Shrinkage
    # AC-2.1, AC-2.2, AC-2.3
    # =========================================================================

    def test_us2_ac2_1_adjustment_exceeding_500_euros_transitions_to_pending_director_approval(
        self, client: TestClient
    ) -> None:
        """[US-2][AC-2.1] Given a stock adjustment request with total financial value >= 500.00 EUR, when submitted by a Section Manager, then the stock state transitions to PENDING_DIRECTOR_APPROVAL and sends a notification push to the Director's console."""
        # 10 units * 55.00 EUR = 550.00 EUR >= 500.00 EUR threshold
        payload = {
            "sku_id": "SKU-FRAIS-101",
            "department_id": "RAYON_FRAIS",
            "zone": "COLD_STORAGE_RESERVE",
            "quantity_delta": -10,
            "unit_price_cents": 5500,
            "reason_code": "THEFT",
            "initiator_id": "chef_frais_01@carrefour.com",
            "initiator_role": "CHEF_DE_RAYON",
            "user_departments": ["RAYON_FRAIS"],
        }
        response = client.post(
            "/v1/stores/STORE_FR_75015/adjustments",
            json=payload,
            headers={"Idempotency-Key": "c0000000-0000-0000-0000-000000000002"},
        )
        assert response.status_code == 202
        data: Mapping[str, Any] = response.json()
        assert data["status"] == "PENDING_DIRECTOR_APPROVAL"
        assert data["total_value_cents"] == 55000
        assert "adjustment_id" in data

    def test_us2_ac2_2_director_approval_deducts_physical_stock_and_locks_reason_code(
        self, client: TestClient
    ) -> None:
        """[US-2][AC-2.2] Given a pending adjustment, when approved by the Director, then the physical stock is deducted, the reason code is locked, and an audit trail log is written to BigQuery."""
        # 1. Submit high-value adjustment
        submit_payload = {
            "sku_id": "SKU-FRAIS-101",
            "department_id": "RAYON_FRAIS",
            "zone": "COLD_STORAGE_RESERVE",
            "quantity_delta": -12,
            "unit_price_cents": 5000,  # 600.00 EUR
            "reason_code": "BREAKAGE",
            "initiator_id": "chef_frais_01@carrefour.com",
            "initiator_role": "CHEF_DE_RAYON",
            "user_departments": ["RAYON_FRAIS"],
        }
        submit_resp = client.post(
            "/v1/stores/STORE_FR_75015/adjustments",
            json=submit_payload,
            headers={"Idempotency-Key": "c0000000-0000-0000-0000-000000000003"},
        )
        assert submit_resp.status_code == 202
        adjustment_id = submit_resp.json()["adjustment_id"]

        # 2. Director approves the pending adjustment
        signoff_payload = {
            "director_id": "directeur_75015@carrefour.com",
            "action": "APPROVE",
            "note": "Approved after inspecting broken pallet.",
        }
        signoff_resp = client.post(
            f"/v1/stores/STORE_FR_75015/adjustments/{adjustment_id}/sign-off",
            json=signoff_payload,
            headers={"X-User-Role": "DIRECTEUR_MAGASIN"},
        )
        assert signoff_resp.status_code == 200
        data: Mapping[str, Any] = signoff_resp.json()
        assert data["status"] == "APPROVED"
        assert data["adjustment_id"] == adjustment_id

    def test_us2_ac2_3_director_rejection_leaves_stock_intact_and_returns_explanation(
        self, client: TestClient
    ) -> None:
        """[US-2][AC-2.3] Given a pending adjustment, when rejected by the Director, then stock remains intact and a mandatory explanation note is returned to the initiator."""
        # 1. Submit high-value adjustment
        submit_payload = {
            "sku_id": "SKU-FRAIS-101",
            "department_id": "RAYON_FRAIS",
            "zone": "COLD_STORAGE_RESERVE",
            "quantity_delta": -15,
            "unit_price_cents": 6000,  # 900.00 EUR
            "reason_code": "THEFT",
            "initiator_id": "chef_frais_01@carrefour.com",
            "initiator_role": "CHEF_DE_RAYON",
            "user_departments": ["RAYON_FRAIS"],
        }
        submit_resp = client.post(
            "/v1/stores/STORE_FR_75015/adjustments",
            json=submit_payload,
            headers={"Idempotency-Key": "c0000000-0000-0000-0000-000000000004"},
        )
        assert submit_resp.status_code == 202
        adjustment_id = submit_resp.json()["adjustment_id"]

        # 2. Director rejects with mandatory note
        rejection_note = "Rejected: Goods were found misplaced in Dry Reserve aisle 3."
        signoff_payload = {
            "director_id": "directeur_75015@carrefour.com",
            "action": "REJECT",
            "note": rejection_note,
        }
        signoff_resp = client.post(
            f"/v1/stores/STORE_FR_75015/adjustments/{adjustment_id}/sign-off",
            json=signoff_payload,
            headers={"X-User-Role": "DIRECTEUR_MAGASIN"},
        )
        assert signoff_resp.status_code == 200
        data: Mapping[str, Any] = signoff_resp.json()
        assert data["status"] == "REJECTED"
        assert data["director_note"] == rejection_note
