# [ADR-0003] Asynchronous Messaging & Ingestion: Google Cloud Pub/Sub and Cloud Tasks

* **Status**: accepted
* **Deciders**: Lead Cloud Architect, SecOps Architect, Tech Lead
* **Date**: 2026-09-15
* **Superseded by**: N/A
* **Approved-by**: npintaux

## Context and Problem Statement

Carrefour Stock Flow must absorb continuous high-velocity transaction streams, including real-time Point of Sale (POS) basket depletions (absorbing up to 15,000 events/second across 1,200 stores on peak Saturday rushes), EDI Advanced Shipping Notices (ASNs) from central SAP ERP, markdown notification broadcasts, and mobile audit records. Directly coupling POS registers and mobile barcode scanners to backend transactional databases causes thread pool exhaustion and cascading lock contention. We require an asynchronous, decoupled event-driven backbone that absorbs traffic bursts, guarantees at-least-once delivery, isolates failure domains, and enables rate-limited dispatch to legacy enterprise backends.

## Decision Drivers

* **High-Throughput Durability**: Buffer up to 15,000 events/sec during store peak hours without blocking POS checkout registers.
* **Loose Coupling & Fan-Out**: Broadcast stock updates simultaneously to store consoles, POS markdown engines, analytics pipelines, and SAP ERP.
* **Fault Isolation & Dead-Letter Queues (DLQ)**: Prevent poison-pill messages from blocking ingestion; isolate failed transactions for automated replay.
* **Rate-Controlled Downstream Dispatch**: Throttle outbound synchronization requests to prevent overwhelming legacy SAP Retail ERP endpoints.

## Considered Options

* **Option 1: Google Cloud Pub/Sub + Google Cloud Tasks** - Managed serverless event ingestion bus (Pub/Sub) with push/pull subscriptions and DLQ, combined with Cloud Tasks for rate-limited, scheduled execution against downstream enterprise systems.
* **Option 2: Self-Managed Apache Kafka on Compute Engine / GKE** - Distributed commit log cluster deployed and managed manually or via Strimzi operator.
* **Option 3: RabbitMQ Cluster on Compute Engine** - AMQP-based message broker with complex topic and exchange routing rules.

## Decision Outcome

Chosen option: **Option 1: Google Cloud Pub/Sub + Google Cloud Tasks**, because it is fully serverless, provides virtually limitless auto-scaling for peak store rushes, requires zero cluster or partition rebalancing maintenance, natively integrates with Cloud Run push endpoints, and supports Dead-Letter Topics (DLQ) and Cloud Tasks rate limiting.

### Positive Consequences

* **Buffer Against POS Spikes**: Checkout registers publish asynchronously to Pub/Sub within 10ms, decoupling customer checkout from stock database transaction locks.
* **Zero Infrastructure Overhead**: No Kafka brokers, Zookeeper/KRaft nodes, or broker storage partitions to patch, size, or balance.
* **Dead-Letter Resiliency**: Poison-pill messages or invalid ASN payloads automatically divert to a Dead-Letter Queue (DLQ) after 5 failed retries, with Cloud Monitoring alerts.
* **Controlled ERP Integration**: Cloud Tasks queues govern outbound calls to legacy SAP ERP, enforcing concurrency limits (e.g. max 50 concurrent requests) to avoid ERP downtime.

### Negative Consequences / Trade-offs

* **At-Least-Once Delivery**: Subscribers must handle potential duplicate messages (mitigated by enforcing UUID idempotency keys across all consumers).
* **Out-of-Order Message Arrival**: Standard Pub/Sub does not guarantee global ordering without ordering keys (mitigated by using Pub/Sub ordering keys based on `store_id:sku_id` for sequential stock adjustments).
* **Latency Profile**: Message transit time is typically 20–50ms (well within the contractual 5-second POS depletion requirement).

## Pros and Cons of the Options

### Option 1: Google Cloud Pub/Sub + Google Cloud Tasks

* Good, because it effortlessly absorbs 15,000+ events/sec burst traffic with zero manual provisioning.
* Good, because Cloud Tasks provides native rate-limiting, retry exponential backoff, and execution scheduling.
* Good, because it includes native Dead-Letter Queue support and IAM access control.
* Bad, because message consumers must implement idempotency to handle at-least-once delivery duplicates.

### Option 2: Apache Kafka on Compute Engine / GKE

* Good, because it provides strict partition ordering and long-term event log retention.
* Bad, because running 24/7 Kafka broker nodes incurs heavy baseline infrastructure costs violating the €45/store/month cap.
* Bad, because cluster partition management, rebalancing, and ZooKeeper/KRaft operations demand dedicated operational staff.

### Option 3: RabbitMQ Cluster

* Good, because AMQP provides sophisticated message routing keys, fanouts, and direct exchanges.
* Bad, because cluster scaling during peak retail surges is complex and prone to node queue memory exhaustion.
* Bad, because it requires continuous infrastructure management and patch automation.

## Links & References

* Official GCP Documentation: https://cloud.google.com/pubsub/docs
* Official GCP Documentation: https://cloud.google.com/tasks/docs
* Related ADRs: ADR-0001, ADR-0002, ADR-0005
