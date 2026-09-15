# [ADR-0004] Authentication, Authorization & Departmental RBAC Partitioning

* **Status**: accepted
* **Deciders**: Lead Cloud Architect, SecOps Architect, Tech Lead
* **Date**: 2026-09-15
* **Superseded by**: N/A
* **Approved-by**: npintaux

## Context and Problem Statement

Carrefour Stock Flow must enforce strict departmental stock domain boundaries and hierarchical approval controls across diverse store personas (Receiving Dock Specialists, Section Managers, Stock Clerks, Quality Agents, Store Directors). In retail operations, staff cross-contamination—such as a Dry Grocery clerk adjusting Fresh Dairy inventory or unauthorized personnel writing off thousands of Euros in shrinkage—causes major financial discrepancies. The system requires federated enterprise single sign-on (SSO), short-lived OIDC/JWT tokens, row-level tenant and department isolation (`store_id`, `department_id`), and dual-key cryptographic authorization for adjustments exceeding €500.

## Decision Drivers

* **Enterprise Identity Federation**: Seamless integration with Carrefour corporate Identity Provider (Google Workspace / Okta IDP) via OpenID Connect (OIDC).
* **Fine-Grained Departmental Scoping (FR-3.1)**: Section Managers and clerks restricted strictly to their assigned store department IDs, rejecting out-of-scope adjustments with HTTP 403.
* **Dual-Key Authorization Thresholds (FR-3.2, US-2)**: Inventory write-offs exceeding €500 must transition to `PENDING_DIRECTOR_APPROVAL` requiring Store Director dual-sign-off.
* **Strict Store Tenant Isolation (FR-3.3)**: Row-Level Security (RLS) and API token validation ensuring zero cross-store data leakage.

## Considered Options

* **Option 1: Federated Google Cloud Identity / Okta OIDC + JWT Claims Validation + PostgreSQL Row-Level Security (RLS)** - Enterprise OIDC token issuance with custom token claims (`store_id`, `department_ids`, `roles`), verified at Cloud Run ingress, combined with application-level RBAC interceptors and PostgreSQL Row-Level Security.
* **Option 2: Standalone Custom OAuth2 / JWT Server** - Custom-built authorization service with local username/password or static API keys stored in a database.
* **Option 3: Basic HTTP Authentication & Shared API Keys** - Pre-shared static API keys distributed across Zebra handheld terminals and desktop clients.

## Decision Outcome

Chosen option: **Option 1: Federated Google Cloud Identity / Okta OIDC + JWT Claims Validation + PostgreSQL Row-Level Security (RLS)**, because it aligns with Carrefour enterprise identity standards, provides cryptographically verifiable short-lived tokens (1 hour expiry), enforces Zero Trust least privilege at both API and database layers, and supports multi-role claim attributes needed for departmental scoping and dual-sign-off workflows.

### Positive Consequences

* **Zero Hardcoded Credentials**: Mobile devices and web consoles authenticate using federated OIDC identity; tokens expire automatically after 60 minutes.
* **Deterministic Department Isolation**: JWT payload claims (`store_id`, `department_id`, `roles`) are validated on every API call; unauthorized cross-department modifications are rejected with HTTP 403 (`ERR_OUT_OF_SCOPE_DEPARTMENT`).
* **Dual-Key Enforcement**: Adjustments >= €500 automatically generate a cryptographic pending approval event, requiring Store Director role verification before ledger commit.
* **Defense-in-Depth**: Application RBAC checks combined with PostgreSQL tenant row-level security prevent any cross-store data exposure even during query errors.

### Negative Consequences / Trade-offs

* **Token Refresh Lifecycle**: Mobile scanners operating in offline cold rooms must renew tokens before entering offline zones, or support local cryptographic session validation.
* **JWT Size Overhead**: Embedding department lists and role claims into JWT increases request header size slightly (negligible over HTTP/2).
* **Identity Provider Dependency**: Carrefour Okta / Google Workspace IDP availability becomes critical for initial login (mitigated by token caching during active shifts).

## Pros and Cons of the Options

### Option 1: Federated Google Cloud Identity / Okta OIDC + JWT + RLS

* Good, because it leverages existing corporate Carrefour credentials and centralized account deprovisioning.
* Good, because short-lived signed tokens enforce least privilege with cryptographically tamper-proof claims.
* Good, because PostgreSQL RLS provides defense-in-depth against accidental data leakage across store tenants.
* Bad, because client applications must handle automatic token renewal workflows.

### Option 2: Standalone Custom OAuth2 Server

* Good, because authentication logic is completely self-contained within the application code.
* Bad, because managing user passwords, MFA, and credential rotations introduces high security liability and maintenance costs.
* Bad, because employees would need separate credentials from their standard corporate Carrefour accounts.

### Option 3: Basic HTTP Authentication & Shared API Keys

* Good, because implementation is trivial for scanner clients.
* Bad, because shared static keys violate Zero Trust, lack individual employee accountability, and pose catastrophic credential leak risks.
* Bad, because Revoking a compromised key requires re-imaging hundreds of Zebra devices simultaneously.

## Links & References

* Official GCP Documentation: https://cloud.google.com/iam/docs
* Official GCP Documentation: https://cloud.google.com/docs/authentication
* Related ADRs: ADR-0001, ADR-0002, ADR-0005
