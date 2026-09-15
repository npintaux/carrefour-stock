# [ADR-0001] Serverless Compute Platform Selection: Google Cloud Run

* **Status**: accepted
* **Deciders**: Lead Cloud Architect, SecOps Architect, Tech Lead
* **Date**: 2026-09-15
* **Superseded by**: N/A
* **Approved-by**: npintaux

## Context and Problem Statement

Carrefour Stock Flow operates across 1,200 supermarket and hypermarket locations, managing store inventory from early morning receiving (05:00 CET) to store closing (23:00 CET). Supermarket workload exhibits extreme diurnality: during peak shopping and restocking hours (06:00 - 21:00), the system experiences high concurrency and barcode scanning traffic, whereas traffic drops to near zero between 00:00 and 05:00. The architecture requires a compute platform that scales dynamically, satisfies the contractual NFR budget ceiling (<= €45/month/store instance), maintains regional multi-zone high availability (99.95% SLO), and minimizes idle carbon footprint in alignment with Carrefour sustainability goals.

## Decision Drivers

* **Diurnal Auto-scaling & Cost Efficiency**: Ability to scale down to zero during closed store hours (00:00 - 05:00) to keep compute costs <= €45/store/month.
* **Operational Simplicity**: Minimize container orchestration overhead, node lifecycle maintenance, and cluster patching across hundreds of store microservices.
* **Regional High Availability**: Native multi-zone container execution across 3 zones in `europe-west9` (Paris) with automatic health checking and traffic migration.
* **Low Carbon Footprint**: Low-idle energy consumption maximizing Carbon-Free Energy (CFE) utilization.

## Considered Options

* **Option 1: Google Cloud Run (Fully Managed Serverless Containers)** - Containerized microservices executed on Google's managed serverless infrastructure with auto-scaling to zero and per-100ms billing.
* **Option 2: Google Kubernetes Engine (GKE Autopilot / Standard)** - Managed Kubernetes cluster with dedicated worker node pools running across multiple availability zones.
* **Option 3: Google Compute Engine (GCE Managed Instance Groups)** - Traditional virtual machine instances configured in autoscaling MIGs behind an External Application Load Balancer.

## Decision Outcome

Chosen option: **Option 1: Google Cloud Run (Fully Managed Serverless Containers)**, because it natively satisfies diurnality via automatic scale-to-zero, eliminates node pool maintenance, guarantees multi-zone regional resiliency across Google infrastructure, and achieves the lowest carbon footprint and operational cost.

### Positive Consequences

* **Sub-Second Scale-to-Zero**: Zero compute charges during store non-operating hours (00:00 to 05:00), easily meeting the €45/month budget ceiling.
* **Zero Infrastructure Management**: No Kubernetes control plane or node upgrades, kernel patches, or capacity planning required.
* **Native Multi-Zone Fault Tolerance**: Cloud Run automatically distributes container instances across multiple zones within the region (`europe-west9`).
* **Direct Integration**: Native integration with Cloud IAM, Workload Identity, Secret Manager, Cloud Logging, and Google Cloud Armor.

### Negative Consequences / Trade-offs

* **Cold Starts**: Initial invocation from 0 instances can introduce a 300–800ms latency spike (mitigated by configuring `min-instances=2` during active store operational hours 05:00–23:00).
* **Execution Duration Cap**: Maximum request timeout of 60 minutes (not an issue for sub-second API requests, while long background batches use Cloud Tasks or Pub/Sub).
* **State Statelessness**: Containers cannot maintain local persistent disks; all state must reside in Cloud SQL, Memorystore Redis, or Cloud Storage.

## Pros and Cons of the Options

### Option 1: Google Cloud Run

* Good, because it scales to zero during closed store hours, eliminating idle compute spend.
* Good, because it provides fully managed multi-zone redundancy without cluster maintenance overhead.
* Good, because it provides native integration with Secret Manager, Cloud IAM, and Cloud Trace.
* Bad, because cold starts require configured `min-instances` during daytime store operational hours.

### Option 2: Google Kubernetes Engine (GKE)

* Good, because it offers rich orchestration primitives, daemonsets, and custom networking topologies.
* Good, because it allows long-running daemon processes and complex stateful container workloads.
* Bad, because idle worker nodes and cluster management fees incur continuous baseline costs (€70+/month minimum), breaching the store cost budget.
* Bad, because it introduces significant operational maintenance, node upgrades, and YAML manifest complexity.

### Option 3: Google Compute Engine (GCE Managed Instance Groups)

* Good, because it provides complete OS-level control and customized kernel configurations.
* Bad, because VM autoscaling reactions are slow (minutes vs seconds for containers), risking latency spikes during sudden rush-hour traffic.
* Bad, because OS patching, disk sizing, and base image management create substantial administrative toil.

## Links & References

* Official GCP Documentation: https://cloud.google.com/run/docs
* Related ADRs: ADR-0002, ADR-0003, ADR-0004, ADR-0005
