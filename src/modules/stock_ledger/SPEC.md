# Subsystem Specification: Stock Ledger (`src/modules/stock_ledger/`)

> **Status**: `LIVING DESIGN DOCUMENT — Tech-Lead-seeded (Gate 2), implementer-maintained`  
> **Source**: Subsystem Tech Lead (`/lead-decompose`)  
> **Parent Architecture**: [`architecture.md`](file:///home/user/carrefour-stock/docs/architecture.md)  
> **Business Requirements**: [`docs/PRD.md`](file:///home/user/carrefour-stock/docs/PRD.md)  
> **Interface Contract**: [`openapi.yaml`](file:///home/user/carrefour-stock/src/modules/stock_ledger/openapi.yaml)  
> **Selected Domain Pattern**: `decision-list`  
> **Target Implementer**: Developer Worker (`/implement`)  
> **Target Verifier**: Independent Test Architect (`/test-architect`)

---

## 1. Domain Scope & Responsibility
* **Subsystem Identifier**: `stock_ledger`
* **Directory Root**: `src/modules/stock_ledger/`
* **Domain Purpose**: 
  - Manage real-time multi-zone store inventory partitioned across physical and virtual sub-locations: `RECEIVING_DOCK`, `COLD_STORAGE_RESERVE`, `DRY_RESERVE`, `IN_TRANSIT_FLOOR`, `SALES_FLOOR_FACING`, `QUARANTINE_DAMAGED`, `CUSTOMER_CLICK_COLLECT_STAGED` (FR-2.1).
  - Enforce strict role-based departmental scoping (FR-3.1, US-1: Section Managers / *Chefs de Rayon* can only query and mutate items in their assigned department taxonomy; unauthorized mutations return HTTP 403 `ERR_OUT_OF_SCOPE_DEPARTMENT`).
  - Enforce dual-key authorization for high-value shrinkage and adjustments (FR-3.2, US-2: adjustments with absolute financial value $\ge €500.00$ require Store Director dual-sign-off and transition to `PENDING_DIRECTOR_APPROVAL`).
  - Support two-step replenishment stock movements between zones to eliminate phantom stock (FR-2.2).
  - Absorb sub-second Point of Sale (POS) basket depletions from sales floor stock (FR-2.3).
* **Allowed Dependencies**:
  - Google Cloud SQL PostgreSQL (Enterprise Plus Regional HA)
  - Google Cloud Memorystore for Redis
  - Google Cloud Pub/Sub
  - Google Cloud BigQuery
* **Encapsulation Rules**: Only public entrypoints in `src/modules/stock_ledger/entrypoints/` may be invoked by outside callers or routers. Internal domain models, rule evaluation logic in `src/modules/stock_ledger/domain/rules/base.py`, and rule engine in `src/modules/stock_ledger/domain/engine.py` are strictly private to this subsystem. Persistence is decoupled via the `StockRepository` port in `src/modules/stock_ledger/domain/repository.py` and implemented under `src/modules/stock_ledger/adapters/`.

---

## 2. External Contract & API Schema
* **Interface Definition**: Defined in `src/modules/stock_ledger/openapi.yaml`.
* **Primary Endpoints**:
  | HTTP Verb | Path | Operation ID | Success Status | Error Statuses |
  |---|---|---|---|---|
  | `GET` | `/v1/stores/{store_id}/stock` | `listDepartmentStock` | `200 OK` | `400 Bad Request`, `403 Forbidden`, `500 Internal Error` |
  | `POST` | `/v1/stores/{store_id}/adjustments` | `submitStockAdjustment` | `200 OK`, `202 Accepted` | `400 Bad Request`, `403 Forbidden`, `422 Unprocessable`, `500 Internal Error` |
  | `POST` | `/v1/stores/{store_id}/adjustments/{adjustment_id}/sign-off` | `signOffStockAdjustment` | `200 OK` | `400 Bad Request`, `403 Forbidden`, `404 Not Found`, `409 Conflict`, `500 Internal Error` |
  | `POST` | `/v1/stores/{store_id}/transfers` | `executeInternalTransfer` | `200 OK` | `400 Bad Request`, `403 Forbidden`, `422 Unprocessable`, `500 Internal Error` |
  | `POST` | `/v1/stores/{store_id}/pos-depletions` | `ingestPosDepletion` | `200 OK` | `400 Bad Request`, `422 Unprocessable`, `500 Internal Error` |

---

## 3. Domain Models & Data Structures
Immutable dataclasses representing requests, entities, decisions, and outcomes in `src/modules/stock_ledger/domain/models.py`:

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class StockZone(str, Enum):
    RECEIVING_DOCK = "RECEIVING_DOCK"
    COLD_STORAGE_RESERVE = "COLD_STORAGE_RESERVE"
    DRY_RESERVE = "DRY_RESERVE"
    IN_TRANSIT_FLOOR = "IN_TRANSIT_FLOOR"
    SALES_FLOOR_FACING = "SALES_FLOOR_FACING"
    QUARANTINE_DAMAGED = "QUARANTINE_DAMAGED"
    CUSTOMER_CLICK_COLLECT_STAGED = "CUSTOMER_CLICK_COLLECT_STAGED"


class AdjustmentStatus(str, Enum):
    AUTO_APPROVED = "AUTO_APPROVED"
    PENDING_DIRECTOR_APPROVAL = "PENDING_DIRECTOR_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ReasonCode(str, Enum):
    THEFT = "THEFT"
    BREAKAGE = "BREAKAGE"
    INTERNAL_CONSUMPTION = "INTERNAL_CONSUMPTION"
    MISCOUNT = "MISCOUNT"
    EXPIRY_SPOILAGE = "EXPIRY_SPOILAGE"
    OTHER = "OTHER"


@dataclass(frozen=True)
class StockItem:
    """Immutable stock balance record for a specific SKU and zone."""

    sku_id: str
    ean13: str
    product_name: str
    department_id: str
    zone: StockZone
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True)
class AdjustmentEvaluationRequest:
    """Immutable input payload for adjustment policy rule evaluation."""

    request_id: str
    store_id: str
    sku_id: str
    department_id: str
    zone: StockZone
    quantity_delta: int
    unit_price_cents: int
    reason_code: ReasonCode
    initiator_id: str
    initiator_role: str
    user_departments: tuple[str, ...]
    threshold_cents: int = 50000  # €500.00 default threshold


@dataclass(frozen=True)
class Decision:
    """Immutable outcome of rule evaluation."""

    is_allowed: bool
    status_code: int
    error_code: Optional[str]
    reason: str
    action: Optional[str] = None  # e.g. "AUTO_APPROVE", "HOLD_FOR_APPROVAL"
    details: Optional[dict[str, object]] = None


@dataclass(frozen=True)
class AdjustmentRecord:
    """Persisted adjustment entity in datastore."""

    adjustment_id: str
    store_id: str
    sku_id: str
    department_id: str
    zone: StockZone
    quantity_delta: int
    unit_price_cents: int
    total_value_cents: int
    reason_code: ReasonCode
    initiator_id: str
    status: AdjustmentStatus
    director_id: Optional[str] = None
    director_note: Optional[str] = None
```

---

## 4. Domain Pattern Realization & Business Logic

### Selected Pattern: `decision-list`
* **Port / Abstract Base Class**: Defined in `src/modules/stock_ledger/domain/rules/base.py` (`Rule(abc.ABC)`).
* **Repository ABC Port**: Defined in `src/modules/stock_ledger/domain/repository.py` (`StockRepository(abc.ABC)`).
* **Component Breakdown (1 class per file)**:
  | Component ID | Class Name | Target File | PRD User Story & AC | Logic & Conditions |
  |---|---|---|---|---|
  | **R1** | `DepartmentScopeRule` | `src/modules/stock_ledger/domain/rules/department_scope_rule.py` | US-1 (AC-1.1, AC-1.2) | Validates that the SKU's target department matches the initiator's authorized `user_departments` claim unless the user holds global role `DIRECTEUR_MAGASIN`. If mismatched, short-circuits with `is_allowed=False, status_code=403, error_code="ERR_OUT_OF_SCOPE_DEPARTMENT"`. |
  | **R2** | `SufficientStockRule` | `src/modules/stock_ledger/domain/rules/sufficient_stock_rule.py` | US-1 (AC-1.2), FR-2.1 | When `quantity_delta < 0`, checks against `StockRepository` to verify the specified zone contains sufficient available quantity. If insufficient, short-circuits with `is_allowed=False, status_code=422, error_code="ERR_INSUFFICIENT_STOCK"`. |
  | **R3** | `DualKeyThresholdRule` | `src/modules/stock_ledger/domain/rules/dual_key_threshold_rule.py` | US-2 (AC-2.1) | Calculates `total_value_cents = abs(quantity_delta) * unit_price_cents`. If `total_value_cents >= threshold_cents` (default €500), flags adjustment for dual-key authorization (`action="HOLD_FOR_APPROVAL"`, status `PENDING_DIRECTOR_APPROVAL`, HTTP `202 Accepted`). Otherwise flags `action="AUTO_APPROVE"`, HTTP `200 OK`. |
  | **S1** | `SignOffValidator` | `src/modules/stock_ledger/domain/rules/sign_off_validator.py` | US-2 (AC-2.2, AC-2.3) | Validates director sign-off requests. Requires initiator to hold `DIRECTEUR_MAGASIN`, adjustment record to be in `PENDING_DIRECTOR_APPROVAL` (409 Conflict if already decided), and mandatory note if action is `REJECT` (400 Bad Request). |

### Rule ABC Definition (`src/modules/stock_ledger/domain/rules/base.py`)
```python
import abc
from ..models import AdjustmentEvaluationRequest, Decision


class Rule(abc.ABC):
    """Abstract Base Class for individual decision predicates in stock_ledger."""

    @property
    @abc.abstractmethod
    def rule_id(self) -> str:
        """Unique rule identifier (e.g., 'R1_DEPARTMENT_SCOPE')."""
        ...

    @abc.abstractmethod
    def evaluate(self, request: AdjustmentEvaluationRequest) -> Decision:
        """Evaluate business rule against adjustment request."""
        ...
```

---

## 5. Composite Engine / Coordinator (`engine.py`)
* **Coordinator File**: `src/modules/stock_ledger/domain/engine.py` (`AdjustmentDecisionEngine`)
* **Composition Pattern**: Instantiates and coordinates ordered sequence of `Rule` implementations (`DepartmentScopeRule` $\rightarrow$ `SufficientStockRule` $\rightarrow$ `DualKeyThresholdRule`).
* **Execution Semantics**: Ordered evaluation; halts on first failing predicate (`is_allowed=False`), returning the specific failure `Decision` (403 or 422). If all rules pass, returns a success `Decision` (`200 OK` for auto-approval or `202 Accepted` for dual-key hold).

```python
from collections.abc import Sequence
from .models import AdjustmentEvaluationRequest, Decision
from .rules.base import Rule


class AdjustmentDecisionEngine:
    """Composed dispatcher executing ordered rule sequence for stock adjustments."""

    def __init__(self, rules: Sequence[Rule]) -> None:
        self._rules = tuple(rules)

    def evaluate(self, request: AdjustmentEvaluationRequest) -> Decision:
        for rule in self._rules:
            decision = rule.evaluate(request)
            if not decision.is_allowed:
                return decision
            # If a rule sets an action (e.g. HOLD_FOR_APPROVAL), preserve it
            if decision.action == "HOLD_FOR_APPROVAL":
                return decision

        return Decision(
            is_allowed=True,
            status_code=200,
            error_code=None,
            action="AUTO_APPROVE",
            reason="All adjustment policy rules passed.",
        )
```

---

## 6. Error Taxonomy & Status Code Mapping
| Exception Class | HTTP Status Code | Response Code String | Trigger Scenario |
|---|---|---|---|
| `DepartmentScopeViolationError` | `403 Forbidden` | `ERR_OUT_OF_SCOPE_DEPARTMENT` | User attempts to query or adjust stock in a department outside their assigned `department_ids` (US-1, AC-1.2) |
| `InsufficientStockError` | `422 Unprocessable` | `ERR_INSUFFICIENT_STOCK` | Requested negative adjustment or transfer exceeds available quantity in source zone |
| `InvalidPayloadError` | `400 Bad Request` | `INVALID_PAYLOAD` | Missing required fields, negative unit price, or malformed UUID |
| `AdjustmentNotFoundError` | `404 Not Found` | `ADJUSTMENT_NOT_FOUND` | Director sign-off target adjustment ID does not exist |
| `InvalidTransitionError` | `409 Conflict` | `STATE_CONFLICT` | Sign-off attempted on an adjustment that is not in `PENDING_DIRECTOR_APPROVAL` state |
| `UnauthorizedDirectorError` | `403 Forbidden` | `ERR_UNAUTHORIZED_DIRECTOR` | Non-director user attempts to invoke `/sign-off` endpoint |
| `InternalServiceError` | `500 Server Error` | `INTERNAL_ERROR` | Datastore or infrastructure failure; stack traces sanitized |

---

## 7. Acceptance Criteria & Test Cases for Verification
The Independent Test Architect (`/test-architect`) must implement orthogonal contract tests verifying:
1. **Scenario 1 (US-1 / AC-1.1 - Department Stock Query Filtered)**:
   - Query `/v1/stores/{store_id}/stock?department_id=RAYON_FRAIS` with `CHEF_DE_RAYON` token in `RAYON_FRAIS`.
   - Assert `200 OK` with only products belonging to `RAYON_FRAIS`.
2. **Scenario 2 (US-1 / AC-1.2 - Out-of-Scope Department Rejection)**:
   - Submit adjustment on `RAYON_EPICERIE` with user having `user_departments: ["RAYON_FRAIS"]`.
   - Assert `403 Forbidden` with response body containing `code: "ERR_OUT_OF_SCOPE_DEPARTMENT"`.
3. **Scenario 3 (US-2 / AC-2.1 - Dual-Key Escalation for >= €500 Write-Off)**:
   - Submit negative adjustment: 10 units of €55.00 each (€550.00 total) within assigned department.
   - Assert `202 Accepted` with status `PENDING_DIRECTOR_APPROVAL` and notification queued.
4. **Scenario 4 (US-2 / AC-2.2 - Store Director Approval Commit)**:
   - Post sign-off with action `APPROVE` by `DIRECTEUR_MAGASIN`.
   - Assert `200 OK`, status `APPROVED`, stock balance deducted, and audit trail recorded.
5. **Scenario 5 (US-2 / AC-2.3 - Store Director Rejection)**:
   - Post sign-off with action `REJECT` and mandatory note.
   - Assert `200 OK`, status `REJECTED`, stock remains intact. Rejection without note returns `400 Bad Request`.
6. **Scenario 6 (FR-2.2 - Multi-Zone Transfer Validation)**:
   - Execute transfer from `DRY_RESERVE` to `SALES_FLOOR_FACING`.
   - Assert `200 OK` and updated zone allocations. Transfer exceeding source zone quantity returns `422 Unprocessable`.
7. **Scenario 7 (Idempotency Key Verification)**:
   - Replay exact `Idempotency-Key` on mutative endpoints.
   - Assert cached idempotent response returned without double-deduction.
