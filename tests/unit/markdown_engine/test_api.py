"""Unit tests for FastAPI entrypoints in markdown_engine.

Traceability:
- [US-4][AC-4.1]: POST /v1/markdown/evaluate and POST /v1/markdown/print-label.
- [US-4][AC-4.2]: POST /v1/markdown/pos-feed.
- [US-4][AC-4.3]: POST /v1/markdown/donations.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.modules.markdown_engine.entrypoints.api import app


@pytest.fixture
def client() -> TestClient:
    """Fixture providing FastAPI test client."""
    return TestClient(app, raise_server_exceptions=False)


def test_evaluate_endpoint_happy_path(client: TestClient) -> None:
    """[US-4][AC-4.1] Evaluate markdown dynamic pricing."""
    today = datetime.now(UTC).date()
    expiry_tomorrow = (today + timedelta(days=1)).isoformat()
    payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": "STORE_FR_75015",
        "sku_id": "SKU-YOGURT-BIO-01",
        "ean_barcode": "3560070123456",
        "lot_number": "LOT-2026-09-A",
        "expiry_date": expiry_tomorrow,
        "original_price_cents": 350,
        "quantity": 10,
    }
    response = client.post("/v1/markdown/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["eligible"] is True
    assert data["discount_percentage"] == 30
    assert data["discounted_price_cents"] == 245
    assert data["status"] == "DISCOUNT_30"


def test_evaluate_endpoint_validation_error(client: TestClient) -> None:
    """[US-4][AC-4.1] Missing fields return 400."""
    response = client.post("/v1/markdown/evaluate", json={"quantity": 5})
    assert response.status_code == 400
    data = response.json()
    assert "code" in data
    assert "message" in data


def test_evaluate_endpoint_expired_error(client: TestClient) -> None:
    """[US-4][AC-4.3] Expired product returns 422."""
    payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": "STORE_FR_75015",
        "sku_id": "SKU-YOGURT-BIO-01",
        "ean_barcode": "3560070123456",
        "lot_number": "LOT-2026-09-A",
        "expiry_date": "2020-01-01",
        "original_price_cents": 350,
        "quantity": 10,
    }
    response = client.post("/v1/markdown/evaluate", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "ITEM_EXPIRED_DONATION_REQUIRED"


def test_evaluate_endpoint_fault_simulation(client: TestClient) -> None:
    """[US-4] X-Simulate-Fault header triggers 500 without leaking stack trace."""
    payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": "STORE_FR_75015",
        "sku_id": "SKU-YOGURT-BIO-01",
        "ean_barcode": "3560070123456",
        "lot_number": "LOT-2026-09-A",
        "expiry_date": "2026-09-20",
        "original_price_cents": 350,
        "quantity": 10,
    }
    response = client.post(
        "/v1/markdown/evaluate",
        headers={"X-Simulate-Fault": "DATASTORE_DISCONNECTED"},
        json=payload,
    )
    assert response.status_code == 500
    data = response.json()
    assert data["code"] == "INTERNAL_ERROR"
    assert "Traceback" not in response.text


def test_evaluate_endpoint_unexpected_runtime_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[US-4] Unexpected non-domain exception is caught by unhandled_exception_handler returning 500."""
    import src.modules.markdown_engine.entrypoints.api as api_mod

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Unexpected boom")

    monkeypatch.setattr(api_mod._engine, "evaluate", _boom)

    payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": "STORE_FR_75015",
        "sku_id": "SKU-YOGURT-BIO-01",
        "ean_barcode": "3560070123456",
        "lot_number": "LOT-2026-09-A",
        "expiry_date": "2026-09-20",
        "original_price_cents": 350,
        "quantity": 10,
    }
    response = client.post("/v1/markdown/evaluate", json=payload)
    assert response.status_code == 500
    data = response.json()
    assert data["code"] == "INTERNAL_ERROR"
    assert "Traceback" not in response.text


