"""In-memory Cloud Pub/Sub publisher adapter for POS markdown broadcast.

Traceability:
- [US-4][AC-4.2]: Pub/Sub markdown topic broadcast for till synchronization.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..domain.exceptions import PubSubPublishError
from ..domain.models import PosFeedMessage
from ..domain.ports.pos_publisher_port import PosPublisherPort


class InMemoryPosPublisherAdapter(PosPublisherPort):
    """In-memory adapter simulating Cloud Pub/Sub markdown event publication."""

    def __init__(self, simulate_fault: bool = False) -> None:
        """Initialize adapter.

        Args:
            simulate_fault: When True, simulates Pub/Sub publish failure.
        """
        self.simulate_fault = simulate_fault
        self.published_messages: list[PosFeedMessage] = []

    def publish_pos_markdown(
        self,
        request_id: str,
        store_id: str,
        ean_barcode: str,
        promotional_barcode: str,
        discounted_price_cents: int,
        valid_until: datetime,
    ) -> PosFeedMessage:
        """Publish promotional markdown event.

        Args:
            request_id: Unique request identifier.
            store_id: Store identifier.
            ean_barcode: Product EAN-13 barcode.
            promotional_barcode: Promotional sticker barcode.
            discounted_price_cents: Markdown price in cents.
            valid_until: Validity expiration timestamp.

        Returns:
            PosFeedMessage confirming topic publication.

        Raises:
            PubSubPublishError: If simulate_fault is active.
        """
        if self.simulate_fault:
            raise PubSubPublishError(
                "Pub/Sub topic 'pos-markdown-updates' unreachable."
            )

        now = datetime.now(UTC)
        msg_id = f"MSG-{uuid.uuid4().hex[:12].upper()}"
        message = PosFeedMessage(
            message_id=msg_id,
            topic="pos-markdown-updates",
            store_id=store_id,
            ean_barcode=ean_barcode,
            promotional_barcode=promotional_barcode,
            discounted_price_cents=discounted_price_cents,
            valid_until=valid_until,
            published_at=now,
        )
        self.published_messages.append(message)
        return message
