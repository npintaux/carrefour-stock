# [ADR-0005] Mobile Offline-First Resilience & Idempotent Synchronization

* **Status**: accepted
* **Deciders**: Lead Cloud Architect, SecOps Architect, Tech Lead
* **Date**: 2026-09-15
* **Superseded by**: N/A
* **Approved-by**: npintaux

## Context and Problem Statement

Supermarket store associates frequently operate in RF-shielded environments such as concrete basement reserves, walk-in cold rooms (-18°C / 4°C), and remote loading docks where Wi-Fi and 4G coverage drop intermittently. During inbound pallet receiving, temperature probing, and shelf replenishment, mobile scanning workflows cannot block or fail due to network loss. Furthermore, when network connectivity is restored, replaying queued mobile requests risks generating duplicate inventory receipts or over-adjusting stock balances if network timeouts occur during sync.

## Decision Drivers

* **Zero-Downtime Scanning**: Warehouse and sales floor associates must continue scanning barcodes, recording temperatures, and picking items uninterrupted during network outages.
* **Idempotent Synchronization (NFR-4)**: Cloud APIs must enforce strict idempotency on all mutative requests (`POST`, `PUT`, `PATCH`) to guarantee zero duplicate stock records upon retry.
* **Data Integrity & Consistency**: Local mobile queues must prevent data loss and ensure correct ordering when syncing batches to the central Cloud Run API.
* **Cryptographic Local Storage**: Sensitive offline transactions cached on handheld devices must be encrypted at rest in accordance with GDPR/RGPD security requirements.

## Considered Options

* **Option 1: Offline-First Local Storage (Android Room / SQLite) + Encrypted WorkManager Queue + UUID Idempotency-Key Central Validation** - Mobile Zebra clients record scans into an encrypted SQLite local cache (SQLCipher/Room), dispatch background sync via Android Jetpack WorkManager with exponential backoff, and attach client-generated UUID `Idempotency-Key` headers verified centrally in Cloud Run and Redis/Cloud SQL.
* **Option 2: Cloud Firestore Mobile SDK with Offline Persistence** - Use Google Cloud Firestore Android SDK which provides built-in offline document caching and automatic background synchronization.
* **Option 3: Online-Only Mobile Client with Retry Toast Prompts** - Disallow offline operations; require continuous network connection and prompt users to retry manually when requests fail.

## Decision Outcome

Chosen option: **Option 1: Offline-First Local Storage (Android Room / SQLite) + Encrypted WorkManager Queue + UUID Idempotency-Key Central Validation**, because it grants total control over domain-specific validation (e.g. validating cold-chain temperature thresholds locally without network roundtrips), protects data at rest with encryption, and enforces strict server-side idempotency keys cached in Memorystore Redis and persisted in Cloud SQL.

### Positive Consequences

* **Uninterrupted Store Operations**: Associates scan pallets and record temperatures without delay in walk-in freezers or dock signal dead-zones.
* **Guaranteed Exactly-Once Processing**: Central APIs enforce a 24-hour deduplication window on `Idempotency-Key`, ensuring replayed offline requests never create duplicate stock receipts.
* **Local Business Rule Execution**: Cold-chain threshold violations (e.g. > 4°C for chilled poultry) trigger immediate quarantine prompts locally on the handheld even while offline.
* **Resilient Retry Mechanism**: Jetpack WorkManager handles network constraints, exponential backoff, and battery optimization natively.

### Negative Consequences / Trade-offs

* **Conflict Resolution**: If two associates pick from the same bin while offline, conflict detection must be resolved server-side using version optimistic concurrency tokens.
* **Local State Size**: Mobile devices must prune completed transaction history periodically to prevent local SQLite database bloat.
* **Idempotency Store Maintenance**: Central Memorystore Redis cache must maintain active idempotency keys with a 24-hour TTL, backed by a persistent PostgreSQL idempotency table.

## Pros and Cons of the Options

### Option 1: Offline-First Android Room + WorkManager + UUID Idempotency Keys

* Good, because associates can operate indefinitely in zero-connectivity refrigerated zones.
* Good, because deterministic UUID idempotency keys eliminate duplicate transaction hazards.
* Good, because local business validation provides instant UI feedback (< 50ms) for barcode scans and temperature checks.
* Bad, because client-side synchronization and conflict reconciliation require dedicated testing and state management.

### Option 2: Cloud Firestore Mobile SDK Offline Persistence

* Good, because offline document synchronization is handled automatically by the Google SDK.
* Bad, because complex relational transactions and atomic inventory ledger movements cannot be natively executed within Firestore.
* Bad, because SDK lacks customizable domain validation logic for hardware barcode scanner integration.

### Option 3: Online-Only Mobile Client

* Good, because mobile app implementation is simple without local database synchronization logic.
* Bad, because associates are blocked whenever stepping into cold-storage reserves or shielded dock areas, halting receiving operations.
* Bad, because network drops during transaction commit lead to uncertain state and duplicate scans.

## Links & References

* Official GCP Documentation: https://cloud.google.com/architecture/framework/reliability
* Official GCP Documentation: https://cloud.google.com/run/docs/configuring/request-timeout
* Related ADRs: ADR-0001, ADR-0002, ADR-0003, ADR-0004
