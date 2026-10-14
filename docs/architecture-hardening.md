# Architecture Hardening

## Current cycle

Cycle 1 hardens the highest-risk paths in this order: tenant isolation, durable
asynchronous analysis, transaction boundaries, database invariants,
authentication, and deploy safety. This document records the implementation
state in the repository; a green local or CI run is required before a change is
treated as release evidence.

Final local validation for this cycle was recorded on 2026-10-14 against the
rebuilt Compose images: Alembic reached `0005_outbox_dispatch_lease`, Ruff
completed without findings, all 21 tests passed (including the PostgreSQL
contract test), and a real API-to-Redis-to-Celery-to-PostgreSQL analysis flow
completed successfully. This is local evidence, not evidence of an AWS
production rollout.

Status vocabulary:

- FOUND — reproduced or established by code inspection.
- IN_PROGRESS — remediation exists only in part or still needs validation.
- FIXED — remediation and a regression check are present in the repository.
- ACCEPTED_RISK — deliberately not implemented; the consequence is recorded.
- BLOCKED_EXTERNAL — completion needs infrastructure, an account, or an
  operational decision outside this repository.

## Findings

| ID | Severity | Component | Risk | Evidence | Action | Status |
| --- | --- | --- | --- | --- | --- | --- |
| AH-001 | P0 | Authentication | A missing ENVIRONMENT enabled the local bearer bypass because the application defaulted to development. | Former configuration default; CognitoTokenVerifier.verify. | Default application settings to production; make Compose opt into development explicitly; add regressions for missing environment and dev-token. | FIXED |
| AH-002 | P0 | Async worker | A worker could start without registering the analysis task and reject published work as unknown. | Celery task discovery relied on import side effects. | Explicitly include app.workers.ai_worker; test task registration without importing the API. | FIXED |
| AH-003 | P1 | Async consistency | A database commit followed by broker publication can split state and delivery; a relay without a persisted lease can also emit needless duplicates. | Original request path published directly after commit; migration 0005 and the relay implementation. | Persist state and durable job in one transaction; let Beat alone claim a persisted relay lease/token before every send, release it on synchronous broker failure, and recover stale leases periodically. | FIXED |
| AH-004 | P0 | Tenant isolation | A worker could locate an entity by globally known UUID without a tenant scope. | Original internal repository method and worker message contained only the entity ID. | Remove the unscoped port, put tenant_id and correlation_id in the durable job/message, and scope claim/complete/fail queries. | FIXED |
| AH-005 | P1 | Database integrity | Duplicate licitação business numbers could be inserted concurrently within one tenant. | No tenant_id, numero unique constraint. | Migration 0004_analysis_outbox adds the tenant-aware key after preflight checks; API maps the resulting conflict to HTTP 409. | FIXED |
| AH-006 | P0 | Cognito authorization | The application expected a tenant claim in a token mode that Cognito would not provide by default; self-registration could also make tenant assignment caller-controlled. | Terraform Cognito client/schema configuration. | Use Cognito ID tokens, make custom:tenant_id immutable, remove it from writable attributes, and require administrative user creation. | FIXED |
| AH-007 | P1 | Cloud secrets and networking | ECS tasks using CMK-encrypted Secrets Manager values could fail to start; database and Redis ingress was broader than the workload boundary. | ECS execution policy and VPC security groups. | Grant constrained kms:Decrypt via Secrets Manager and replace VPC-CIDR ingress with service-SG-to-SG rules. | FIXED |
| AH-008 | P1 | Deployment | A normal Terraform apply could update ECS services before a migration task had succeeded. | ECS services tracked task_definition directly. | Terraform now ignores task-definition rollout drift; scripts/ecs-rollout.sh runs and verifies the migration task before promoting API, worker and scheduler. CI checks its syntax. | FIXED |
| AH-009 | P1 | Cache resilience | A Redis failure after a successful database write could turn a committed creation into a client-visible error; cached report data could be treated as authoritative. | Create/report use cases. | Make report cache reads, writes, and invalidation best effort; validate cached tenant identity and fall back to PostgreSQL. | FIXED |
| AH-010 | P2 | Observability | API and worker failures lacked a common request/job correlation trail and readiness did not prove dependencies were live. | Logging and health entry points. | Add JSON event helper, generated/validated X-Request-ID, tenant/job/correlation fields for critical events, and ready checks for PostgreSQL and Redis. | FIXED |
| AH-011 | P2 | Architecture boundaries | The architecture test could miss forbidden imports in nested packages and did not protect the application layer. | Previous shallow source scan. | Recursively parse app/domain and app/application ASTs; reject framework and outer-adapter imports. | FIXED |
| AH-012 | P2 | Integration coverage | SQLite cannot faithfully validate PostgreSQL locks and composite foreign keys. | tests/conftest.py and the former unit-only suite. | Add a PostgreSQL contract test gated by RUN_POSTGRES_INTEGRATION=1; run it in Compose and CI after Alembic reaches head. | FIXED |
| AH-013 | P2 | Defense in depth | A repository regression could bypass application tenant predicates because PostgreSQL Row Level Security is not enabled. | Shared-schema model and migrations. | Record the shared-schema strategy and defer RLS until connection/session-variable semantics, admin access, and migration rollout are designed and tested. | ACCEPTED_RISK |
| AH-014 | P2 | Worker capacity | Worker autoscaling uses CPU, which is not a reliable proxy for queue backlog or oldest durable job age. | Terraform ECS autoscaling policies. | Add queue-age/backlog metrics and a target/step policy only after the metric pipeline and operational thresholds are agreed. | ACCEPTED_RISK |
| AH-015 | P1 | Terraform rollout | Environment-qualified resource names and TLS/database changes can replace or reboot real resources if applied to an existing estate without a migration plan. | Terraform resource naming, RDS parameters, ACM listener changes. | Require a reviewed terraform plan, backup/cutover window, real-RDS TLS verification, and migration task completion before rollout. | BLOCKED_EXTERNAL |
| AH-016 | P1 | Terraform state | Generated RDS/Redis/Cognito secrets are stored in Terraform state. | Terraform resources and state semantics. | Declare an S3 backend and ship an ignored backend.hcl template; bootstrap the encrypted bucket, lock table and restrictive IAM policy in the target organization before apply. | BLOCKED_EXTERNAL |

