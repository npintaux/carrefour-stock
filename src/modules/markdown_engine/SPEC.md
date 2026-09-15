# Subsystem Specification: Markdown Engine (`src/modules/markdown_engine/`)

> **Status**: `LIVING DESIGN DOCUMENT — Tech-Lead-seeded (Gate 2), implementer-maintained`  
> **Source**: Subsystem Tech Lead (`/lead-decompose`)  
> **Parent Architecture**: [`architecture.md`](file:///home/user/carrefour-stock/docs/architecture.md)  
> **Business Requirements**: [`docs/PRD.md`](file:///home/user/carrefour-stock/docs/PRD.md)  
> **Interface Contract**: [`openapi.yaml`](file:///home/user/carrefour-stock/src/modules/markdown_engine/openapi.yaml)  
> **Selected Domain Pattern**: `decision-list`  
> **Target Implementer**: Developer Worker (`/implement`)  
> **Target Verifier**: Independent Test Architect (`/test-architect`)

---

## 1. Domain Scope & Responsibility
* **Subsystem Identifier**: `markdown_engine`
* **Directory Root**: `src/modules/markdown_engine/`
* **Domain Purpose**: The `markdown_engine` subsystem governs perishable date auditing (DLC/DLUO), dynamic discount pricing evaluation (T-1 at 30%, T-0 at 50%), promotional ESC/POS thermal barcode generation for Bluetooth mobile printers, real-time POS checkout broadcast feeds via Cloud Pub/Sub, and French AGEC law compliant charity donation (Banques Alimentaires) and bio-waste disposal write-offs.
* **Allowed Dependencies**:
  - Persistence: Google Cloud SQL (PostgreSQL Enterprise Plus) via dedicated repository port.
  - Messaging: Google Cloud Pub/Sub (`pos-markdown-updates` topic) via dedicated publisher port.
  - Analytics & Audit: Google Cloud BigQuery for AGEC fiscal donation logging.
  - Standard Libraries & Pure Python typing/dataclasses.
* **Encapsulation Rules**: External callers may only invoke public entrypoints defined in `src/modules/markdown_engine/entrypoints/`. Pure domain models, predicates, and engine logic under `src/modules/markdown_engine/domain/` are strictly isolated from direct I/O and external frameworks.

---

## 2. External Contract & API Schema
* **Interface Definition**: Defined in `src/modules/markdown_engine/openapi.yaml`.
* **Primary Endpoints**:
  | HTTP Verb | Path | Operation ID | Success Status | Error Statuses |
  |---|---|---|---|---|
  | `POST` | `/v1/markdown/evaluate` | `evaluateMarkdown` | `200 OK` | `400 Bad Request`, `422 Unprocessable`, `500 Internal Error` |
  | `POST` | `/v1/markdown/print-label` | `printMarkdownLabel` | `200 OK` | `400 Bad Request`, `422 Unprocessable`, `500 Internal Error` |
  | `POST` | `/v1/markdown/pos-feed` | `publishPosMarkdownEvent` | `201 Created` | `400 Bad Request`, `422 Unprocessable`, `500 Internal Error` |
  | `POST` | `/v1/markdown/donations` | `recordDonationOrSpoilage` | `201 Created` | `400 Bad Request`, `422 Unprocessable`, `500 Internal Error` |

---

## 3. Domain Models & Data Structures
The domain layer models requests, decisions, and output payloads as immutable dataclasses (`src/modules/markdown_engine/domain/models.py`):

```python
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Optional


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
    current_date: Optional[date] = None


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
    details: Optional[Mapping[str, Any]] = None


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
    beneficiary_name: Optional[str]
    stock_decremented: bool
    timestamp: datetime
```

---

## 4. Domain Pattern Realization & Business Logic

### Selected Pattern: `decision-list`
* **Port / Abstract Base Class**: Defined in `src/modules/markdown_engine/domain/rules/base.py`.
  - Concrete domain rules evaluate product attributes, expiry thresholds, and price calculations in an ordered chain.
  - Each rule implements the `Rule` ABC with `rule_id` and `evaluate(request: EvaluationRequest) -> Decision`.
* **Required Domain Artifacts**:
  - `rules/base.py`: Abstract Base Class for rule predicates.
  - `engine.py`: Composed decision dispatcher executing ordered rule evaluations.
* **Component Breakdown (1 class per file)**:
  | Component ID | Class Name | Target File | PRD User Story & AC | Logic & Conditions |
  |---|---|---|---|---|
  | **C1** | `Rule` | `src/modules/markdown_engine/domain/rules/base.py` | US-4 | Abstract base class defining `rule_id` and `evaluate` contract. |
  | **C2** | `PayloadValidationRule` | `src/modules/markdown_engine/domain/rules/payload_validation_rule.py` | US-4 (AC-4.1) | Validates non-empty IDs, positive quantities, and valid positive prices; rejects malformed inputs with 400. |
  | **C3** | `ExpiredDonationGatingRule` | `src/modules/markdown_engine/domain/rules/expired_donation_gating_rule.py` | US-4 (AC-4.3, FR-4.3) | Checks if `current_date > expiry_date` ($T > 0$ past expiry). Rejects retail sale markdown and flags lot for donation/bio-waste write-off with 422. |
  | **C4** | `DayZeroDiscountRule` | `src/modules/markdown_engine/domain/rules/day_zero_discount_rule.py` | US-4 (AC-4.1, Journey 3) | If `expiry_date == current_date` ($T-0$ expiry today), triggers 50% dynamic markdown calculation (`round(original_price_cents * 0.50)`). |
  | **C5** | `DayMinusOneDiscountRule` | `src/modules/markdown_engine/domain/rules/day_minus_one_discount_rule.py` | US-4 (AC-4.1, FR-4.1) | If `expiry_date - current_date == 1 day` ($T-1$ expiry tomorrow), triggers 30% dynamic markdown calculation (`round(original_price_cents * 0.70)`). |
  | **C6** | `StandardFreshnessRule` | `src/modules/markdown_engine/domain/rules/standard_freshness_rule.py` | US-4 (AC-4.1) | If product has $\ge 2$ days before expiry ($T-2$ or greater), item remains at standard price with 0% discount. |

* **Supporting Ports (Inverted Dependencies)**:
  | Port Interface | Target File | Purpose |
  |---|---|---|
  | `PrinterPort` | `src/modules/markdown_engine/domain/ports/printer_port.py` | ESC/POS byte sequence generation and barcode encoding (AC-4.1, FR-4.2). |
  | `PosFeedPublisherPort` | `src/modules/markdown_engine/domain/ports/pos_publisher_port.py` | Pub/Sub topic dispatch for till synchronization (AC-4.2). |
  | `DonationLedgerPort` | `src/modules/markdown_engine/domain/ports/donation_ledger_port.py` | AGEC tax reporting and stock write-off ledger integration (AC-4.3, FR-4.3). |

---

## 5. Composite Engine / Coordinator (`engine.py`)
* **Coordinator File**: `src/modules/markdown_engine/domain/engine.py`
* **Composition Pattern**: Instantiates and coordinates ordered sequence of rules:
  1. `PayloadValidationRule` (short-circuits with 400 on invalid payload)
  2. `ExpiredDonationGatingRule` (short-circuits with 422 on expired items, re-routing to donation candidate)
  3. `DayZeroDiscountRule` (matches $T-0$, emits `DISCOUNT_50` with 200)
  4. `DayMinusOneDiscountRule` (matches $T-1$, emits `DISCOUNT_30` with 200)
  5. `StandardFreshnessRule` (fallback for fresh items, emits `STANDARD_PRICE` with 200)
* **Execution Semantics**: Ordered evaluation; the first decisive rule produces the resulting `Decision`.

---

## 6. Error Taxonomy & Status Code Mapping
| Exception Class | HTTP Status Code | Response Code String | Trigger Scenario |
|---|---|---|---|
| `InvalidMarkdownPayloadError` | `400 Bad Request` | `INVALID_PAYLOAD` | Missing required fields, non-positive price/quantity, invalid dates |
| `ItemAlreadyExpiredError` | `422 Unprocessable Entity` | `ITEM_EXPIRED_DONATION_REQUIRED` | Product expiry date is in the past; retail markdown prohibited by hygiene laws |
| `IneligibleMarkdownError` | `422 Unprocessable Entity` | `INELIGIBLE_FOR_MARKDOWN` | Lot category or state cannot be discounted |
| `PrinterCommunicationError` | `500 Server Error` | `PRINTER_COMMUNICATION_ERROR` | Bluetooth/network ESC/POS printer driver failure |
| `PubSubPublishError` | `500 Server Error` | `PUBSUB_BROADCAST_FAILURE` | Failure publishing to `pos-markdown-updates` topic |
| `InternalServiceError` | `500 Server Error` | `INTERNAL_ERROR` | Unexpected unhandled exception |

---

## 7. Acceptance Criteria & Test Cases for Verification
The Independent Test Architect (`/test-architect`) must implement orthogonal contract tests verifying:
1. **Scenario 1 (Happy Path T-1 30% Discount - AC-4.1)**:
   - Given a perishable lot with expiry date tomorrow ($T-1$),
   - When `POST /v1/markdown/evaluate` is called with price 400 cents,
   - Then response status is `200 OK`, `eligible: true`, `discount_percentage: 30`, and `discounted_price_cents: 280`.
2. **Scenario 2 (Happy Path T-0 50% Discount - AC-4.1)**:
   - Given a perishable lot with expiry date today ($T-0$),
   - When `POST /v1/markdown/evaluate` is called with price 500 cents,
   - Then response status is `200 OK`, `eligible: true`, `discount_percentage: 50`, and `discounted_price_cents: 250`.
3. **Scenario 3 (Validation Failure - Bad Request)**:
   - Given a request with negative price or zero quantity,
   - When `POST /v1/markdown/evaluate` is called,
   - Then response status is `400 Bad Request` with structured `ErrorResponse`.
4. **Scenario 4 (Expired Product Gating - AC-4.3)**:
   - Given a product whose expiry date is in the past ($T+1$ or older),
   - When `POST /v1/markdown/evaluate` is called,
   - Then response status is `422 Unprocessable Entity` citing `ITEM_EXPIRED_DONATION_REQUIRED`.
5. **Scenario 5 (ESC/POS Label Generation - AC-4.1, FR-4.2)**:
   - When `POST /v1/markdown/print-label` is called with valid evaluation parameters,
   - Then response status is `200 OK`, returning Base64-encoded ESC/POS bytes and promotional barcode.
6. **Scenario 6 (POS Feed Broadcast - AC-4.2)**:
   - When `POST /v1/markdown/pos-feed` is called,
   - Then event is published to `pos-markdown-updates` topic and returns `201 Created` with message ID.
7. **Scenario 7 (AGEC Charity Donation / Spoilage - AC-4.3, FR-4.3)**:
   - When `POST /v1/markdown/donations` is called for Banques Alimentaires with action `CHARITY_DONATION`,
   - Then response status is `201 Created`, returning `fiscal_slip_id` and confirming stock deduction.
