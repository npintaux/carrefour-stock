"""Tests for InMemoryStockRepository adapter."""

from __future__ import annotations

import pytest

from src.modules.stock_ledger.adapters.memory_repository import InMemoryStockRepository
from src.modules.stock_ledger.domain.models import (
    AdjustmentRecord,
    AdjustmentStatus,
    ReasonCode,
    StockItem,
    StockZone,
)


def test_seed_and_get_stock() -> None:
    """[US-1][AC-1.1] Retrieve seeded stock items partitioned by department and zone."""
    repo = InMemoryStockRepository()
    item1 = StockItem(
        sku_id="SKU-FRAIS-1",
        ean13="3560070123456",
        product_name="Milk",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity=50,
        unit_price_cents=120,
    )
    item2 = StockItem(
        sku_id="SKU-FRAIS-2",
        ean13="3560070123457",
        product_name="Butter",
        department_id="RAYON_FRAIS",
        zone=StockZone.COLD_STORAGE_RESERVE,
        quantity=20,
        unit_price_cents=250,
    )
    item3 = StockItem(
        sku_id="SKU-EPICERIE-1",
        ean13="3560070999999",
        product_name="Pasta",
        department_id="RAYON_EPICERIE",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity=100,
        unit_price_cents=90,
    )
    repo.seed_items("STORE_FR_75015", [item1, item2, item3])

    # Query only RAYON_FRAIS
    frais_items = repo.get_stock(store_id="STORE_FR_75015", department_id="RAYON_FRAIS")
    assert len(frais_items) == 2

    # Query RAYON_FRAIS filtered by zone
    cold_items = repo.get_stock(
        store_id="STORE_FR_75015",
        department_id="RAYON_FRAIS",
        zone=StockZone.COLD_STORAGE_RESERVE,
    )
    assert len(cold_items) == 1
    assert cold_items[0].sku_id == "SKU-FRAIS-2"


def test_get_stock_item_and_by_ean() -> None:
    """[US-1][AC-1.1] Look up specific items by SKU and EAN13 barcode."""
    repo = InMemoryStockRepository()
    item = StockItem(
        sku_id="SKU-FRAIS-1",
        ean13="3560070123456",
        product_name="Milk",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity=50,
        unit_price_cents=120,
    )
    repo.seed_items("STORE_FR_75015", [item])

    found_by_sku = repo.get_stock_item(
        "STORE_FR_75015", "SKU-FRAIS-1", StockZone.SALES_FLOOR_FACING
    )
    assert found_by_sku is not None
    assert found_by_sku.quantity == 50

    not_found_sku = repo.get_stock_item(
        "STORE_FR_75015", "SKU-NONEXISTENT", StockZone.SALES_FLOOR_FACING
    )
    assert not_found_sku is None

    found_by_ean = repo.get_stock_item_by_ean(
        "STORE_FR_75015", "3560070123456", StockZone.SALES_FLOOR_FACING
    )
    assert found_by_ean is not None
    assert found_by_ean.sku_id == "SKU-FRAIS-1"

    not_found_ean = repo.get_stock_item_by_ean(
        "STORE_FR_75015", "9999999999999", StockZone.SALES_FLOOR_FACING
    )
    assert not_found_ean is None


def test_update_stock_quantity() -> None:
    """[US-1][AC-1.2] Apply positive and negative quantity adjustments."""
    repo = InMemoryStockRepository()
    item = StockItem(
        sku_id="SKU-FRAIS-1",
        ean13="3560070123456",
        product_name="Milk",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity=50,
        unit_price_cents=120,
    )
    repo.seed_items("STORE_FR_75015", [item])

    updated = repo.update_stock_quantity(
        "STORE_FR_75015", "SKU-FRAIS-1", StockZone.SALES_FLOOR_FACING, -10
    )
    assert updated.quantity == 40

    updated_pos = repo.update_stock_quantity(
        "STORE_FR_75015", "SKU-FRAIS-1", StockZone.SALES_FLOOR_FACING, 15
    )
    assert updated_pos.quantity == 55


def test_update_stock_quantity_nonexistent_raises() -> None:
    """[US-1][AC-1.2] Updating non-existent item raises KeyError."""
    repo = InMemoryStockRepository()
    with pytest.raises(KeyError):
        repo.update_stock_quantity(
            "STORE_FR_75015", "SKU-NONE", StockZone.SALES_FLOOR_FACING, -5
        )


def test_save_get_and_update_adjustment() -> None:
    """[US-2][AC-2.1] Persist and update adjustment lifecycle records."""
    repo = InMemoryStockRepository()
    record = AdjustmentRecord(
        adjustment_id="adj-001",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=5500,
        total_value_cents=55000,
        reason_code=ReasonCode.THEFT,
        initiator_id="chef@carrefour.com",
        status=AdjustmentStatus.PENDING_DIRECTOR_APPROVAL,
    )
    saved = repo.save_adjustment(record)
    assert saved.adjustment_id == "adj-001"

    retrieved = repo.get_adjustment("STORE_FR_75015", "adj-001")
    assert retrieved is not None
    assert retrieved.status == AdjustmentStatus.PENDING_DIRECTOR_APPROVAL

    not_found = repo.get_adjustment("STORE_FR_75015", "adj-999")
    assert not_found is None

    # Update to APPROVED
    updated_rec = AdjustmentRecord(
        adjustment_id="adj-001",
        store_id="STORE_FR_75015",
        sku_id="SKU-FRAIS-1",
        department_id="RAYON_FRAIS",
        zone=StockZone.SALES_FLOOR_FACING,
        quantity_delta=-10,
        unit_price_cents=5500,
        total_value_cents=55000,
        reason_code=ReasonCode.THEFT,
        initiator_id="chef@carrefour.com",
        status=AdjustmentStatus.APPROVED,
        director_id="director@carrefour.com",
        director_note="Inspected and approved",
    )
    updated = repo.update_adjustment(updated_rec)
    assert updated.status == AdjustmentStatus.APPROVED
    assert updated.director_id == "director@carrefour.com"


def test_check_and_set_idempotency() -> None:
    """[US-1][AC-1.3] Idempotency keys are registered atomically."""
    repo = InMemoryStockRepository()
    assert repo.check_and_set_idempotency("key-1") is True
    assert repo.check_and_set_idempotency("key-1") is False
    assert repo.check_and_set_idempotency("key-2") is True
