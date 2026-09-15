"""Unit tests for stock_ledger public FastAPI entrypoints."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from starlette.testclient import TestClient

from src.modules.stock_ledger.adapters.memory_repository import InMemoryStockRepository
from src.modules.stock_ledger.domain.models import (
    AdjustmentRecord,
    AdjustmentStatus,
    ReasonCode,
    StockItem,
    StockZone,
)
from src.modules.stock_ledger.entrypoints.api import app, get_repository


@pytest.fixture
def repo() -> InMemoryStockRepository:
    """Fixture providing a fresh in-memory repository."""
    repository = InMemoryStockRepository()
    # Seed items for tests
    item1 = StockItem(
        sku_id="SKU-FRAIS-101",
        ean13="3560070123456",
        product_name="Carrefour Lait Demi-Écrémé 1L",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity=50,
        unit_price_cents=115,
    )
    item2 = StockItem(
        sku_id="SKU-EPICERIE-404",
        ean13="3560070999999",
        product_name="Carrefour Pâtes Penne 500g",
        department_id="RAYON_EPICERIE",
        zone=StockZone.DRY_RESERVE,
        quantity=100,
        unit_price_cents=95,
    )
    repository.seed_items("STORE_FR_75015", [item1, item2])
    return repository


@pytest.fixture
def client(repo: InMemoryStockRepository) -> Generator[TestClient, None, None]:
    """Fixture providing TestClient with overridden repository dependency."""
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_list_department_stock_200(client: TestClient) -> None:
    """[US-1][AC-1.1] Query stock in assigned department returns 200 OK."""
    headers = {
        "X-User-Role": "CHEF_DE_RAYON",
        "X-User-Departments": "RAYON_FRAIS,RAYON_BOISSONS",
    }
    resp = client.get(
        "/v1/stores/STORE_FR_75015/stock?department_id=RAYON_FRAIS",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["store_id"] == "STORE_FR_75015"
    assert data["department_id"] == "RAYON_FRAIS"
    assert data["total_items"] == 1
    assert data["items"][0]["sku_id"] == "SKU-FRAIS-101"


def test_list_department_stock_with_zone_filter(client: TestClient) -> None:
    """[US-1][AC-1.1] Query stock filtered by zone returns matching items."""
    headers = {
        "X-User-Role": "CHEF_DE_RAYON",
        "X-User-Departments": "RAYON_FRAIS",
    }
    resp = client.get(
        "/v1/stores/STORE_FR_75015/stock?department_id=RAYON_FRAIS&zone=SALES_FLOOR_FACING",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["total_items"] == 1

    resp_empty = client.get(
        "/v1/stores/STORE_FR_75015/stock?department_id=RAYON_FRAIS&zone=COLD_STORAGE_RESERVE",
        headers=headers,
    )
    assert resp_empty.status_code == 200
    assert resp_empty.json()["total_items"] == 0


def test_list_department_stock_missing_department_400(client: TestClient) -> None:
    """[US-1][AC-1.1] Missing department_id returns 400 Bad Request."""
    resp = client.get("/v1/stores/STORE_FR_75015/stock")
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_PAYLOAD"


def test_list_department_stock_out_of_scope_403(client: TestClient) -> None:
    """[US-1][AC-1.2] Querying department outside authorized claims returns 403 Forbidden."""
    headers = {
        "X-User-Role": "CHEF_DE_RAYON",
        "X-User-Departments": "RAYON_FRAIS",
    }
    resp = client.get(
        "/v1/stores/STORE_FR_75015/stock?department_id=RAYON_EPICERIE",
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "ERR_OUT_OF_SCOPE_DEPARTMENT"


def test_submit_adjustment_auto_approved_200(client: TestClient) -> None:
    """[US-2][AC-2.1] Negative adjustment < €500 is auto-approved with 200 OK and deducts stock."""
    payload = {
        "sku_id": "SKU-FRAIS-101",
        "department_id": "RAYON_FRAIS",
        "zone": "SALES_FLOOR_FACING",
        "quantity_delta": -5,
        "unit_price_cents": 115,
        "reason_code": "BREAKAGE",
        "initiator_id": "chef@carrefour.com",
        "initiator_role": "CHEF_DE_RAYON",
        "user_departments": ["RAYON_FRAIS"],
    }
    headers = {"Idempotency-Key": "550e8400-e29b-41d4-a716-446655440001"}
    resp = client.post(
        "/v1/stores/STORE_FR_75015/adjustments",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "AUTO_APPROVED"
    assert data["total_value_cents"] == 575

    # Check stock was updated
    stock_resp = client.get(
        "/v1/stores/STORE_FR_75015/stock?department_id=RAYON_FRAIS",
        headers={"X-User-Role": "CHEF_DE_RAYON", "X-User-Departments": "RAYON_FRAIS"},
    )
    assert stock_resp.json()["items"][0]["quantity"] == 45


def test_submit_adjustment_high_value_202(
    client: TestClient, repo: InMemoryStockRepository
) -> None:
    """[US-2][AC-2.1] Negative adjustment >= €500 returns 202 Accepted and leaves stock intact."""
    # Seed high unit cost item: 10 units at €55.00 each
    repo.seed_items(
        "STORE_FR_75015",
        [
            StockItem(
                sku_id="SKU-CHAMPAGNE",
                ean13="3560070555555",
                product_name="Champagne Dom",
                department_id="RAYON_FRAIS",
                zone=StockZone.SALES_FLOOR_FACING,
                quantity=20,
                unit_price_cents=5500,
            )
        ],
    )
    payload = {
        "sku_id": "SKU-CHAMPAGNE",
        "department_id": "RAYON_FRAIS",
        "zone": "SALES_FLOOR_FACING",
        "quantity_delta": -10,
        "unit_price_cents": 5500,  # 10 * 5500 = 55000 cents (€550)
        "reason_code": "THEFT",
        "initiator_id": "chef@carrefour.com",
        "initiator_role": "CHEF_DE_RAYON",
        "user_departments": ["RAYON_FRAIS"],
    }
    headers = {"Idempotency-Key": "550e8400-e29b-41d4-a716-446655440002"}
    resp = client.post(
        "/v1/stores/STORE_FR_75015/adjustments",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "PENDING_DIRECTOR_APPROVAL"
    assert data["total_value_cents"] == 55000

    # Stock balance must remain 20 (not deducted yet)
    item = repo.get_stock_item(
        "STORE_FR_75015", "SKU-CHAMPAGNE", StockZone.SALES_FLOOR_FACING
    )
    assert item is not None
    assert item.quantity == 20


def test_submit_adjustment_out_of_scope_403(client: TestClient) -> None:
    """[US-1][AC-1.2] Adjustment with mismatched user_departments returns 403 Forbidden."""
    payload = {
        "sku_id": "SKU-EPICERIE-404",
        "department_id": "RAYON_EPICERIE",
        "zone": "DRY_RESERVE",
        "quantity_delta": -5,
        "unit_price_cents": 95,
        "reason_code": "BREAKAGE",
        "initiator_id": "chef@carrefour.com",
        "initiator_role": "CHEF_DE_RAYON",
        "user_departments": ["RAYON_FRAIS"],
    }
    headers = {"Idempotency-Key": "550e8400-e29b-41d4-a716-446655440003"}
    resp = client.post(
        "/v1/stores/STORE_FR_75015/adjustments",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "ERR_OUT_OF_SCOPE_DEPARTMENT"


def test_submit_adjustment_insufficient_stock_422(client: TestClient) -> None:
    """[US-1][AC-1.2] Negative adjustment exceeding available stock returns 422 Unprocessable."""
    payload = {
        "sku_id": "SKU-FRAIS-101",
        "department_id": "RAYON_FRAIS",
        "zone": "SALES_FLOOR_FACING",
        "quantity_delta": -100,  # only 50 available
        "unit_price_cents": 115,
        "reason_code": "THEFT",
        "initiator_id": "chef@carrefour.com",
        "initiator_role": "CHEF_DE_RAYON",
        "user_departments": ["RAYON_FRAIS"],
    }
    headers = {"Idempotency-Key": "550e8400-e29b-41d4-a716-446655440004"}
    resp = client.post(
        "/v1/stores/STORE_FR_75015/adjustments",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "ERR_INSUFFICIENT_STOCK"


def test_submit_adjustment_malformed_payload_400(client: TestClient) -> None:
    """[US-1][AC-1.2] Missing required fields returns 400 Bad Request."""
    headers = {"Idempotency-Key": "550e8400-e29b-41d4-a716-446655440005"}
    resp = client.post(
        "/v1/stores/STORE_FR_75015/adjustments",
        json={"sku_id": "SKU-1"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_PAYLOAD"


def test_sign_off_approve_200(
    client: TestClient, repo: InMemoryStockRepository
) -> None:
    """[US-2][AC-2.2] Store Director approval commits adjustment and deducts stock."""
    # Seed pending adjustment and item
    repo.seed_items(
        "STORE_FR_75015",
        [
            StockItem(
                sku_id="SKU-CHAMPAGNE",
                ean13="3560070555555",
                product_name="Champagne Dom",
                department_id="RAYON_FRAIS",
                zone=StockZone.SALES_FLOOR_FACING,
                quantity=20,
                unit_price_cents=5500,
            )
        ],
    )
    repo.save_adjustment(
        AdjustmentRecord(
            adjustment_id="adj-direct-001",
            store_id="STORE_FR_75015",
            sku_id="SKU-CHAMPAGNE",
            department_id="RAYON_FRAIS",
            zone=StockZone.SALES_FLOOR_FACING,
            quantity_delta=-10,
            unit_price_cents=5500,
            total_value_cents=55000,
            reason_code=ReasonCode.THEFT,
            initiator_id="chef@carrefour.com",
            status=AdjustmentStatus.PENDING_DIRECTOR_APPROVAL,
        )
    )

    headers = {"X-User-Role": "DIRECTEUR_MAGASIN"}
    payload = {
        "director_id": "directeur@carrefour.com",
        "action": "APPROVE",
        "note": "Approved after stockroom check",
    }
    resp = client.post(
        "/v1/stores/STORE_FR_75015/adjustments/adj-direct-001/sign-off",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"

    # Verify stock deducted
    item = repo.get_stock_item(
        "STORE_FR_75015", "SKU-CHAMPAGNE", StockZone.SALES_FLOOR_FACING
    )
    assert item is not None
    assert item.quantity == 10


def test_sign_off_reject_200_and_missing_note_400(
    client: TestClient, repo: InMemoryStockRepository
) -> None:
    """[US-2][AC-2.3] Store Director rejection requires note and leaves stock untouched."""
    repo.save_adjustment(
        AdjustmentRecord(
            adjustment_id="adj-direct-002",
            store_id="STORE_FR_75015",
            sku_id="SKU-FRAIS-101",
            department_id="RAYON_FRAIS",
            zone=StockZone.SALES_FLOOR_FACING,
            quantity_delta=-10,
            unit_price_cents=115,
            total_value_cents=1150,
            reason_code=ReasonCode.BREAKAGE,
            initiator_id="chef@carrefour.com",
            status=AdjustmentStatus.PENDING_DIRECTOR_APPROVAL,
        )
    )
    headers = {"X-User-Role": "DIRECTEUR_MAGASIN"}

    # Rejection without note -> 400
    resp_no_note = client.post(
        "/v1/stores/STORE_FR_75015/adjustments/adj-direct-002/sign-off",
        json={"director_id": "directeur@carrefour.com", "action": "REJECT"},
        headers=headers,
    )
    assert resp_no_note.status_code == 400

    # Rejection with note -> 200
    resp_reject = client.post(
        "/v1/stores/STORE_FR_75015/adjustments/adj-direct-002/sign-off",
        json={
            "director_id": "directeur@carrefour.com",
            "action": "REJECT",
            "note": "False count.",
        },
        headers=headers,
    )
    assert resp_reject.status_code == 200
    assert resp_reject.json()["status"] == "REJECTED"


def test_sign_off_non_director_403(
    client: TestClient, repo: InMemoryStockRepository
) -> None:
    """[US-2][AC-2.2] Non-director role claim returns 403 Forbidden."""
    repo.save_adjustment(
        AdjustmentRecord(
            adjustment_id="adj-direct-003",
            store_id="STORE_FR_75015",
            sku_id="SKU-FRAIS-101",
            department_id="RAYON_FRAIS",
            zone=StockZone.SALES_FLOOR_FACING,
            quantity_delta=-10,
            unit_price_cents=115,
            total_value_cents=1150,
            reason_code=ReasonCode.BREAKAGE,
            initiator_id="chef@carrefour.com",
            status=AdjustmentStatus.PENDING_DIRECTOR_APPROVAL,
        )
    )
    headers = {"X-User-Role": "CHEF_DE_RAYON"}
    resp = client.post(
        "/v1/stores/STORE_FR_75015/adjustments/adj-direct-003/sign-off",
        json={"director_id": "chef@carrefour.com", "action": "APPROVE"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "ERR_UNAUTHORIZED_DIRECTOR"


def test_sign_off_not_found_404(client: TestClient) -> None:
    """[US-2][AC-2.2] Non-existent adjustment returns 404 Not Found."""
    headers = {"X-User-Role": "DIRECTEUR_MAGASIN"}
    resp = client.post(
        "/v1/stores/STORE_FR_75015/adjustments/nonexistent/sign-off",
        json={"director_id": "directeur@carrefour.com", "action": "APPROVE"},
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "ADJUSTMENT_NOT_FOUND"


def test_sign_off_conflict_409(
    client: TestClient, repo: InMemoryStockRepository
) -> None:
    """[US-2][AC-2.2] Adjustment not in PENDING state returns 409 Conflict."""
    repo.save_adjustment(
        AdjustmentRecord(
            adjustment_id="adj-direct-004",
            store_id="STORE_FR_75015",
            sku_id="SKU-FRAIS-101",
            department_id="RAYON_FRAIS",
            zone=StockZone.SALES_FLOOR_FACING,
            quantity_delta=-10,
            unit_price_cents=115,
            total_value_cents=1150,
            reason_code=ReasonCode.BREAKAGE,
            initiator_id="chef@carrefour.com",
            status=AdjustmentStatus.APPROVED,
        )
    )
    headers = {"X-User-Role": "DIRECTEUR_MAGASIN"}
    resp = client.post(
        "/v1/stores/STORE_FR_75015/adjustments/adj-direct-004/sign-off",
        json={"director_id": "directeur@carrefour.com", "action": "APPROVE"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "STATE_CONFLICT"


def test_execute_internal_transfer_to_existing_zone_200(
    client: TestClient, repo: InMemoryStockRepository
) -> None:
    """[US-1][AC-1.1] Move stock to existing target zone updates balances and returns 200 OK."""
    # Seed SKU-EPICERIE-404 in target zone SALES_FLOOR_FACING
    target_item = StockItem(
        sku_id="SKU-EPICERIE-404",
        ean13="3560070999999",
        product_name="Carrefour Pâtes Penne 500g",
        department_id="RAYON_EPICERIE",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity=10,
        unit_price_cents=95,
    )
    repo.seed_items("STORE_FR_75015", [target_item])

    headers = {
        "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440010-b",
        "X-User-Departments": "RAYON_EPICERIE",
    }
    payload = {
        "sku_id": "SKU-EPICERIE-404",
        "department_id": "RAYON_EPICERIE",
        "source_zone": "DRY_RESERVE",
        "target_zone": "SALES_FLOOR_FACING",
        "quantity": 25,
        "operator_id": "els_jean@carrefour.com",
    }
    resp = client.post(
        "/v1/stores/STORE_FR_75015/transfers",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMMITTED"


def test_execute_internal_transfer_200(client: TestClient) -> None:
    """[US-1][AC-1.1] Move stock between zones updates balances and returns 200 OK."""
    headers = {
        "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440010",
        "X-User-Departments": "RAYON_EPICERIE",
    }
    payload = {
        "sku_id": "SKU-EPICERIE-404",
        "department_id": "RAYON_EPICERIE",
        "source_zone": "DRY_RESERVE",
        "target_zone": "SALES_FLOOR_FACING",
        "quantity": 25,
        "operator_id": "els_jean@carrefour.com",
    }
    resp = client.post(
        "/v1/stores/STORE_FR_75015/transfers",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMMITTED"

    # Verify idempotency cache hit
    resp2 = client.post(
        "/v1/stores/STORE_FR_75015/transfers",
        json=payload,
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "COMMITTED"
    assert resp2.json()["transfer_id"] == resp.json()["transfer_id"]


def test_execute_internal_transfer_insufficient_stock_422(client: TestClient) -> None:
    """[US-1][AC-1.1] Transfer exceeding source zone stock returns 422 Unprocessable."""
    headers = {
        "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440011",
        "X-User-Departments": "RAYON_EPICERIE",
    }
    payload = {
        "sku_id": "SKU-EPICERIE-404",
        "department_id": "RAYON_EPICERIE",
        "source_zone": "DRY_RESERVE",
        "target_zone": "SALES_FLOOR_FACING",
        "quantity": 999,  # exceeds 100 available
        "operator_id": "els_jean@carrefour.com",
    }
    resp = client.post(
        "/v1/stores/STORE_FR_75015/transfers",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "ERR_INSUFFICIENT_STOCK"


def test_execute_internal_transfer_department_mismatch_403(client: TestClient) -> None:
    """[US-1][AC-1.2] Transfer in department not authorized on user header returns 403 Forbidden."""
    headers = {
        "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440012",
        "X-User-Departments": "RAYON_FRAIS",
    }
    payload = {
        "sku_id": "SKU-EPICERIE-404",
        "department_id": "RAYON_EPICERIE",
        "source_zone": "DRY_RESERVE",
        "target_zone": "SALES_FLOOR_FACING",
        "quantity": 10,
        "operator_id": "els_jean@carrefour.com",
    }
    resp = client.post(
        "/v1/stores/STORE_FR_75015/transfers",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "ERR_OUT_OF_SCOPE_DEPARTMENT"


def test_execute_internal_transfer_malformed_payload_400(client: TestClient) -> None:
    """[US-1][AC-1.1] Transfer with invalid or missing fields returns 400 Bad Request."""
    headers = {"Idempotency-Key": "550e8400-e29b-41d4-a716-446655440013"}
    resp = client.post(
        "/v1/stores/STORE_FR_75015/transfers",
        json={"sku_id": "SKU-1"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_PAYLOAD"


def test_ingest_pos_depletion_200(client: TestClient) -> None:
    """[US-1][AC-1.1] Deplete sales floor inventory for basket items returns 200 OK."""
    headers = {"Idempotency-Key": "till-receipt-001"}
    payload = {
        "receipt_id": "REC-20260915-00129",
        "till_id": "TILL-04",
        "timestamp": "2026-09-15T11:45:00Z",
        "items": [
            {"ean13": "3560070123456", "quantity": 2},
        ],
    }
    resp = client.post(
        "/v1/stores/STORE_FR_75015/pos-depletions",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "DEPLETED"
    assert resp.json()["processed_items"] == 1


def test_ingest_pos_depletion_unknown_sku_422(client: TestClient) -> None:
    """[US-1][AC-1.1] POS depletion for unmapped barcode returns 422 Unprocessable."""
    headers = {"Idempotency-Key": "till-receipt-002"}
    payload = {
        "receipt_id": "REC-20260915-00130",
        "till_id": "TILL-04",
        "timestamp": "2026-09-15T11:45:00Z",
        "items": [
            {"ean13": "9999999999999", "quantity": 1},
        ],
    }
    resp = client.post(
        "/v1/stores/STORE_FR_75015/pos-depletions",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "UNPROCESSABLE_ITEM"


def test_ingest_pos_depletion_malformed_400(client: TestClient) -> None:
    """[US-1][AC-1.1] POS depletion with malformed payload returns 400 Bad Request."""
    headers = {"Idempotency-Key": "till-receipt-003"}
    resp = client.post(
        "/v1/stores/STORE_FR_75015/pos-depletions",
        json={"receipt_id": "REC-01"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_PAYLOAD"


def test_idempotent_replay_returns_cached_or_accepted(client: TestClient) -> None:
    """[US-1][AC-1.3] Submitting same Idempotency-Key does not re-apply action."""
    payload = {
        "sku_id": "SKU-FRAIS-101",
        "department_id": "RAYON_FRAIS",
        "zone": "SALES_FLOOR_FACING",
        "quantity_delta": -2,
        "unit_price_cents": 115,
        "reason_code": "BREAKAGE",
        "initiator_id": "chef@carrefour.com",
        "initiator_role": "CHEF_DE_RAYON",
        "user_departments": ["RAYON_FRAIS"],
    }
    headers = {"Idempotency-Key": "550e8400-e29b-41d4-a716-446655440099"}
    resp1 = client.post(
        "/v1/stores/STORE_FR_75015/adjustments",
        json=payload,
        headers=headers,
    )
    assert resp1.status_code == 200

    # Replay
    resp2 = client.post(
        "/v1/stores/STORE_FR_75015/adjustments",
        json=payload,
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["adjustment_id"] == resp1.json()["adjustment_id"]


def test_custom_openapi_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify custom_openapi returns parsed schema and caches it."""
    from pathlib import Path

    from src.modules.stock_ledger.entrypoints.api import custom_openapi

    # 1. Clear cached schema
    app.openapi_schema = None
    schema = custom_openapi()
    assert isinstance(schema, dict)
    assert "openapi" in schema

    # 2. Subsequent call returns cached schema
    cached = custom_openapi()
    assert cached == schema

    # 3. Nonexistent file branch
    app.openapi_schema = None
    monkeypatch.setattr(Path, "exists", lambda self: False)
    assert custom_openapi() == {}
    app.openapi_schema = None


