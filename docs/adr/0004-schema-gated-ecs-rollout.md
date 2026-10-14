# ADR 0004 — Rollout ECS condicionado à migration

- Status: Accepted
- Data: 2026-10-14

## Contexto

Uma definição de task nova pode depender de schema que ainda não existe. Um
`terraform apply` convencional atualizava `task_definition` das services ECS no
mesmo passo que registrava a definição de migration, permitindo que API,
worker ou scheduler iniciassem antes de `alembic upgrade head` concluir.

## Decisão

As services ECS ignoram alterações de `task_definition` no Terraform após sua
criação. O Terraform continua responsável por registrar task definitions e
infraestrutura. A promoção de API, worker e scheduler é feita por
`scripts/ecs-rollout.sh`: ele executa uma task Fargate de migration na rede
privada, aguarda o estado `STOPPED`, exige exit code `0` em todos os
containers e só então chama `update-service` com as definições imutáveis por
digest.

## Alternativas consideradas

| Alternativa | Decisão |
| --- | --- |
| Atualizar services no mesmo `terraform apply` | Rejeitada: não há dependência Terraform para o exit code de uma task ECS. |
| `local-exec` dentro do Terraform | Rejeitada: mistura credenciais operacionais, estado e uma operação imperativa não idempotente no apply. |
| Permitir rollout manual por console/CLI | Rejeitada como caminho normal: torna fácil pular a migration. |
| EKS/Kubernetes Jobs | Adiada: não justifica introduzir outra plataforma de orquestração. |

## Consequências

O pipeline de deploy precisa possuir permissão para `ecs:RunTask`,
`ecs:DescribeTasks` e `ecs:UpdateService` somente no cluster/services alvo.
Credenciais AWS, subnets reais, task-role policies e o primeiro bootstrap não
podem ser validados localmente; o runbook define os valores necessários.

O script é um guardrail versionado, não uma garantia contra uma credencial
privilegiada que execute comandos fora do processo. A conta deve restringir
quem pode atualizar as services diretamente.

## Validação

A sintaxe do script é checada na CI. Terraform valida que as services ignoram
drift de task definition e expõe os ARNs/nomes necessários. A execução real da
task continua bloqueada por acesso a uma conta AWS.
