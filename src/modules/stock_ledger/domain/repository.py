"""Domain repository port interface for stock persistence."""

from __future__ import annotations

import abc

from .models import AdjustmentRecord, StockItem, StockZone


class StockRepository(abc.ABC):
    """Abstract domain port for stock ledger datastore access."""

    @abc.abstractmethod
    def get_stock(
        self,
        store_id: str,
        department_id: str,
        zone: StockZone | None = None,
    ) -> list[StockItem]:
        """Retrieve stock items for a given store, department, and optional zone filter.

        Args:
            store_id: Identifier of the store tenant.
            department_id: Department category code.
            zone: Optional sub-zone location filter.

        Returns:
            List of matching StockItem records.
        """
        ...

    @abc.abstractmethod
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
        ...

    @abc.abstractmethod
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
        ...

    @abc.abstractmethod
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
        """
        ...

    @abc.abstractmethod
    def save_adjustment(self, record: AdjustmentRecord) -> AdjustmentRecord:
        """Persist a newly created stock adjustment record.

        Args:
            record: AdjustmentRecord entity to store.

        Returns:
            The persisted AdjustmentRecord.
        """
        ...

    @abc.abstractmethod
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
        ...

    @abc.abstractmethod
    def update_adjustment(self, record: AdjustmentRecord) -> AdjustmentRecord:
        """Update an existing adjustment record (e.g. upon sign-off).

        Args:
            record: Updated AdjustmentRecord entity.

        Returns:
            The updated AdjustmentRecord.
        """
        ...

    @abc.abstractmethod
    def check_and_set_idempotency(self, key: str) -> bool:
        """Atomically verify and register an idempotency key.

        Args:
            key: Unique idempotency key token.

        Returns:
            True if the key is new and registered, False if already present (replay).
        """
        ...
