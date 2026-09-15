"""In-memory repository adapter implementing the StockRepository domain port."""

from __future__ import annotations

from collections.abc import Sequence

from ..domain.models import AdjustmentRecord, StockItem, StockZone
from ..domain.repository import StockRepository


class InMemoryStockRepository(StockRepository):
    """Thread-safe in-memory datastore adapter implementing the StockRepository domain port."""

    def __init__(self) -> None:
        """Initialize empty collections for items, adjustments, and idempotency cache."""
        # store_id -> {(sku_id, zone): StockItem}
        self._items: dict[str, dict[tuple[str, StockZone], StockItem]] = {}
        # store_id -> {adjustment_id: AdjustmentRecord}
        self._adjustments: dict[str, dict[str, AdjustmentRecord]] = {}
        # set of seen idempotency keys
        self._idempotency_keys: set[str] = set()

    def seed_items(self, store_id: str, items: Sequence[StockItem]) -> None:
        """Helper to seed initial inventory for tests and demonstrations.

        Args:
            store_id: Identifier of the store tenant.
            items: Sequence of StockItem instances to register.
        """
        store_map = self._items.setdefault(store_id, {})
        for item in items:
            store_map[(item.sku_id, item.zone)] = item

    def get_stock(
        self,
        store_id: str,
        department_id: str,
        zone: StockZone | None = None,
    ) -> list[StockItem]:
        """Retrieve stock items matching store, department, and optional zone filter.

        Args:
            store_id: Identifier of the store tenant.
            department_id: Department category code.
            zone: Optional sub-zone location filter.

        Returns:
            List of matching StockItem records.
        """
        store_map = self._items.get(store_id, {})
        results: list[StockItem] = []
        for item in store_map.values():
            if item.department_id != department_id:
                continue
            if zone is not None and item.zone != zone:
                continue
            results.append(item)
        return results

    def get_stock_item(
        self,
        store_id: str,
        sku_id: str,
        zone: StockZone,
    ) -> StockItem | None:
        """Retrieve a specific SKU balance at a specific zone.

        Args:
            store_id: Identifier of the store tenant.
            sku_id: Product SKU identifier.
            zone: Sub-zone location.

        Returns:
            The StockItem if found, None otherwise.
        """
        return self._items.get(store_id, {}).get((sku_id, zone))

    def get_stock_item_by_ean(
        self,
        store_id: str,
        ean13: str,
        zone: StockZone,
    ) -> StockItem | None:
        """Retrieve a specific SKU balance by EAN13 barcode at a specific zone.

        Args:
            store_id: Identifier of the store tenant.
            ean13: EAN-13 barcode string.
            zone: Sub-zone location.

        Returns:
            The StockItem if found, None otherwise.
        """
        store_map = self._items.get(store_id, {})
        for item in store_map.values():
            if item.ean13 == ean13 and item.zone == zone:
                return item
        return None

    def update_stock_quantity(
        self,
        store_id: str,
        sku_id: str,
        zone: StockZone,
        quantity_delta: int,
    ) -> StockItem:
        """Apply a quantity delta to an existing stock balance.

        Args:
            store_id: Identifier of the store tenant.
            sku_id: Product SKU identifier.
            zone: Sub-zone location.
            quantity_delta: Positive or negative delta.

        Returns:
            The updated StockItem record.

        Raises:
            KeyError: If the stock item does not exist in the store/zone.
        """
        store_map = self._items.setdefault(store_id, {})
        key = (sku_id, zone)
        existing = store_map.get(key)
        if existing is None:
            raise KeyError(
                f"Stock item SKU '{sku_id}' not found in store '{store_id}' zone '{zone.value}'."
            )

        new_quantity = existing.quantity + quantity_delta
        updated = StockItem(
            sku_id=existing.sku_id,
            ean13=existing.ean13,
            product_name=existing.product_name,
            department_id=existing.department_id,
            zone=existing.zone,
            quantity=new_quantity,
            unit_price_cents=existing.unit_price_cents,
        )
        store_map[key] = updated
        return updated

    def save_adjustment(self, record: AdjustmentRecord) -> AdjustmentRecord:
        """Persist a newly created stock adjustment record.

        Args:
            record: AdjustmentRecord entity to store.

        Returns:
            The persisted AdjustmentRecord.
        """
        store_adj = self._adjustments.setdefault(record.store_id, {})
        store_adj[record.adjustment_id] = record
        return record

    def get_adjustment(
        self,
        store_id: str,
        adjustment_id: str,
    ) -> AdjustmentRecord | None:
        """Retrieve an adjustment record by store and adjustment ID.

        Args:
            store_id: Identifier of the store tenant.
            adjustment_id: Unique adjustment identifier.

        Returns:
            The AdjustmentRecord if found, None otherwise.
        """
        return self._adjustments.get(store_id, {}).get(adjustment_id)

    def update_adjustment(self, record: AdjustmentRecord) -> AdjustmentRecord:
        """Update an existing adjustment record.

        Args:
            record: Updated AdjustmentRecord entity.

        Returns:
            The updated AdjustmentRecord.
        """
        store_adj = self._adjustments.setdefault(record.store_id, {})
        store_adj[record.adjustment_id] = record
        return record

    def check_and_set_idempotency(self, key: str) -> bool:
        """Atomically verify and register an idempotency key.

        Args:
            key: Unique idempotency key token.

        Returns:
            True if the key is new and registered, False if already present (replay).
        """
        if key in self._idempotency_keys:
            return False
        self._idempotency_keys.add(key)
        return True