def test_default_get_repository() -> None:
    """Verify get_repository returns default singleton."""
    from src.modules.stock_ledger.entrypoints.api import _GLOBAL_REPO, get_repository

    assert get_repository() is _GLOBAL_REPO


def test_trigger_fault_handling() -> None:
    """Verify TRIGGER_FAULT returns 500 across endpoints."""
    # Test with un-overridden client
    with TestClient(app) as fault_client:
        # 1. list stock
        resp1 = fault_client.get(
            "/v1/stores/TRIGGER_FAULT/stock?department_id=RAYON_FRAIS",
            headers={"X-User-Role": "DIRECTEUR_MAGASIN"},
        )
        assert resp1.status_code == 500
        assert resp1.json()["code"] == "INTERNAL_ERROR"

        # 2. adjustments
        resp2 = fault_client.post(
            "/v1/stores/TRIGGER_FAULT/adjustments",
            json={
                "sku_id": "SKU-FRAIS-101",
                "department_id": "RAYON_FRAIS",
                "zone": "SALES_FLOOR_FACING",
                "quantity_delta": 1,
                "unit_price_cents": 100,
                "reason_code": "OTHER",
                "initiator_id": "chef@carrefour.com",
                "initiator_role": "CHEF_DE_RAYON",
                "user_departments": ["RAYON_FRAIS"],
            },
            headers={"Idempotency-Key": "fault-key-1"},
        )
        assert resp2.status_code == 500

        # 3. sign-off
        resp3 = fault_client.post(
            "/v1/stores/STORE_FR_75015/adjustments/adj-pending-001/sign-off",
            json={
                "director_id": "TRIGGER_FAULT",
                "action": "APPROVE",
            },
            headers={"X-User-Role": "DIRECTEUR_MAGASIN"},
        )
        assert resp3.status_code == 500

        # 4. transfers
        resp4 = fault_client.post(
            "/v1/stores/TRIGGER_FAULT/transfers",
            json={
                "sku_id": "SKU-FRAIS-101",
                "department_id": "RAYON_FRAIS",
                "source_zone": "SALES_FLOOR_FACING",
                "target_zone": "COLD_STORAGE_RESERVE",
                "quantity": 1,
                "operator_id": "op-1",
            },
            headers={"Idempotency-Key": "fault-key-2"},
        )
        assert resp4.status_code == 500

        # 5. pos-depletions
        resp5 = fault_client.post(
            "/v1/stores/TRIGGER_FAULT/pos-depletions",
            json={
                "receipt_id": "REC-FAULT",
                "till_id": "TILL-01",
                "timestamp": "2026-09-15T12:00:00Z",
                "items": [{"ean13": "3560070123456", "quantity": 1}],
            },
            headers={"Idempotency-Key": "fault-key-3"},
        )
        assert resp5.status_code == 500
