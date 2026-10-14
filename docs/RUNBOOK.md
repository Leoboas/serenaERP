# Runbook operacional

## Princípios de resposta

1. Preserve evidência antes de tentar corrigir: horário, request ID,
   correlation ID, job ID, tenant ID, task/container ID e erro sanitizado.
2. Não use Redis como fonte de verdade e não execute FLUSHALL para tentar
   corrigir fila parada.
3. Não apague analysis_jobs, tabelas ou volumes para mascarar uma falha.
4. Não faça downgrade automático de migration em ambiente compartilhado.
5. Quando houver dúvida sobre isolamento, interrompa apenas o fluxo afetado e
   trate o incidente como potencial P0 até haver evidência em contrário.

## Verificação local inicial

Use PowerShell no Windows:

~~~powershell
docker compose up -d --build
docker compose ps
docker compose exec -T app alembic current --check-heads
docker compose exec -T app pytest -v
Invoke-WebRequest http://localhost:8000/health
Invoke-WebRequest http://localhost:8000/ready
docker compose logs --tail=100 app worker beat migrate
~~~

O endpoint health responde apenas que o processo HTTP está vivo. O endpoint
ready também exige PostgreSQL e Redis acessíveis. Em Compose, app, worker e
beat aguardam a task migrate concluir com sucesso.

## Smoke test: CRUD, tenant e análise

O ambiente local precisa ter ENVIRONMENT=development. Não use este token fora
do host local.

~~~powershell
$tenant = "00000000-0000-0000-0000-000000000001"
$headers = @{ Authorization = "Bearer dev-token"; "X-Tenant-ID" = $tenant }
$payload = @{ numero = "SMOKE-$([guid]::NewGuid().ToString('N').Substring(0, 8))"; descricao = "Smoke test local"; valor_estimado = "1000.00" } | ConvertTo-Json
$created = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/licitacoes/" -Headers $headers -ContentType "application/json" -Body $payload
$requested = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/licitacoes/$($created.id)/analisar-ia" -Headers $headers
$deadline = (Get-Date).AddSeconds(50)
do {
  Start-Sleep -Seconds 2
  $final = Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/licitacoes/$($created.id)" -Headers $headers
} while ($final.status -eq "EM_ANALISE_IA" -and (Get-Date) -lt $deadline)
if ($final.status -eq "EM_ANALISE_IA") { throw "Tempo limite aguardando o relay Beat e o worker" }
$created
$requested
$final
docker compose logs --tail=200 worker beat
~~~

Expected evidence:

- Create returns HTTP 201.
- Analysis request returns HTTP 200 with status EM_ANALISE_IA.
- Worker logs contain a registered process task and a completed-analysis event.
- Final GET becomes ANALISADO for the payload above, or ALERTA_RISCO for a
  value above one million.
- The response includes X-Request-ID; preserve it with the job ID from logs.

For a negative isolation check, create with tenant A and then request the same
resource using a token/header for tenant B. Read and analysis request must
return 404; tenant B must not be able to alter the state of tenant A.

## Inspecting durable analysis state

For local diagnosis only:

~~~powershell
docker compose exec -T postgres psql -U goverp -d goverp -c "SELECT tenant_id, status, attempt_count, available_at, dispatch_locked_at, locked_at, completed_at, left(coalesce(last_error, ''), 160) AS last_error FROM analysis_jobs ORDER BY created_at DESC LIMIT 20;"
~~~

Interpretation:

| State | Meaning | Safe next action |
| --- | --- | --- |
| PENDING | Committed work awaits publisher/worker or retry time. | Check Beat, Redis and available_at; do not delete it. |
| PROCESSING | A worker holds a claim. | Check locked_at, worker logs and timeout. Let the lease recovery path operate unless the worker is conclusively gone. |
| COMPLETED | Business state and job completion were committed together. | Investigate output only if the resulting licitação status is unexpected. |
| FAILED | Retries were exhausted or the target state was incompatible. | Preserve last_error and correlate with worker logs before choosing a business retry. |

