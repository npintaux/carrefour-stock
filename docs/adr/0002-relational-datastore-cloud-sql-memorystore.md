# [ADR-0002] Primary Datastore & Caching Architecture: Cloud SQL PostgreSQL and Memorystore Redis

* **Status**: accepted
* **Deciders**: Lead Cloud Architect, SecOps Architect, Tech Lead
* **Date**: 2026-09-15
* **Superseded by**: N/A
* **Approved-by**: npintaux

## Context and Problem Statement

Carrefour Stock Flow manages stock inventory across 15,000 to 60,000 active SKUs per store. Stock movements, inbound receipts, and shelf replenishment require strict ACID transactional guarantees: two clerks replenishing the same reserve bin or claiming identical inventory lots must not cause phantom balances or negative stock anomalies. Simultaneously, thousands of continuous mobile barcode lookups per minute demand sub-second read latency (P95 < 120ms, P99 < 250ms). We need a datastore architecture that guarantees ACID isolation, supports complex relational models (hierarchy of Store -> Department -> Zone -> Aisle -> Bin -> Batch/Lot), and provides ultra-low latency caching.

## Decision Drivers

* **ACID Transactions & Row-Level Locking**: Strict consistency for inventory balances, preventing double-allocation and race conditions during simultaneous picks and receipts.
* **Low Read Latency**: Sub-10ms lookup times for frequent barcode EAN-13 and SSCC pallet queries across mobile handhelds.
* **Regional High Availability**: Sub-minute RPO (< 1 min) and low RTO (< 15 min) with automated regional failover in `europe-west9`.
* **Cost Predictability**: Economical database sizing compliant with the monthly €45/store ceiling while accommodating peak Saturday surges.

## Considered Options

* **Option 1: Hybrid Cloud SQL PostgreSQL (Enterprise Plus Regional HA) + Memorystore Redis** - Fully managed PostgreSQL with multi-zone standby replication, paired with Memorystore Redis as a look-aside cache for hot barcode and session queries.
* **Option 2: Google Cloud Spanner** - Globally distributed, horizontally scalable NewSQL relational database with external consistency and multi-region replication.
* **Option 3: Google Cloud Firestore (Datastore mode)** - Serverless NoSQL document database providing document-level transactions and flexible JSON schemas.

## Decision Outcome

Chosen option: **Option 1: Hybrid Cloud SQL PostgreSQL (Enterprise Plus Regional HA) + Memorystore Redis**, because it provides robust ACID transactions and row-level locking needed for inventory ledgers, integrates natively with mature relational ORMs, enables read offloading via Redis to meet P95 < 120ms, and fits within the budget constraints.

### Positive Consequences

* **Strict ACID Concurrency**: Row-level locking (`SELECT FOR UPDATE`) prevents phantom stock and inventory over-allocation during concurrent mobile operations.
* **High-Throughput Read Caching**: Memorystore Redis offloads up to 90% of barcode lookup queries, achieving sub-10ms response times.
* **Automated Regional High Availability**: Cloud SQL Enterprise Plus provides synchronous replication across dual zones with 99.99% availability and sub-minute failover.
* **Data Sovereignty & Encryption**: Customer-Managed Encryption Keys (CMEK) via Cloud KMS and IAM database authentication for zero hardcoded credentials.

### Negative Consequences / Trade-offs

* **Connection Overhead**: Serverless Cloud Run instances can exhaust PostgreSQL connection limits if not managed (mitigated using Cloud SQL Auth Proxy and built-in connection pooling).
* **Cache Invalidation Complexity**: Look-aside cache requires proactive invalidation on stock transfer commits.
* **Horizontal Scaling Limits**: Unlike Cloud Spanner, Cloud SQL scales vertically; high-volume reporting must be directed to read replicas.

## Pros and Cons of the Options

### Option 1: Hybrid Cloud SQL PostgreSQL + Memorystore Redis

* Good, because it delivers true relational integrity, foreign keys, and ACID transactional guarantees essential for inventory ledgers.
* Good, because Memorystore Redis delivers sub-10ms cache latency, easily beating the P95 < 120ms NFR target.
* Good, because cost is predictable and cost-effective for regional retail deployments.
* Bad, because connection pooling must be managed between serverless Cloud Run and Cloud SQL.

### Option 2: Google Cloud Spanner

* Good, because it provides limitless horizontal scale and global multi-region replication.
* Bad, because minimum node provisioning costs (~$0.90/hour or ~$650/month per node) vastly exceed the target store cost envelope.
* Bad, because global distributed consensus introduces unnecessary write latency overhead for single-store retail operations.

### Option 3: Google Cloud Firestore

* Good, because it offers serverless scale-to-zero and seamless mobile client synchronization.
* Bad, because multi-document ACID transactions and complex analytical queries (e.g. variance calculations across thousands of SKUs) are constrained and expensive.
* Bad, because NoSQL lacks enforced relational schemas and foreign keys, increasing the risk of stock ledger inconsistencies.

## Links & References

* Official GCP Documentation: https://cloud.google.com/sql/docs/postgres
* Official GCP Documentation: https://cloud.google.com/memorystore/docs/redis
* Related ADRs: ADR-0001, ADR-0003, ADR-0005
