# Subsystem Specification: Inbound Logistics & Dock Receiving (`src/modules/inbound_dock/`)

> **Status**: `LIVING DESIGN DOCUMENT — Tech-Lead-seeded (Gate 2), implementer-maintained`  
> **Source**: Subsystem Tech Lead (`/lead-decompose`)  
> **Parent Architecture**: [`architecture.md`](file:///home/user/carrefour-stock/docs/architecture.md)  
> **Business Requirements**: [`docs/PRD.md`](file:///home/user/carrefour-stock/docs/PRD.md)  
> **Interface Contract**: [`openapi.yaml`](file:///home/user/carrefour-stock/src/modules/inbound_dock/openapi.yaml)  
> **Selected Domain Pattern**: `state-machine`  
> **Target Implementer**: Developer Worker (`/implement`)  
> **Target Verifier**: Independent Test Architect (`/test-architect`)

---

## 1. Domain Scope & Responsibility
* **Subsystem Identifier**: `inbound_dock`
* **Directory Root**: `src/modules/inbound_dock/`
* **Domain Purpose**: Ingestion of Advanced Shipping Notices (ASNs) from SAP ERP/WMS, GS1/SSCC-18 pallet barcode parsing and validation, cold-chain temperature verification (0°C to 4°C for CHILLED, ≤ -18°C for FROZEN), quarantine vs backroom staging lifecycle transitions, and carrier discrepancy claim logging with photo proof.
* **Allowed Dependencies**:
  - Google Cloud SQL (PostgreSQL Enterprise Plus) for shipment and pallet status persistence
  - Google Cloud Memorystore for Redis for sub-10ms SSCC barcode cache lookups
  - Google Cloud Storage for delivery manifest photos and discrepancy evidence
  - Google Cloud Pub/Sub for publishing goods receipt events (`asn-received-topic`)
  - Google Cloud Tasks for rate-limited synchronization to central SAP ERP
* **Encapsulation Rules**: Only public entrypoints in `src/modules/inbound_dock/entrypoints/` may be invoked by outside callers or HTTP routes. Internal domain models, state machines, and rules in `src/modules/inbound_dock/domain/` are strictly private to this subsystem. External systems are integrated exclusively through abstract ports in `domain/` implemented in `adapters/`.

---

## 2. External Contract & API Schema
* **Interface Definition**: Defined in `src/modules/inbound_dock/openapi.yaml`.
* **Primary Endpoints**:
  | HTTP Verb | Path | Operation ID | Success Status | Error Statuses |
  |---|---|---|---|---|
  | `POST` | `/v1/inbound-shipments` | `ingestAsn` | `201 Created` | `400 Bad Request`, `409 Conflict`, `422 Unprocessable`, `500 Server Error` |
  | `GET` | `/v1/stores/{storeId}/inbound-shipments/{asnId}` | `getAsn` | `200 OK` | `400 Bad Request`, `404 Not Found`, `500 Server Error` |
  | `POST` | `/v1/inbound-shipments/{asnId}/receive-pallet` | `receivePallet` | `200 OK` | `400 Bad Request`, `404 Not Found`, `409 Conflict`, `422 Unprocessable`, `500 Server Error` |
  | `POST` | `/v1/inbound-shipments/{asnId}/discrepancies` | `recordDiscrepancy` | `201 Created` | `400 Bad Request`, `404 Not Found`, `422 Unprocessable`, `500 Server Error` |

---

## 3. Domain Models & Data Structures
Immutable dataclasses representing requests, entities, and state transition results (`src/modules/inbound_dock/domain/models.py`):

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Optional


class TemperatureRegime(Enum):
    """Cold-chain classification regimes."""

    AMBIENT = "AMBIENT"
    CHILLED = "CHILLED"
    FROZEN = "FROZEN"


class PalletLifecycleState(Enum):
    """Lifecycle states of an inbound pallet."""

    EXPECTED = auto()
    IN_RECEIVING = auto()
    BACKROOM_STAGING = auto()
    STATUS_QUARANTINE = auto()
    REJECTED_RTV = auto()


class PalletEventType(Enum):
    """Domain events driving pallet lifecycle transitions."""

    SCAN = auto()
    PASS_INSPECTION = auto()
    FAIL_COLD_CHAIN = auto()
    FLAG_DAMAGE = auto()
    RETURN_TO_VENDOR = auto()


@dataclass(frozen=True)
class AsnLineItem:
    """Individual product line item on an ASN manifest."""

    sku: str
    ean13: str
    expected_quantity: int
    lot_number: str
    bbd: str  # YYYY-MM-DD


@dataclass(frozen=True)
class PalletEntity:
    """Inbound pallet container domain entity."""

    sscc: str
    asn_id: str
    temperature_regime: TemperatureRegime
    state: PalletLifecycleState
    lines: tuple[AsnLineItem, ...]
    probed_temperature: Optional[float] = None
    received_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


@dataclass(frozen=True)
class PalletEvent:
    """Event triggering a pallet state transition."""

    event_type: PalletEventType
    entity_id: str  # SSCC
    store_id: str
    operator_id: str
    probed_temperature: Optional[float] = None
    damage_observed: bool = False
    notes: Optional[str] = None


@dataclass(frozen=True)
class TransitionResult:
    """Result of state machine evaluation."""

    success: bool
    from_state: PalletLifecycleState
    to_state: PalletLifecycleState
    target_location: str
    message: str
    violation_reason: Optional[str] = None
```

---

## 4. Domain Pattern Realization & Business Logic

### Selected Pattern: `state-machine`
* **Pattern Implementation**: Concrete state machine and transition table defined in `src/modules/inbound_dock/domain/state_machine.py`.
* **Ports / Secondary Collaborators**:
  - `InboundShipmentRepository` in `src/modules/inbound_dock/domain/repository.py` (abstract repository port for loading/saving ASN and pallet state).
  - `ColdChainEvaluator` in `src/modules/inbound_dock/domain/cold_chain_evaluator.py` (pure domain evaluation of probed temperature against regulatory thresholds: 0°C to 4°C for CHILLED, ≤ -18°C for FROZEN).
  - `BarcodeValidator` in `src/modules/inbound_dock/domain/barcode_validator.py` (GS1-128 and SSCC-18 check digit and format validator).
* **Component Breakdown**:
  | Component ID | Class Name | Target File | PRD User Story & AC | Logic & Conditions |
  |---|---|---|---|---|
  | **C1** | `InboundPalletStateMachine` | `src/modules/inbound_dock/domain/state_machine.py` | US-3 (AC-3.1, AC-3.2) | Manages deterministic lifecycle transitions (`EXPECTED -> IN_RECEIVING -> BACKROOM_STAGING / STATUS_QUARANTINE / REJECTED_RTV`). Enforces illegal transition guards (raising `InvalidTransitionError` -> 409 Conflict). |
  | **C2** | `ColdChainEvaluator` | `src/modules/inbound_dock/domain/cold_chain_evaluator.py` | US-3 (AC-3.1) | Evaluates probed temperature: CHILLED requires 0.0°C <= T <= 4.0°C; FROZEN requires T <= -18.0°C; AMBIENT requires no temperature gating. Breaches produce `COLD_CHAIN_VIOLATION`. |
  | **C3** | `BarcodeValidator` | `src/modules/inbound_dock/domain/barcode_validator.py` | US-3 (AC-3.2, FR-1.2) | Validates 18-digit SSCC barcode structure, modulo-10 Luhn check digit, and standard EAN-13 formats. |
  | **C4** | `InboundShipmentRepository` | `src/modules/inbound_dock/domain/repository.py` | US-3 (AC-3.2, AC-3.3) | Abstract repository port for durable persistence of ASNs, pallets, and discrepancy claims. Implemented via Cloud SQL + Redis in adapters. |

---

## 5. Composite Coordinator (`state_machine.py` & Service Coordination)
* **Coordinator File**: `src/modules/inbound_dock/domain/state_machine.py`
* **Composition Pattern**:
  `InboundPalletStateMachine` coordinates lifecycle transition logic against the immutable `TRANSITION_MATRIX`:
  - `(EXPECTED, SCAN)` -> `IN_RECEIVING`
  - `(IN_RECEIVING, PASS_INSPECTION)` -> `BACKROOM_STAGING`
  - `(IN_RECEIVING, FAIL_COLD_CHAIN)` -> `STATUS_QUARANTINE`
  - `(IN_RECEIVING, FLAG_DAMAGE)` -> `STATUS_QUARANTINE`
  - `(STATUS_QUARANTINE, RETURN_TO_VENDOR)` -> `REJECTED_RTV`
* **Execution Semantics**:
  1. Upon receiving an SSCC scan, `InboundPalletStateMachine` transitions pallet from `EXPECTED` to `IN_RECEIVING`.
  2. `ColdChainEvaluator` tests the probed temperature against the pallet's `TemperatureRegime`.
  3. If temperature is within bounds and no damage is flagged, the event `PASS_INSPECTION` transitions the pallet to `BACKROOM_STAGING` (assigned to target location `BACKROOM_STAGING` or `COLD_STORAGE_RESERVE`).
  4. If temperature is out of bounds (e.g. 7.5°C for a 0-4°C CHILLED pallet) or damage is observed, the event `FAIL_COLD_CHAIN` or `FLAG_DAMAGE` transitions the pallet to `STATUS_QUARANTINE` (assigned to location `QUARANTINE_DAMAGED`).
  5. Any attempt to transition an already finalized pallet (`BACKROOM_STAGING`, `REJECTED_RTV`) raises `InvalidTransitionError` mapping to HTTP `409 Conflict`.

---

## 6. Error Taxonomy & Status Code Mapping
| Exception Class | HTTP Status Code | Response Code String | Trigger Scenario |
|---|---|---|---|
| `InvalidBarcodeError` | `400 Bad Request` | `INVALID_SSCC_BARCODE` | Barcode fails SSCC-18 length check, non-numeric chars, or check digit verification |
| `MissingTemperatureError` | `400 Bad Request` | `MISSING_PROBE_TEMPERATURE` | Probed temperature omitted on CHILLED or FROZEN pallet intake |
| `ShipmentNotFoundError` | `404 Not Found` | `SHIPMENT_NOT_FOUND` | Inbound ASN ID does not exist in store datastore |
| `PalletNotFoundError` | `404 Not Found` | `PALLET_NOT_FOUND` | Scanned SSCC does not belong to the referenced ASN |
| `InvalidTransitionError` | `409 Conflict` | `STATE_CONFLICT` | Event conflicts with pallet's current lifecycle state (e.g. re-scanning finalized pallet) |
| `ColdChainViolationError` | `422 Unprocessable` | `COLD_CHAIN_VIOLATION` | Temperature probe exceeds regulatory limits (e.g., > 4°C for chilled or > -18°C for frozen) when attempting direct acceptance |
| `DatabaseAdapterError` | `500 Server Error` | `INTERNAL_DATABASE_ERROR` | Cloud SQL or Redis connectivity or write failure |

---

## 7. Acceptance Criteria & Test Cases for Verification
The Independent Test Architect (`/test-architect`) must implement orthogonal contract tests verifying:
1. **Scenario 1 (Happy Path - Compliant Pallet Receiving)**:
   - Given an ASN with expected chilled pallet (regime `CHILLED`), when receiving with probed temperature $2.5^\circ\text{C}$ and valid SSCC, response status is `200 OK`, pallet status is `BACKROOM_STAGING`, and target location is `COLD_STORAGE_RESERVE` (linking US-3, AC-3.2).
2. **Scenario 2 (Cold-Chain Breach Quarantine)**:
   - Given a chilled pallet with requirement $0^\circ\text{C}-4^\circ\text{C}$, when operator inputs $7.5^\circ\text{C}$, response is `200 OK` (or `422 Unprocessable` if rejected), pallet state transitions to `STATUS_QUARANTINE`, target location is `QUARANTINE_DAMAGED`, and violation reason states `COLD_CHAIN_VIOLATION` (linking US-3, AC-3.1).
3. **Scenario 3 (Malformed SSCC Barcode)**:
   - Given an invalid SSCC barcode (e.g. length != 18 or invalid check digit), request returns HTTP `400 Bad Request` with code `INVALID_SSCC_BARCODE`.
4. **Scenario 4 (Lifecycle State Conflict)**:
   - Given a pallet already in `BACKROOM_STAGING`, an incoming receipt event raises `InvalidTransitionError` returning HTTP `409 Conflict` with code `STATE_CONFLICT`.
5. **Scenario 5 (ASN Ingestion & Idempotency Replay)**:
   - Ingesting an ASN with an existing `Idempotency-Key` does not duplicate line items or pallets, returning cached `201 Created` / `200 OK` (linking US-3, AC-3.3).