The relay uses a persisted dispatch token/lease. A synchronous publish failure
releases it immediately; a relay crash is recovered when the lease expires.
The transport remains at-least-once, so the worker claim path must continue to
neutralize duplicate delivery.

## Incident: worker does not process a task

1. Confirm process health and task registration:

   ~~~powershell
   docker compose ps
   docker compose logs --tail=200 worker beat redis
   docker compose exec -T worker celery -A app.workers.celery_app inspect ping
   ~~~

2. Verify that worker logs list serenaerp.analysis.process and
   serenaerp.analysis.dispatch_pending at startup.
3. Inspect analysis_jobs. A PENDING record is durable evidence that API
   transaction succeeded even if publication failed.
4. Verify Redis and the worker broker URL, including that cache, broker and
   result backend use their intended logical databases.
5. If Beat is down, restore it. It relays pending work periodically; manually
   invoking business code or inserting a replacement job is not the recovery
   procedure.
6. If a task is PROCESSING beyond the configured lease timeout, collect worker
   exit evidence. The reclaim flow is designed for abandoned leases; avoid
   forcing duplicate execution before observing the claim behavior.

Escalate if a job for one tenant is associated with another tenant ID, if a
completed job did not produce a matching tenant-scoped business update, or if
the same external side effect appears twice.

## Incident: Redis unavailable

Symptoms:

- ready returns HTTP 503;
- cache warnings appear;
- Beat publication can fail while the database transaction remains durable.

Actions:

1. Check Redis health and connectivity, not just the API process:

   ~~~powershell
   docker compose ps redis
   docker compose logs --tail=200 redis app worker beat
   docker compose exec -T redis redis-cli ping
   ~~~

2. Restore Redis before expecting new Celery work to execute.
3. After restoration, inspect PENDING jobs and Beat/worker logs. Durable jobs
   should be relayed; do not recreate licitações merely because cache or broker
   was unavailable.
4. Confirm a report falls back to PostgreSQL rather than accepting stale cache
   as truth.

## Incident: PostgreSQL unavailable or connections exhausted

Symptoms include ready 503, migration failure, DB driver errors, or stalled
requests. Local diagnosis:

~~~powershell
docker compose logs --tail=200 postgres app worker
docker compose exec -T postgres psql -U goverp -d goverp -c "SELECT state, count(*) FROM pg_stat_activity WHERE datname = 'goverp' GROUP BY state;"
~~~

Actions:

1. Stop rollout; do not restart database containers or delete volumes as a
   first action.
2. Check database health, capacity, active sessions and application connection
   behavior.
3. Treat an incomplete migration as a deployment blocker. Inspect Alembic
   revision and database logs before retrying.
4. After recovery, verify current head and run the smoke test. The worker can
   resume durable jobs only after both database and Redis are healthy.

## Incident: migration failed

1. Capture migration container/task logs and the exact Alembic revision.
2. Run current head inspection; do not infer success from a restarted API:

   ~~~powershell
   docker compose logs --tail=300 migrate
   docker compose exec -T app alembic current
   docker compose exec -T app alembic heads
   ~~~

3. For 0004_analysis_outbox, inspect and remediate preflight data issues
   (non-positive values, invalid statuses, duplicate tenant business numbers)
   using an approved data-fix plan.
4. Do not use a downgrade as a generic recovery mechanism. Restore from backup
   or perform a forward-compatible corrective migration if needed.
5. Resume API/worker deployment only after migration exits with code 0 and
   current reports a single expected head.

## Incident: API unhealthy

| Signal | Interpretation | First check |
| --- | --- | --- |
| health fails | HTTP process is not responding. | Container/task lifecycle and application logs. |
| health passes, ready fails | Process lives but PostgreSQL or Redis dependency is unavailable. | Database/Redis connectivity and credentials. |
| ALB target unhealthy | Readiness endpoint, task security group, private subnet route, logs. | Target group health reason and ECS stopped-task reason. |
| Repeated 401/403 | Authentication/tenant claim mismatch. | Token type, issuer, audience, token_use and header claim equality. |

