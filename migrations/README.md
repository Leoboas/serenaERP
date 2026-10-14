# Migrações Alembic

As migrações são parte do contrato de implantação do SerenaERP. Não altere
manualmente um banco compartilhado para compensar uma migration: registre a
mudança em uma revisão Alembic, valide-a em PostgreSQL e promova-a pelo gate de
migration.

## Fluxo local

~~~bash
docker compose up -d --build
docker compose exec -T app alembic upgrade head
docker compose exec -T app alembic current --check-heads
~~~

O serviço migrate do Compose executa alembic upgrade head antes de app, worker
e beat; o comando manual acima é seguro para confirmar que a base já está no
head.

## Revisões atuais

| Revisão | Finalidade |
| --- | --- |
| 0001_initial | Schema inicial de tenants e licitações. |
| 0002_licitacoes_reporting_indexes | Índices de consultas de relatório. |
| 0003_default_tenant_seed | Tenant local de desenvolvimento, inserido de modo idempotente. |
| 0004_analysis_outbox | Job durável de análise, integridade tenant-aware e constraints de domínio. |
| 0005_outbox_dispatch_lease | Lease e token recuperáveis para impedir publicação concorrente do mesmo outbox record. |

## Cuidados de rollout

0004_analysis_outbox faz verificações prévias e falha em vez de reescrever
dados históricos quando encontra valor não positivo, status desconhecido ou
duplicidade de tenant_id, numero. As chaves únicas são construídas
concorrentemente com `lock_timeout`; checks são adicionados como `NOT VALID` e
depois validados. Se uma tentativa for interrompida após criar um índice válido,
o rerun o reutiliza; um índice inválido é descartado antes da nova tentativa.
Corrija dados inválidos com um plano auditável antes de tentar novamente.

0005_outbox_dispatch_lease adiciona somente colunas nulas e uma constraint de
coerência entre token e instante da lease. A revisão é transacional e usa
`lock_timeout`, portanto falha sem deixar colunas/indexes parciais se não puder
obter a janela de DDL. Registros existentes continuam recuperáveis pelo
dispatcher após o upgrade.

Em ECS, execute uma única task de migration e espere o código de saída 0 antes
de implantar as novas tasks de API/worker. O procedimento operacional está em
[docs/RUNBOOK.md](../docs/RUNBOOK.md).

Evite downgrade automático em produção: remover constraints ou a tabela de
jobs pode descartar evidências de processamento pendente. Faça backup,
avalie compatibilidade de código e use um plano de reversão específico.
