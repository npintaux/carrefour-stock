"""Canonical Behavioral Verification Test Suite for inbound_dock.

Tests end-to-end user stories and acceptance criteria defined in docs/PRD.md
and mapped to inbound_dock in docs/traceability.md.

Every test method maps directly to a PRD User Story (US-3) and Acceptance
Criterion (AC-3.1, AC-3.2, AC-3.3) for strict end-to-end traceability.

Black-box isolation: tests interact exclusively with the public HTTP entrypoint
without importing internal domain or adapter classes.
"""

from collections.abc import Mapping
import time
from typing import Any
import uuid

import pytest
from fastapi.testclient import TestClient


class TestBehavioralInboundDock:
    """End-to-end user story and acceptance criteria verification for inbound_dock."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Instantiate test client for the inbound_dock public entrypoint."""
        from src.modules.inbound_dock.entrypoints.api import app

        return TestClient(app)

    # --- User Story US-3: Receiving Dock ASN Barcode Ingestion & Cold-Chain Check ---
    # Acceptance Criteria AC-3.1, AC-3.2, AC-3.3

    def test_us3_ac3_1_cold_chain_violation_triggers_quarantine_lock(
        self, client: TestClient
    ) -> None:
        """[US-3][AC-3.1] Refrigerated pallet temperature violation (0-4°C) triggers quarantine lock.

        Given an inbound refrigerated pallet with target temperature 0°C - 4°C,
        when the specialist inputs a probed temperature of 7.5°C,
        then the system automatically triggers a COLD_CHAIN_VIOLATION prompt,
        locks the pallet from available inventory, and marks it STATUS_QUARANTINE.
        """
        # Step 1: Ingest ASN with a chilled pallet (target 0-4°C)
        asn_id = f"ASN-CHILLED-{uuid.uuid4().hex[:8]}"
        sscc = "037000123456789012"
        ingest_payload = {
            "asn_id": asn_id,
            "store_id": "STORE_FR_75015",
            "supplier_id": "SUPPLIER_DC_CREPY",
            "expected_delivery": "2026-09-15T06:30:00Z",
            "pallets": [
                {
                    "sscc": sscc,
                    "temperature_regime": "CHILLED",
                    "lines": [
                        {
                            "sku": "SKU-FRESH-MILK-01",
                            "ean13": "3560070112233",
                            "expected_quantity": 60,
                            "lot_number": "LOT-MILK-2026",
                            "bbd": "2026-09-22",
                        }
                    ],
                }
            ],
        }
        ingest_resp = client.post(
            "/v1/inbound-shipments",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=ingest_payload,
        )
        assert ingest_resp.status_code == 201

        # Step 2: Receiving specialist scans pallet and inputs probed temperature of 7.5°C (> 4.0°C)
        receive_payload = {
            "sscc": sscc,
            "store_id": "STORE_FR_75015",
            "operator_id": "OP_DOCK_SPECIALIST_01",
            "probed_temperature": 7.5,
            "damage_observed": False,
            "notes": "Probed temperature 7.5C violates 0-4C cold-chain specification",
        }
        receive_resp = client.post(
            f"/v1/inbound-shipments/{asn_id}/receive-pallet",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=receive_payload,
        )
        assert receive_resp.status_code == 200
        data: Mapping[str, Any] = receive_resp.json()

        # Assert cold-chain quarantine lock
        assert data["is_compliant"] is False
        assert data["status"] == "STATUS_QUARANTINE"
        assert data["target_location"] == "QUARANTINE_DAMAGED"
        assert "COLD_CHAIN_VIOLATION" in (data.get("violation_reason") or "")

        # Verify ASN state reflects quarantine status
        get_resp = client.get(f"/v1/stores/STORE_FR_75015/inbound-shipments/{asn_id}")
        assert get_resp.status_code == 200
        asn_data: Mapping[str, Any] = get_resp.json()
        matching_pallet = next((p for p in asn_data["pallets"] if p["sscc"] == sscc), None)
        assert matching_pallet is not None
        assert matching_pallet["status"] == "STATUS_QUARANTINE"
        assert matching_pallet["probed_temperature"] == 7.5

    def test_us3_ac3_1_frozen_pallet_temperature_violation_triggers_quarantine(
        self, client: TestClient
    ) -> None:
        """[US-3][AC-3.1] Frozen pallet temperature violation (-18°C) triggers quarantine lock.

        Given an inbound frozen pallet with target temperature <= -18°C,
        when probed temperature is -12.0°C (> -18°C),
        then the system flags COLD_CHAIN_VIOLATION and quarantines the pallet.
        """
        asn_id = f"ASN-FROZEN-{uuid.uuid4().hex[:8]}"
        sscc = "037000987654321098"
        ingest_payload = {
            "asn_id": asn_id,
            "store_id": "STORE_FR_75015",
            "supplier_id": "SUPPLIER_DC_CREPY",
            "expected_delivery": "2026-09-15T06:30:00Z",
            "pallets": [
                {
                    "sscc": sscc,
                    "temperature_regime": "FROZEN",
                    "lines": [
                        {
                            "sku": "SKU-FROZEN-PIZZA",
                            "ean13": "3560070445566",
                            "expected_quantity": 40,
                            "lot_number": "LOT-PIZZA-2026",
                            "bbd": "2027-03-31",
                        }
                    ],
                }
            ],
        }
        client.post(
            "/v1/inbound-shipments",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=ingest_payload,
        )

        # Probed temperature -12.0°C breaches -18°C threshold
        receive_payload = {
            "sscc": sscc,
            "store_id": "STORE_FR_75015",
            "operator_id": "OP_DOCK_SPECIALIST_01",
            "probed_temperature": -12.0,
            "damage_observed": False,
        }
        receive_resp = client.post(
            f"/v1/inbound-shipments/{asn_id}/receive-pallet",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=receive_payload,
        )
        assert receive_resp.status_code == 200
        data: Mapping[str, Any] = receive_resp.json()
        assert data["is_compliant"] is False
        assert data["status"] == "STATUS_QUARANTINE"

    def test_us3_ac3_1_compliant_temperature_moves_to_staging(
        self, client: TestClient
    ) -> None:
        """[US-3][AC-3.1] Compliant temperature transitions pallet to BACKROOM_STAGING."""
        asn_id = f"ASN-COMPLIANT-{uuid.uuid4().hex[:8]}"
        sscc = "037000111222333444"
        ingest_payload = {
            "asn_id": asn_id,
            "store_id": "STORE_FR_75015",
            "supplier_id": "SUPPLIER_DC_CREPY",
            "expected_delivery": "2026-09-15T06:30:00Z",
            "pallets": [
                {
                    "sscc": sscc,
                    "temperature_regime": "CHILLED",
                    "lines": [
                        {
                            "sku": "SKU-BUTTER-01",
                            "ean13": "3560070778899",
                            "expected_quantity": 100,
                            "lot_number": "LOT-BUTTER-01",
                            "bbd": "2026-10-15",
                        }
                    ],
                }
            ],
        }
        client.post(
            "/v1/inbound-shipments",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=ingest_payload,
        )

        receive_payload = {
            "sscc": sscc,
            "store_id": "STORE_FR_75015",
            "operator_id": "OP_DOCK_SPECIALIST_01",
            "probed_temperature": 2.5,  # within [0, 4]
            "damage_observed": False,
        }
        receive_resp = client.post(
            f"/v1/inbound-shipments/{asn_id}/receive-pallet",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=receive_payload,
        )
        assert receive_resp.status_code == 200
        data: Mapping[str, Any] = receive_resp.json()
        assert data["is_compliant"] is True
        assert data["status"] == "BACKROOM_STAGING"
        assert data["target_location"] in ["BACKROOM_STAGING", "COLD_STORAGE_RESERVE"]

    def test_us3_ac3_2_sscc_barcode_scan_retrieves_asn_within_sla(
        self, client: TestClient
    ) -> None:
        """[US-3][AC-3.2] Scanning SSCC barcode retrieves matching ASN line items in <= 150ms.

        Given an incoming SSCC barcode scanned on mobile terminal,
        when scanned, then matching ASN line items appear in <= 150ms from Redis cache.
        """
        asn_id = f"ASN-FAST-LOOKUP-{uuid.uuid4().hex[:8]}"
        sscc = "037000555666777888"
        ingest_payload = {
            "asn_id": asn_id,
            "store_id": "STORE_FR_75015",
            "supplier_id": "SUPPLIER_DC_LILLE",
            "expected_delivery": "2026-09-15T07:00:00Z",
            "pallets": [
                {
                    "sscc": sscc,
                    "temperature_regime": "AMBIENT",
                    "lines": [
                        {
                            "sku": "SKU-COFFEE-BEANS",
                            "ean13": "3560070111111",
                            "expected_quantity": 200,
                            "lot_number": "LOT-COFFEE-01",
                            "bbd": "2027-06-30",
                        }
                    ],
                }
            ],
        }
        # Ingest shipment
        client.post(
            "/v1/inbound-shipments",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=ingest_payload,
        )

        # Warm lookup and measure latency
        start_time = time.perf_counter()
        resp = client.get(f"/v1/stores/STORE_FR_75015/inbound-shipments/{asn_id}")
        duration_ms = (time.perf_counter() - start_time) * 1000

        assert resp.status_code == 200
        data: Mapping[str, Any] = resp.json()
        assert data["asn_id"] == asn_id
        assert len(data["pallets"]) >= 1
        pallet = data["pallets"][0]
        assert pallet["sscc"] == sscc
        assert len(pallet["lines"]) >= 1
        assert pallet["lines"][0]["sku"] == "SKU-COFFEE-BEANS"

        # Assert SLA budget (<= 150ms)
        assert duration_ms <= 150.0, f"Query took {duration_ms:.2f}ms, exceeding 150ms SLA"

    def test_us3_ac3_3_offline_mobile_terminal_sync_with_idempotency_keys(
        self, client: TestClient
    ) -> None:
        """[US-3][AC-3.3] Offline queued scans sync with UUID idempotency tokens without duplicates.

        Given poor dock Wi-Fi, when scans are recorded offline,
        then the terminal queues transactions locally and pushes them with UUID idempotency
        tokens upon reconnection without duplicate stock entries.
        """
        asn_id = f"ASN-OFFLINE-SYNC-{uuid.uuid4().hex[:8]}"
        sscc = "037000999888777666"
        ingest_payload = {
            "asn_id": asn_id,
            "store_id": "STORE_FR_75015",
            "supplier_id": "SUPPLIER_DC_LILLE",
            "expected_delivery": "2026-09-15T07:00:00Z",
            "pallets": [
                {
                    "sscc": sscc,
                    "temperature_regime": "AMBIENT",
                    "lines": [
                        {
                            "sku": "SKU-MINERAL-WATER",
                            "ean13": "3560070222222",
                            "expected_quantity": 500,
                            "lot_number": "LOT-WATER-01",
                            "bbd": "2028-01-01",
                        }
                    ],
                }
            ],
        }
        client.post(
            "/v1/inbound-shipments",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=ingest_payload,
        )

        offline_idempotency_token = str(uuid.uuid4())
        receive_payload = {
            "sscc": sscc,
            "store_id": "STORE_FR_75015",
            "operator_id": "OP_DOCK_OFFLINE_01",
            "probed_temperature": 18.0,
            "damage_observed": False,
            "notes": "Synchronized from offline local queue buffer",
        }

        # First synchronization attempt (e.g. initial connection flush)
        resp1 = client.post(
            f"/v1/inbound-shipments/{asn_id}/receive-pallet",
            headers={"Idempotency-Key": offline_idempotency_token},
            json=receive_payload,
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["status"] == "BACKROOM_STAGING"

        # Replay identical payload with exact same UUID idempotency token (network retry simulation)
        resp2 = client.post(
            f"/v1/inbound-shipments/{asn_id}/receive-pallet",
            headers={"Idempotency-Key": offline_idempotency_token},
            json=receive_payload,
        )
        # Idempotent response: same outcome without duplicate receiving or 409 error
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["sscc"] == data1["sscc"]
        assert data2["status"] == data1["status"]

        # Verify shipment only shows the pallet received once
        asn_check = client.get(f"/v1/stores/STORE_FR_75015/inbound-shipments/{asn_id}")
        assert asn_check.status_code == 200
        asn_data = asn_check.json()
        assert asn_data["received_pallets"] == 1