Never return stack traces, connection strings or JWTs to callers while
diagnosing an API failure.

## Suspected incorrect tenant data

1. Record the reported tenant ID, resource UUID, request ID and timestamps.
2. Confirm the request token claim and X-Tenant-ID from sanitized gateway/API
   evidence.
3. Query the resource only through a controlled, audited support procedure
   that includes tenant_id. Do not use an unscoped UUID lookup.
4. Inspect the matching analysis job by both job ID and tenant ID.
5. Preserve logs and stop any affected asynchronous flow if cross-tenant access
   is plausible. Escalate as P0.

## ECS migration gate

Terraform registers new task definitions but intentionally ignores
`task_definition` drift on the three long-running ECS services. Do not promote
them with a direct `aws ecs update-service`: use the versioned gate below after
the reviewed Terraform apply. It runs the one-shot migration, requires every
container to exit 0, and only then updates API, worker and scheduler.

~~~bash
export ECS_CLUSTER="$(terraform -chdir=terraform output -raw ecs_cluster_name)"
export ECS_MIGRATION_TASK_DEFINITION="$(terraform -chdir=terraform output -raw ecs_migration_task_definition_arn)"
export ECS_API_TASK_DEFINITION="$(terraform -chdir=terraform output -raw ecs_api_task_definition_arn)"
export ECS_WORKER_TASK_DEFINITION="$(terraform -chdir=terraform output -raw ecs_worker_task_definition_arn)"
export ECS_SCHEDULER_TASK_DEFINITION="$(terraform -chdir=terraform output -raw ecs_scheduler_task_definition_arn)"
export ECS_API_SERVICE="$(terraform -chdir=terraform output -raw ecs_api_service_name)"
export ECS_WORKER_SERVICE="$(terraform -chdir=terraform output -raw ecs_worker_service_name)"
export ECS_SCHEDULER_SERVICE="$(terraform -chdir=terraform output -raw ecs_scheduler_service_name)"
export ECS_SERVICE_SECURITY_GROUP_ID="$(terraform -chdir=terraform output -raw ecs_service_security_group_id)"
# Comma-separated private subnet IDs from `terraform output private_subnet_ids`.
export ECS_PRIVATE_SUBNET_IDS="subnet-REPLACE_ME,subnet-REPLACE_ME"
bash scripts/ecs-rollout.sh
~~~

For the very first environment bootstrap, run the migration task as soon as
the task definitions exist and before allowing traffic to the services. This
procedure requires AWS credentials, real private subnet IDs and a deployment
role; it cannot be exercised from this repository alone.

## Bootstrap do state Terraform

Não execute um apply usando state local compartilhado. Um administrador da
conta deve criar primeiro o bucket S3 cifrado, a tabela de lock e a política
IAM restrita. Depois, copie o template versionado para um arquivo ignorado e
inicialize o backend:

~~~bash
cp terraform/backend.hcl.example terraform/backend.hcl
# Edite os placeholders com valores da organização; não comite o arquivo.
terraform -chdir=terraform init -backend-config=backend.hcl
terraform -chdir=terraform plan
~~~

Se houver state local anterior, siga um plano de migração aprovado e registre o
resultado de `terraform init -migrate-state`; não apague o state como forma de
resolver conflito.

## Capacity and observability follow-up

Track at minimum:

- HTTP p50/p95 latency and 4xx/5xx rate;
- ready failures by dependency;
- database connection count/latency;
- count and age of PENDING analysis jobs;
- PROCESSING lease age;
- worker duration, failure rate and retry rate;
- cache errors and cache hit rate.

CPU-only worker scaling is not a queue-backlog strategy. Do not set production
thresholds until these signals are emitted, retained and tested under load.
