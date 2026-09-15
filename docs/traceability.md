# Story <-> Subsystem Traceability Matrix

> **Status**: `FROZEN / BASELINE (Gate 0.5)`  
> **Source**: Lead Cloud Architect (`/architect-design`)  
> **Contractual Inputs**: [`docs/PRD.md`](file:///home/user/carrefour-stock/docs/PRD.md), [`docs/architecture.md`](file:///home/user/carrefour-stock/docs/architecture.md)

---

## 1. Traceability Matrix

This matrix maps each PRD User Story to its realizing architectural subsystem(s) declared in `docs/architecture.md`.

| PRD User Story | Subsystem Path(s) | Realization Scope & Acceptance Criteria |
|---|---|---|
| **US-1** (Department-Scoped Stock View) | `src/modules/stock_ledger/` | Realizes AC-1.1, AC-1.2, AC-1.3: Enforces departmental RBAC boundaries and tenant isolation for stock balance queries and adjustments, returning HTTP 403 on out-of-scope actions. |
| **US-2** (Dual-Key Authorization for High-Value Shrinkage) | `src/modules/stock_ledger/` | Realizes AC-2.1, AC-2.2, AC-2.3: Enforces threshold checks (>= €500), transitions state to PENDING_DIRECTOR_APPROVAL, locks reason codes, and exports audit logs to BigQuery upon Store Director approval. |
| **US-3** (Receiving Dock ASN Barcode Ingestion & Cold-Chain Check) | `src/modules/inbound_dock/` | Realizes AC-3.1, AC-3.2, AC-3.3: Ingests ASN line items, performs cold-chain temperature verification, triggers quarantine locks, and supports offline mobile scan sync with UUID idempotency keys. |
| **US-4** (Dynamic Expiry Sticker Generation & POS Feed) | `src/modules/markdown_engine/` | Realizes AC-4.1, AC-4.2, AC-4.3: Calculates dynamic discounts (T-1: 30%, T-0: 50%), drives mobile Bluetooth label printing, broadcasts markdown events to Pub/Sub for POS recognition, and tracks AGEC food donations. |

---

## 2. Subsystem Coverage Verification

All architectural subsystems declared in [`docs/architecture.md`](file:///home/user/carrefour-stock/docs/architecture.md) are mapped to user stories:

| Subsystem Name | Subsystem Path | Assigned PRD Stories | Functional Module Reference |
|---|---|---|---|
| **inbound_dock** | `src/modules/inbound_dock/` | US-3 | Module 1: Inbound Logistics & Receiving (Dock) |
| **stock_ledger** | `src/modules/stock_ledger/` | US-1, US-2 | Module 2: Multi-Zone Stock Ledger; Module 3: RBAC & Partitioning; Module 5: Continuous Inventory Counting |
| **markdown_engine** | `src/modules/markdown_engine/` | US-4 | Module 4: Perishable Date Tracking & Dynamic Markdown (Anti-Gaspi) |
