"""Orthogonal Behavioral Acceptance Test Suite for markdown_engine Subsystem.

Tests end-to-end user stories and acceptance criteria defined in docs/PRD.md
and mapped in docs/traceability.md:
- US-4: Dynamic Expiry Sticker Generation & POS Feed
  - AC-4.1: T-1 (30%) & T-0 (50%) discount calculation & ESC/POS printer payload within 800ms SLA.
  - AC-4.2: Real-time broadcast of markdown events to Pub/Sub topic `pos-markdown-updates`.
  - AC-4.3: AGEC-compliant charity donation / bio-waste write-off with fiscal slips & stock decrement.

This test suite is authored by the Independent Test Architect and executes
orthogonally to developer unit tests. It treats the subsystem as a black box:
it imports ONLY the public entrypoint app, never internal `domain/` or `adapters/` classes.
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
import time
from typing import Any
import uuid

import pytest
from fastapi.testclient import TestClient

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class TestMarkdownEngineBehavioralAcceptance:
    """End-to-end behavioral verification for US-4 (Dynamic Expiry Sticker Generation & POS Feed)."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Instantiate test client for the markdown_engine public entrypoint."""
        from src.modules.markdown_engine.entrypoints.api import app

        return TestClient(app)

    # =========================================================================
    # User Story US-4 / AC-4.1: Dynamic Expiry Discount Calculation & Print Commands
    # =========================================================================

    def test_us4_ac4_1_dynamic_markdown_t_minus_1_calculates_30_percent_discount(
        self, client: TestClient
    ) -> None:
        """[US-4][AC-4.1] Perishable product with expiry date T-1 calculates 30% markdown price."""
        today = datetime.now(UTC).date()
        t_minus_1_date = (today + timedelta(days=1)).isoformat()
        original_price = 300  # 3.00 EUR

        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "sku_id": "SKU-YOGURT-BIO-01",
            "ean_barcode": "3560070123456",
            "lot_number": "LOT-2026-09-01",
            "expiry_date": t_minus_1_date,
            "original_price_cents": original_price,
            "quantity": 14,
        }

        response = client.post("/v1/markdown/evaluate", json=payload)
        assert response.status_code == 200
        data: Mapping[str, Any] = response.json()

        assert data["eligible"] is True
        assert data["discount_percentage"] == 30
        assert data["discounted_price_cents"] == 210  # 300 * 0.70 = 210
        assert data["status"] == "DISCOUNT_30"
        assert "evaluation_id" in data
        assert data["rule_applied"] != ""

    def test_us4_ac4_1_dynamic_markdown_t_minus_0_calculates_50_percent_discount(
        self, client: TestClient
    ) -> None:
        """[US-4][AC-4.1] Perishable product with expiry date T-0 calculates 50% markdown price."""
        today = datetime.now(UTC).date()
        t_minus_0_date = today.isoformat()
        original_price = 450  # 4.50 EUR

        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "sku_id": "SKU-SALAD-CHICKEN-02",
            "ean_barcode": "3560070654321",
            "lot_number": "LOT-2026-09-02",
            "expiry_date": t_minus_0_date,
            "original_price_cents": original_price,
            "quantity": 6,
        }

        response = client.post("/v1/markdown/evaluate", json=payload)
        assert response.status_code == 200
        data: Mapping[str, Any] = response.json()

        assert data["eligible"] is True
        assert data["discount_percentage"] == 50
        assert data["discounted_price_cents"] == 225  # 450 * 0.50 = 225
        assert data["status"] == "DISCOUNT_50"

    def test_us4_ac4_1_product_not_nearing_expiry_retains_standard_price(
        self, client: TestClient
    ) -> None:
        """[US-4][AC-4.1] Product with expiry date T-5 is not eligible for dynamic markdown and retains standard price."""
        today = datetime.now(UTC).date()
        t_minus_5_date = (today + timedelta(days=5)).isoformat()
        original_price = 500

        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "sku_id": "SKU-CHEESE-COMTE-03",
            "ean_barcode": "3560070987654",
            "lot_number": "LOT-2026-09-03",
            "expiry_date": t_minus_5_date,
            "original_price_cents": original_price,
            "quantity": 8,
        }

        response = client.post("/v1/markdown/evaluate", json=payload)
        assert response.status_code == 200
        data: Mapping[str, Any] = response.json()

        assert data["eligible"] is False
        assert data["discount_percentage"] == 0
        assert data["discounted_price_cents"] == original_price
        assert data["status"] == "STANDARD_PRICE"

    def test_us4_ac4_1_generates_escpos_thermal_print_command_within_latency_sla(
        self, client: TestClient
    ) -> None:
        """[US-4][AC-4.1] Generates ESC/POS print command for paired Bluetooth printer within 800ms SLA."""
        payload = {
            "request_id": str(uuid.uuid4()),
            "evaluation_id": "EVAL-2026-0915-001",
            "ean_barcode": "3560070123456",
            "discounted_price_cents": 210,
            "quantity": 14,
            "printer_id": "ZEBRA_BT_PRINTER_01",
        }

        start_time = time.perf_counter()
        response = client.post("/v1/markdown/print-label", json=payload)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        assert response.status_code == 200
        # WAF Performance NFR SLA: print command dispatched within 800ms
        assert elapsed_ms < 800.0, f"Print command generation took {elapsed_ms:.2f}ms, exceeding 800ms SLA"

        data: Mapping[str, Any] = response.json()
        assert "job_id" in data
        assert "promotional_barcode" in data
        assert len(data["promotional_barcode"]) >= 12
        assert "escpos_payload_base64" in data
        assert len(data["escpos_payload_base64"]) > 0
        assert data["labels_printed"] == 14

    # =========================================================================
    # User Story US-4 / AC-4.2: POS Feed Broadcast via Cloud Pub/Sub
    # =========================================================================

    def test_us4_ac4_2_publish_markdown_event_to_pos_pubsub_topic(
        self, client: TestClient
    ) -> None:
        """[US-4][AC-4.2] Published markdown sticker event is dispatched to Pub/Sub topic pos-markdown-updates for POS till sync."""
        valid_until = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "ean_barcode": "3560070123456",
            "promotional_barcode": "2901234521005",
            "discounted_price_cents": 210,
            "valid_until": valid_until,
        }

        response = client.post("/v1/markdown/pos-feed", json=payload)
        assert response.status_code == 201
        data: Mapping[str, Any] = response.json()

        assert "message_id" in data
        assert data["topic"] == "pos-markdown-updates"
        assert "published_at" in data

    def test_us4_ac4_2_pos_feed_rejects_missing_promotional_barcode_or_negative_price(
        self, client: TestClient
    ) -> None:
        """[US-4][AC-4.2] POS markdown feed publication fails with 400 Bad Request if barcode is missing or price is invalid."""
        invalid_payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "ean_barcode": "3560070123456",
            # missing promotional_barcode
            "discounted_price_cents": -50,  # invalid negative price
            "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        }

        response = client.post("/v1/markdown/pos-feed", json=invalid_payload)
        assert response.status_code == 400
        data: Mapping[str, Any] = response.json()
        assert "code" in data
        assert "message" in data

    def test_us4_ac4_2_pos_feed_rejects_expired_validity_window(
        self, client: TestClient
    ) -> None:
        """[US-4][AC-4.2] POS markdown feed publication rejects past valid_until timestamp with 422 Unprocessable Entity."""
        past_validity = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "ean_barcode": "3560070123456",
            "promotional_barcode": "2901234521005",
            "discounted_price_cents": 210,
            "valid_until": past_validity,
        }

        response = client.post("/v1/markdown/pos-feed", json=payload)
        assert response.status_code == 422
        data: Mapping[str, Any] = response.json()
        assert "code" in data

    # =========================================================================
    # User Story US-4 / AC-4.3: AGEC Charity Donations & Spoilage Write-Off
    # =========================================================================

    def test_us4_ac4_3_record_charity_donation_decrements_stock_and_generates_agec_fiscal_slip(
        self, client: TestClient
    ) -> None:
        """[US-4][AC-4.3] Unsold item at T+0 close logged for charity donation generates AGEC fiscal donation slip and decrements stock."""
        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "sku_id": "SKU-YOGURT-BIO-01",
            "lot_number": "LOT-2026-09-01",
            "action_type": "CHARITY_DONATION",
            "quantity": 8,
            "original_value_cents": 2400,
            "reason_code": "AGEC_DONATION_BANQUE_ALIMENTAIRE",
            "beneficiary_name": "Banques Alimentaires Ile-de-France",
        }

        response = client.post("/v1/markdown/donations", json=payload)
        assert response.status_code == 201
        data: Mapping[str, Any] = response.json()

        assert "record_id" in data
        assert "fiscal_slip_id" in data
        assert data["fiscal_slip_id"].startswith("SLIP-") or len(data["fiscal_slip_id"]) > 0
        assert data["action_type"] == "CHARITY_DONATION"
        assert data["stock_decremented"] is True
        assert "timestamp" in data

    def test_us4_ac4_3_record_bio_waste_spoilage_removal_decrements_stock_with_certificate(
        self, client: TestClient
    ) -> None:
        """[US-4][AC-4.3] Spoilage write-off at store close logs bio-waste removal certificate and decrements inventory."""
        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "sku_id": "SKU-FISH-SALMON-04",
            "lot_number": "LOT-2026-09-04",
            "action_type": "BIO_WASTE_REMOVAL",
            "quantity": 3,
            "original_value_cents": 2700,
            "reason_code": "AGEC_BIODECHET_METHANISATION",
        }

        response = client.post("/v1/markdown/donations", json=payload)
        assert response.status_code == 201
        data: Mapping[str, Any] = response.json()

        assert "record_id" in data
        assert "fiscal_slip_id" in data
        assert data["action_type"] == "BIO_WASTE_REMOVAL"
        assert data["stock_decremented"] is True

    def test_us4_ac4_3_donation_or_spoilage_rejects_zero_or_negative_quantity(
        self, client: TestClient
    ) -> None:
        """[US-4][AC-4.3] Donation or spoilage logging rejects zero or negative quantity with 400 Bad Request."""
        payload = {
            "request_id": str(uuid.uuid4()),
            "store_id": "STORE_FR_75015",
            "sku_id": "SKU-YOGURT-BIO-01",
            "lot_number": "LOT-2026-09-01",
            "action_type": "CHARITY_DONATION",
            "quantity": 0,  # invalid quantity
            "original_value_cents": 0,
            "reason_code": "AGEC_DONATION_BANQUE_ALIMENTAIRE",
        }

        response = client.post("/v1/markdown/donations", json=payload)
        assert response.status_code == 400
        data: Mapping[str, Any] = response.json()
        assert "code" in data
