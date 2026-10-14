# Arquitetura SerenaERP

## Escopo e estado real

SerenaERP é um monólito modular para gestão de licitações municipais. O núcleo
de negócio é organizado em domínio e casos de uso; HTTP, SQLAlchemy, Redis,
Celery, Cognito e AWS são adaptadores de borda. A infraestrutura AWS descrita
por Terraform é um alvo de implantação, não evidência de que uma conta de
produção já esteja provisionada.

O diagrama abaixo representa o fluxo implementado, incluindo o registro
durável de análise. A publicação assíncrona é at-least-once; não há promessa de
exactly-once.

~~~mermaid
flowchart LR
    Client[Cliente] --> API[FastAPI]
    API --> Auth[JWT Cognito e tenant claim]
    Auth --> UseCase[Casos de uso]
    UseCase --> Domain[Domínio: regras e TenantId]
    UseCase --> Ports[Portas: repositório, cache e jobs]
    Ports --> PG[(PostgreSQL)]
    Ports --> Redis[(Redis cache)]
    PG --> Jobs[analysis_jobs durável]
    Jobs --> Relay[Relay do Celery Beat]
    Relay --> Broker[(Redis broker)]
    Broker --> Worker[Celery worker]
    Worker --> PG
~~~

## Mapa dos componentes

| Área | Implementação | Responsabilidade |
| --- | --- | --- |
| Entrada HTTP | app/main.py, app/api | FastAPI, validação de request, autenticação, roteamento e códigos HTTP. |
| Domínio | app/domain | Entidades, estados de licitação, TenantId, AnalysisJob e contratos abstratos. |
| Aplicação | app/application | Casos de uso e DTOs; orquestra portas sem conhecer frameworks. |
| Persistência | app/infrastructure/persistence | SQLAlchemy async, mapeamento ORM e transações PostgreSQL. |
| Cache | app/infrastructure/cache.py, app/infrastructure/redis.py | Redis para relatórios; não é fonte de verdade. |
| Mensageria | app/workers/ai_worker.py | Relay periódico que lê o outbox durável e publica jobs tenant-bound no Celery. |
| Execução assíncrona | app/workers | Registro Celery, worker, Beat e processamento do job. |
| Migração | migrations | Histórico Alembic e invariantes do schema. |
| Configuração | app/core/config.py | Pydantic Settings, variáveis de ambiente e defaults fail-closed. |
| Observabilidade | app/core/observability.py | Eventos JSON selecionados e correlação de request/job. |
| Infraestrutura | terraform | VPC, RDS, ElastiCache, Cognito, ECS, IAM, ALB e budget opcional. |

Os caminhos app/db e app/models são fachadas de compatibilidade que reexportam
adaptadores de infraestrutura. Código novo deve importar os adaptadores pelo
caminho app/infrastructure, para que a separação continue visível.

## Regra de dependência

As dependências permitidas apontam para dentro:

~~~text
API / Worker / Infrastructure  ->  Application  ->  Domain
                                      |
                                      +-> Ports definidas no domínio
~~~

O teste tests/test_architecture.py percorre recursivamente app/domain e
app/application, analisa a AST e bloqueia imports de FastAPI, SQLAlchemy,
Pydantic, Celery, Redis, SDKs AWS e das camadas app/api, app/infrastructure e
app/workers. Ele protege uma fronteira importante, mas não substitui revisão de
contratos, transações ou comportamento em runtime.

## Multi-tenancy

O isolamento é de schema compartilhado e linha compartilhada, com as seguintes
camadas:

1. O token Cognito ID contém custom:tenant_id.
2. O header X-Tenant-ID precisa ser UUID válido e coincidir exatamente com o
   claim antes de o endpoint obter um repositório.
3. O domínio converte o identificador em TenantId.
4. As portas e consultas de licitação recebem TenantId explicitamente.
5. O job assíncrono transporta tenant_id e o worker usa esse valor ao
   reivindicar, concluir ou falhar o job.
6. O banco possui foreign keys, chave única de negócio por tenant e uma foreign
   key composta que impede analysis_jobs de apontar para uma licitação de outro
   tenant.

O UUID global continua sendo um identificador de referência, não uma
autorização. Uma consulta por ID que não inclua tenant_id é considerada defeito
de segurança.

PostgreSQL Row Level Security não está habilitado. Isso deixa predicados de
tenant no repositório como a principal barreira de banco. Veja a ADR de
isolamento antes de introduzir RLS, porque pools de conexão, migrations e
acesso administrativo precisam de desenho explícito.

## Fluxo de criação e análise

### Criação

1. A API autentica o usuário e compara o claim ao header.
2. CreateLicitacao cria a entidade de domínio e o repositório a persiste.
3. PostgreSQL impõe valor positivo e unicidade de tenant_id, numero.
4. A invalidação de cache é melhor esforço. Uma falha de Redis não desfaz uma
   criação já confirmada.

### Solicitação de análise

1. A API passa tenant_id, licitacao_id e correlation_id para o caso de uso.
2. A transação bloqueia a licitação tenant-scoped, move ABERTA para
   EM_ANALISE_IA e grava analysis_jobs como PENDING.