## Changes implemented

- Fail-closed environment default with an explicit local-development override.
- Tenant claim/header authorization at the HTTP boundary and a TenantId value
  object throughout domain and repository ports.
- Tenant-scoped persistence queries plus composite database constraints that
  prevent an analysis job from referencing another tenant's licitação.
- A durable analysis job lifecycle (PENDING, PROCESSING, COMPLETED, FAILED),
  execution claim token, bounded retry metadata, and a periodic relay.
- Migration 0005 adds a separate relay lease/token: Beat claims it before
  sending, releases it after synchronous broker failure, and retries stale leases
  without treating the Redis message as source of truth.
- Atomic completion/failure updates for the job record and business state.
- Cache-as-optimization behavior rather than cache-as-source-of-truth.
- Migration 0004_analysis_outbox with data preflight guards, tenant business
  uniqueness, checks, and dispatch indexes.
- Container startup ordering around a one-shot migration service, a dedicated
  Celery Beat service, non-root runtime user, and readiness probing.
- CI checks for lint, migrations against PostgreSQL, architecture tests,
  application tests, runtime-image build, and Terraform syntax/format.
- ECS/IAM/Terraform hardening for TLS, CMK-backed runtime secrets,
  environment-scoped resource names, private tasks, and SG-to-SG data access.
- Loopback-only Docker Compose port bindings, immutable OCI digest validation,
  and a schema-gated ECS rollout script that Terraform cannot bypass through a
  service task-definition update.
- Final local runtime validation: healthy API/PostgreSQL/Redis/worker/beat,
  migration task exit code 0, `/ready` and `/docs` HTTP 200, and a real
  tenant-bound analysis job completed with both relay and execution leases
  cleared.

## Tests added

- Authentication regressions for the development bypass default and defensive
  handling of incomplete settings objects.
- Negative cross-tenant read and analysis-trigger tests.
- Tenant-local business-key uniqueness test.
- Worker task-registration and duplicate-delivery/idempotent-claim tests.
- Cache outage, relay broker-publication failure recovery, relay lease,
  abandoned-execution budget and durable terminal-failure tests.
- PostgreSQL contract test for tenant business uniqueness, composite FK and
  tenant-scoped outbox locking.
- Recursive domain/application import-boundary test.

The authoritative release command remains:

~~~bash
docker compose exec -T app pytest -v
~~~

For the integration evidence that unit tests do not replace, use the smoke
procedure in [RUNBOOK.md](RUNBOOK.md) after the Compose services are healthy.

## Remaining risks

- The relay is at-least-once, not exactly-once. The persisted relay lease
  suppresses normal duplicate publication, but a crash after Redis accepts a
  message and before the lease is cleared can intentionally result in a safe
  duplicate delivery after lease expiry.
- The claim token makes duplicate state transitions harmless for the
  implemented workflow, but a future external LLM adapter must itself be
  idempotent or receive a stable idempotency key.
- The current analysis body is a two-second simulation. Timeout, cancellation,
  payload retention, and supplier-specific retry behavior must be designed
  before a real LLM is connected.
- PostgreSQL RLS is not enabled. Tenant predicates, foreign keys, constraints,
  and tests are the active protection layers.
- The API has no list pagination or request-rate limiting yet; both matter
  before exposing an internet-facing public workload.
- No CloudWatch alarm, queue-age metric, WAF policy, bootstrapped remote
  Terraform backend, or production Terraform apply is established in this
  repository. An S3 backend template exists, but its bucket and IAM ownership
  must be created externally.
- Docker and CI dependency versions are bounded but not lock-file pinned; a
  repeatable release process should add an audited lock strategy.

## Next cycle

1. Add deterministic fault-injection coverage for Redis/broker outage, retry,
   and abandoned relay/execution-lease recovery in a containerized environment.
2. Design metrics/alarms for durable job age, failure/retry rate, readiness,
   and database connection pressure.
3. Review a non-destructive Terraform plan in the target AWS account before
   treating the infrastructure changes as deployed.
