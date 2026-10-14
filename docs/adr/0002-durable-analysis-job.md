# ADR 0002 — Job durável para análise assíncrona

- Status: Accepted
- Data: 2026-10-14

## Contexto

O fluxo de análise tinha duas escritas independentes: confirmar a mudança no
PostgreSQL e publicar no Redis/Celery. Uma falha entre elas deixava uma
licitação em análise sem trabalho recuperável. Redis e Celery fornecem entrega
at-least-once, portanto uma entrega duplicada ou um crash do worker também são
falhas normais, não exceções improváveis.

## Decisão

Uma solicitação de análise grava a mudança de estado da licitação e um
analysis_job tenant-bound na mesma transação PostgreSQL. A requisição HTTP não
publica no broker: após o commit, o dispatcher periódico do Beat encontra o
trabalho pendente e tenta publicá-lo. Assim, indisponibilidade ou lentidão de
Redis não bloqueia o event loop da API.

O consumidor recebe job_id, tenant_id e correlation_id. Antes do trabalho, ele
reivindica transacionalmente o job e recebe lock_token. Somente o detentor
desse token pode completar ou falhar a tentativa. Conclusão da licitação e
marcação de COMPLETED são gravadas na mesma transação.

O modelo é at-least-once. A migration 0005 adiciona dispatch_locked_at e
dispatch_token persistidos. O Beat reivindica o token antes de publicar; uma
falha síncrona libera a lease e uma queda do relay é recuperada quando ela
expira. Isso não deve ser descrito como exactly-once.

## Alternativas consideradas

| Alternativa | Decisão |
| --- | --- |
| Publicar antes do commit | Rejeitada. Worker pode não encontrar a linha ainda não confirmada. |
| Publicar depois do commit sem registro durável | Rejeitada. Uma falha de broker perde o trabalho. |
| Transação distribuída entre PostgreSQL e Redis | Rejeitada. Complexidade e fragilidade não justificadas para o monólito atual. |
| SQS/EventBridge imediatamente | Adiada. Pode ser adequado no futuro, mas não remove a necessidade de outbox, idempotência e operações AWS. |

## Consequências

Há mais estado operacional: PENDING, PROCESSING, COMPLETED e FAILED, tentativas,
leases, erro e timestamps devem ser observáveis e ter política de retenção.

O placeholder de IA atual é local. Um adaptador LLM futuro deve usar job_id
como chave de idempotência, ou manter um registro transacional do efeito
externo. Um crash após uma chamada externa e antes do commit ainda pode repetir
essa chamada sem essa proteção.

Uma única instância de Beat evita publicação redundante deliberada, mas o
worker deve continuar seguro sob mensagens duplicadas, mensagens atrasadas e
reentrega após crash.

## Validação

Há testes para registro durável, falha de publicação pelo relay, registro das
tasks, job tenant-bound, lease de relay, entrega duplicada, orçamento de crash
e contrato PostgreSQL. A validação operacional final inclui um smoke real com
PostgreSQL, Redis, worker e Beat.