3. A API retorna depois do commit; ela não chama o broker no event loop.
4. O Beat reivindica uma lease de relay persistida antes de publicar. Se a
   publicação falhar, a lease é liberada; se o processo cair, ela expira e o
   Beat recupera o registro durável.

O passo 2 evita a inconsistência de estado sem registro de trabalho. A lease
do relay reduz republicação normal concorrente, mas o transporte continua
at-least-once: uma queda depois de Redis aceitar a mensagem pode resultar em
reentrega após a lease expirar. Esse é o motivo para a execução do worker ser
idempotente.

### Worker e recuperação

1. O worker recebe job_id, tenant_id e correlation_id.
2. Ele faz uma reivindicação transacional de um job PENDING ou de um lease
   abandonado e recebe lock_token.
3. Somente o detentor do lock_token pode completar ou falhar o job.
4. A conclusão atualiza a decisão da licitação e o job na mesma transação.
5. Uma exceção registra apenas um código de falha sanitizado e retorna o job a
   PENDING com backoff, ou marca FAILED e a licitação como FALHA_ANALISE ao
   esgotar tentativas. Uma lease de execução abandonada também consome esse
   orçamento para que crashes repetidos não gerem tentativas infinitas.

Esse mecanismo evita que duas entregas concorrentes concluam a mesma
transição. Ele não torna automaticamente idempotente um efeito externo que
ocorra entre a reivindicação e o commit, por exemplo uma chamada futura a LLM.
Esse adaptador deve usar job_id como chave de idempotência ou registrar seu
efeito de modo recuperável.

## Integridade e acesso a dados

As migrations 0004_analysis_outbox e 0005_outbox_dispatch_lease adicionam:

- unique de tenant_id, numero para a chave de negócio;
- unique de tenant_id, id para servir de alvo da foreign key composta;
- checks de valor estimado positivo e status permitido;
- analysis_jobs com tenant_id, licitacao_id, correlation_id, estado, contagem,
  disponibilidade, lock, erro e timestamps;
- lease/token de relay separados da lease de execução e um índice de despacho
  por status, available_at e dispatch_locked_at, além de índices de tenant e
  correlação.

Antes de aplicar as constraints, a migration faz preflight de valores inválidos,
status desconhecidos e duplicidades. Ela falha de forma explícita em vez de
alterar silenciosamente dados históricos.

As consultas de lista ainda não têm paginação. Não publique um endpoint de
listagem com volume municipal real antes de definir limite, cursor/ordenação e
índices medidos contra o workload.

## Configuração e identidades

| Ambiente | Autenticação esperada | Observação |
| --- | --- | --- |
| development local | Bearer dev-token e tenant seed | Aceito somente quando ENVIRONMENT=development. |
| staging / production | JWT Cognito ID assinado | Issuer, assinatura, audience, token_use e custom:tenant_id são verificados. |

O default de Settings é production. Compose define development de forma
explícita para o ambiente local. Variáveis sem valor de Cognito são aceitáveis
somente enquanto o bypass local for explicitamente selecionado; em outros
ambientes um token não verificável deve falhar com 401.

## Observabilidade

A middleware cria ou valida um UUID em X-Request-ID, devolve-o na resposta e
emite o evento http_request_completed com caminho, status, duração e tenant
quando disponível. Eventos críticos do fluxo assíncrono incluem job_id,
tenant_id, correlation_id e attempt_count.

Eventos de degradação de cache e Redis registram somente tipo de erro e campos
operacionais, sem traceback ou texto bruto de exceção. Antes de operar em
escala, defina retenção, redaction e métricas para tempo de resposta, erros,
disponibilidade de dependências, idade do job, falhas/retries e pressão de
conexão.

## Implantação

Localmente, Docker Compose executa PostgreSQL, Redis, uma task de migration,
API, worker e Beat. PostgreSQL, Redis e API são publicados apenas em loopback
para desenvolvimento; isso não é modelo de rede de produção.

O Terraform declara:

- tasks ECS Fargate privadas, ALB público com redirecionamento HTTP para HTTPS;
- RDS PostgreSQL privado, criptografado, backup e TLS forçado;
- ElastiCache Redis criptografado e autenticado;
- Secrets Manager e KMS para runtime;
- Cognito com atribuição administrativa e tenant imutável;
- security groups de dados que aceitam somente o SG das tasks;
- uma task ECS de migration e um script versionado que a executa e exige exit
  code 0 antes de promover as services;
- autoscaling CPU para API e worker.

O repositório não cria por si só DNS, um certificado ACM válido, credenciais AWS,
backend remoto de Terraform, alarmes ou uma execução em conta real. Esses itens
são pré-requisitos operacionais, não detalhes que podem ser inferidos localmente.

## Leituras relacionadas

- [Security](SECURITY.md)
- [Runbook](RUNBOOK.md)
- [Architecture hardening](architecture-hardening.md)
- [ADR 0001 — isolamento multi-tenant](adr/0001-multi-tenant-isolation.md)
- [ADR 0002 — job durável de análise](adr/0002-durable-analysis-job.md)
- [ADR 0003 — claim de tenant no Cognito](adr/0003-cognito-tenant-claim.md)
- [ADR 0004 — rollout ECS condicionado à migration](adr/0004-schema-gated-ecs-rollout.md)
