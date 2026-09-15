"""Domain models and value objects for the markdown engine subsystem.

Traceability:
- [US-4][AC-4.1]: Models for markdown evaluation and ESC/POS thermal printing.
- [US-4][AC-4.2]: Models for POS Pub/Sub feed broadcast.
- [US-4][AC-4.3]: Models for AGEC charity donations and bio-waste removal records.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


class MarkdownStatus(str, Enum):
    """Categorical evaluation status for perishable stock."""

    DISCOUNT_30 = "DISCOUNT_30"
    DISCOUNT_50 = "DISCOUNT_50"
    STANDARD_PRICE = "STANDARD_PRICE"
    DONATION_CANDIDATE = "DONATION_CANDIDATE"
    SPOILAGE_CANDIDATE = "SPOILAGE_CANDIDATE"


@dataclass(frozen=True)
class EvaluationRequest:
    """Immutable input payload for markdown decision evaluation."""

    request_id: str
    store_id: str
    sku_id: str
    ean_barcode: str
    lot_number: str
    expiry_date: date
    original_price_cents: int
    quantity: int
    current_date: date | None = None


@dataclass(frozen=True)
class Decision:
    """Immutable outcome of rule execution from the decision engine."""

    is_allowed: bool
    status_code: int
    reason: str
    eligible: bool
    discount_percentage: int
    discounted_price_cents: int
    status: MarkdownStatus
    rule_applied: str
    details: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class LabelPrintCommand:
    """Generated thermal print instructions."""

    job_id: str
    promotional_barcode: str
    escpos_payload_base64: str
    labels_printed: int


@dataclass(frozen=True)
class PosFeedMessage:
    """POS broadcast update payload."""

    message_id: str
    topic: str
    store_id: str
    ean_barcode: str
    promotional_barcode: str
    discounted_price_cents: int
    valid_until: datetime
    published_at: datetime


@dataclass(frozen=True)
class DonationSpoilageRecord:
    """Audit record for AGEC-compliant charity donation or bio-waste."""

    record_id: str
    fiscal_slip_id: str
    action_type: str
    store_id: str
    sku_id: str
    lot_number: str
    quantity: int
    original_value_cents: int
    reason_code: str
    beneficiary_name: str | None
    stock_decremented: bool
    timestamp: datetime
