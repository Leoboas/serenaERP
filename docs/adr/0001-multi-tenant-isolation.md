# ADR 0001 — Isolamento multi-tenant por tenant explícito

- Status: Accepted
- Data: 2026-10-14

## Contexto

SerenaERP atende prefeituras em um modelo de schema compartilhado. Um UUID de
licitação é globalmente identificável, mas não concede acesso ao registro. O
maior risco arquitetural é permitir que uma API, um relatório, um job ou uma
consulta de suporte use apenas esse UUID e atravesse tenants.

## Decisão

O tenant canônico vem do claim assinado custom:tenant_id no Cognito ID token.
X-Tenant-ID é preservado como parte do contrato HTTP e deve coincidir
exatamente com o claim; ele nunca pode escolher um tenant diferente.

O identificador é representado por TenantId no domínio e é transportado por:

~~~text
HTTP claim/header -> endpoint -> caso de uso -> porta/repositório
-> banco -> analysis_jobs -> mensagem Celery -> worker
~~~

Repositórios tenant-aware recebem tenant explicitamente. Jobs contêm
tenant_id, licitacao_id e correlation_id. A persistência usa predicados por
tenant e constraints complementares:

- chave de negócio única por tenant_id e numero;
- chave única tenant_id e id em licitações;
- foreign key composta de analysis_jobs para a licitação do mesmo tenant.

Consultas por ID sem tenant não pertencem à porta de domínio/repositório.

## Alternativas consideradas

| Alternativa | Decisão |
| --- | --- |
| Confiar apenas em X-Tenant-ID | Rejeitada. Header é controlado pelo cliente e não é identidade. |
| Banco/schema por tenant | Rejeitada no estágio atual. Aumenta operação, migrations, pooling e custo sem requisito demonstrado. |
| PostgreSQL RLS agora | Adiada. É defesa em profundidade valiosa, mas requer desenho de contexto de sessão, migrations, worker e suporte. |
| UUID global como autorização implícita | Rejeitada. UUID reduz enumeração, não substitui autorização. |

## Consequências

O contrato fica mais verboso: cada novo caminho de dados precisa receber e
validar tenant. Em troca, o código torna ownership visível e testes podem
provar os casos negativos.

RLS permanece um risco residual. Antes de habilitá-lo, deve existir uma ADR de
operacionalização contendo como o tenant é configurado por transação, como
conexões de pool são limpas, quais roles escapam da política e como migrations
são executadas.

## Validação

Os testes cobrem leitura cross-tenant e tentativa de solicitar análise de uma
licitação de outro tenant. A migration estabelece a foreign key composta. A
validação de produção ainda requer testes PostgreSQL reais e um smoke com
tokens Cognito emitidos pela conta alvo.