def test_print_label_endpoint_happy_path(client: TestClient) -> None:
    """[US-4][AC-4.1] Print label command generation."""
    payload = {
        "request_id": str(uuid.uuid4()),
        "evaluation_id": "EVAL-001",
        "ean_barcode": "3560070123456",
        "discounted_price_cents": 245,
        "quantity": 12,
        "printer_id": "PRINTER_ZEBRA_BT_01",
    }
    response = client.post("/v1/markdown/print-label", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["labels_printed"] == 12
    assert "promotional_barcode" in data
    assert "escpos_payload_base64" in data


def test_print_label_endpoint_business_violation_422(client: TestClient) -> None:
    """[US-4][AC-4.1] Unauthorized printer returns 422."""
    payload = {
        "request_id": str(uuid.uuid4()),
        "evaluation_id": "EVAL-001",
        "ean_barcode": "3560070123456",
        "discounted_price_cents": 245,
        "quantity": 12,
        "printer_id": "UNAUTHORIZED_OFFLINE_PRINTER",
    }
    response = client.post("/v1/markdown/print-label", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "code" in data


def test_print_label_endpoint_fault_simulation(client: TestClient) -> None:
    """[US-4] Printer fault simulation triggers 500."""
    payload = {
        "request_id": str(uuid.uuid4()),
        "evaluation_id": "EVAL-001",
        "ean_barcode": "3560070123456",
        "discounted_price_cents": 245,
        "quantity": 12,
        "printer_id": "PRINTER_ZEBRA_BT_01",
    }
    response = client.post(
        "/v1/markdown/print-label",
        headers={"X-Simulate-Fault": "PRINTER_SUBSYSTEM_ERROR"},
        json=payload,
    )
    assert response.status_code == 500
    assert "Traceback" not in response.text


def test_pos_feed_endpoint_happy_path(client: TestClient) -> None:
    """[US-4][AC-4.2] Publish to POS feed."""
    valid_until = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": "STORE_FR_75015",
        "ean_barcode": "3560070123456",
        "promotional_barcode": "2901234524508",
        "discounted_price_cents": 245,
        "valid_until": valid_until,
    }
    response = client.post("/v1/markdown/pos-feed", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["topic"] == "pos-markdown-updates"
    assert "message_id" in data


def test_pos_feed_endpoint_past_validity_422(client: TestClient) -> None:
    """[US-4][AC-4.2] Expired valid_until returns 422."""
    payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": "STORE_FR_75015",
        "ean_barcode": "3560070123456",
        "promotional_barcode": "2901234524508",
        "discounted_price_cents": 245,
        "valid_until": "2020-01-01T00:00:00Z",
    }
    response = client.post("/v1/markdown/pos-feed", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "code" in data


def test_pos_feed_endpoint_fault_simulation(client: TestClient) -> None:
    """[US-4][AC-4.2] PubSub fault triggers 500."""
    valid_until = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": "STORE_FR_75015",
        "ean_barcode": "3560070123456",
        "promotional_barcode": "2901234524508",
        "discounted_price_cents": 245,
        "valid_until": valid_until,
    }
    response = client.post(
        "/v1/markdown/pos-feed",
        headers={"X-Simulate-Fault": "PUBSUB_UNAVAILABLE"},
        json=payload,
    )
    assert response.status_code == 500
    assert "Traceback" not in response.text


def test_donations_endpoint_happy_path(client: TestClient) -> None:
    """[US-4][AC-4.3] Record charity donation with AGEC fiscal slip."""
    payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": "STORE_FR_75015",
        "sku_id": "SKU-YOGURT-BIO-01",
        "lot_number": "LOT-2026-09-A",
        "action_type": "CHARITY_DONATION",
        "quantity": 10,
        "original_value_cents": 3500,
        "reason_code": "AGEC_DONATION_BANQUE_ALIMENTAIRE",
        "beneficiary_name": "Banques Alimentaires",
    }
    response = client.post("/v1/markdown/donations", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["stock_decremented"] is True
    assert "fiscal_slip_id" in data
    assert data["action_type"] == "CHARITY_DONATION"


def test_donations_endpoint_business_violation_422(client: TestClient) -> None:
    """[US-4][AC-4.3] Invalid action type returns 422."""
    payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": "STORE_FR_75015",
        "sku_id": "SKU-YOGURT-BIO-01",
        "lot_number": "LOT-2026-09-A",
        "action_type": "INVALID_ACTION_TYPE",
        "quantity": 10,
        "original_value_cents": 3500,
        "reason_code": "AGEC_DONATION_BANQUE_ALIMENTAIRE",
    }
    response = client.post("/v1/markdown/donations", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "code" in data


def test_donations_endpoint_fault_simulation(client: TestClient) -> None:
    """[US-4][AC-4.3] Datastore fault triggers 500."""
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
    response = client.post(
        "/v1/markdown/donations",
        headers={"X-Simulate-Fault": "BIGQUERY_AUDIT_ERROR"},
        json=payload,
    )
    assert response.status_code == 500
    assert "Traceback" not in response.text
