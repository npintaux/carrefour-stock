"""Port definition for POS markdown Pub/Sub feed broadcast.

Traceability:
- [US-4][AC-4.2]: Real-time markdown broadcast port for checkout sync.
"""

from __future__ import annotations

import abc
from datetime import datetime

from ..models import PosFeedMessage


class PosPublisherPort(abc.ABC):
    """Abstract port for broadcasting markdown price updates to POS subscribers."""

    @abc.abstractmethod
    def publish_pos_markdown(
        self,
        request_id: str,
        store_id: str,
        ean_barcode: str,
        promotional_barcode: str,
        discounted_price_cents: int,
        valid_until: datetime,
    ) -> PosFeedMessage:
        """Broadcast promotional markdown pricing event.

        Args:
            request_id: Unique request identifier.
            store_id: Store identifier.
            ean_barcode: Standard product barcode.
            promotional_barcode: Markdown sticker barcode.
            discounted_price_cents: Markdown price in cents.
            valid_until: Validity expiration timestamp.

        Returns:
            PosFeedMessage confirming topic publication.
        """
        ...
