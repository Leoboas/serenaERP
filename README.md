# serenaERP

## Visão geral executiva

O **serenaERP** é uma plataforma GovTech cloud-native e multi-tenant para gestão e análise inteligente de licitações públicas municipais. A solução organiza o fluxo de criação, consulta, consolidação de gastos e análise assíncrona de licitações, mantendo a separação entre regras de negócio, casos de uso e adaptadores de infraestrutura.

O projeto foi estruturado para operar localmente com Docker Compose e para ser provisionado na AWS com ECS Fargate, RDS PostgreSQL, ElastiCache/Redis, Cognito e componentes de rede definidos em Terraform.

## Destaques de arquitetura e engenharia

### Clean Architecture e DDD

As dependências seguem o sentido da borda para o núcleo:

- \`app/domain\`: entidades, value objects e contratos, sem dependências de FastAPI, SQLAlchemy, Pydantic ou Celery.
- \`app/application\`: casos de uso e DTOs que dependem apenas do domínio e de suas portas.
- \`app/api\`: adaptadores HTTP/FastAPI, autenticação e validação de entrada.
- \`app/infrastructure\`: persistência SQLAlchemy, Redis, Celery e Cognito.
- \`app/workers\`: entrada assíncrona que delega o processamento ao caso de uso.

O teste \`tests/test_architecture.py\` verifica automaticamente que o domínio não importa frameworks. Os contratos \`LicitacaoRepository\`, \`LicitacaoReportRepository\`, \`Cache\` e \`AnalysisJobPublisher\` abstraem banco, cache e mensageria; o adaptador SQLAlchemy fica limitado à infraestrutura.

### Zero-Trust multi-tenancy

\`TenantId\` é um Value Object imutável do domínio. Os casos de uso convertem o identificador recebido para esse tipo e os métodos de leitura e agregação do repositório recebem explicitamente o tenant, aplicando-o às consultas. Na borda HTTP, o \`X-Tenant-ID\` precisa corresponder ao claim \`custom:tenant_id\` do usuário autenticado.

O worker possui uma leitura interna não escopada por tenant para localizar uma tarefa pelo ID da licitação. Ela não é exposta pela API HTTP; futuras evoluções podem transportar também o \`tenant_id\` na mensagem para eliminar essa exceção de privilégio interno.

### Processamento assíncrono

Após a solicitação de análise, a API publica uma tarefa Celery no Redis. O worker recupera a licitação, aplica a regra de classificação de risco e persiste o novo status. A implementação atual simula a etapa de IA/LLM; a porta de publicação permite substituir essa simulação por um provedor real sem acoplar o domínio ao Celery.

### FinOps e infraestrutura cloud

O Terraform descreve execução em ECS Fargate, PostgreSQL gerenciado, Redis, Cognito, VPC e orçamento AWS opcional. Staging usa uma task por serviço com 0,25 vCPU/0,5 GB e componentes menores; produção parte de duas tasks por serviço com 0,5 vCPU/1 GB e autoscaling de 2 a 10 tasks por CPU. O orçamento mensal é criado quando \`budget_alert_email\` é informado.

## Segurança e auditoria

- Não há chaves AWS, tokens JWT reais, chaves privadas, bancos locais, logs, \`.env\`, ambientes virtuais ou cache de testes rastreados pelo Git.
- \`.gitignore\` cobre \`.env\`/\`.env.*\` (preservando \`.env.example\`), \`.venv\`, \`.pytest_cache\`, \`*.db\`, \`*.sqlite\`, \`*.sqlite3\` e logs.
- A varredura do código não encontrou caminhos absolutos locais versionados.
- \`docker-compose.yml\`, \`.env.example\`, \`alembic.ini\` e os defaults da aplicação contêm as credenciais conhecidas \`goverp/goverp\` exclusivamente para desenvolvimento local. Elas não são segredo de produção e não devem ser reutilizadas fora do ambiente local; produção deve injetar segredos pelo mecanismo da plataforma.
- \`Bearer dev-token\` só é aceito quando \`ENVIRONMENT=development\`; em qualquer outro ambiente a validação Cognito/JWT permanece obrigatória.

## Qualidade e métricas verificadas

| Evidência | Resultado |
| --- | --- |
| Pytest (unidade, arquitetura, autenticação, tenant, relatórios e worker) | **8/8 aprovados** |
| Integridade arquitetural | Aprovada por \`test_domain_has_no_framework_dependencies\` |
| Teste de carga Locust | Cenário disponível, sem resultado empírico versionado |

O repositório não contém uma execução auditável de Locust que sustente p50 de 130 ms para consultas, p50 de 310 ms para relatórios, 50 usuários simultâneos ou 0% de erro. Esses valores devem ser publicados somente após uma execução reproduzível, com ambiente, duração, volume de dados e relatório anexados. O cenário está em \`tests/load_test_locust.py\` e exige \`LOCUST_TENANT_IDS\` e \`LOCUST_ACCESS_TOKEN\`.

## Executar localmente

Pré-requisitos: Docker Desktop com engine Linux ativo e Docker Compose.

\`\`\`bash
docker compose up -d --build
docker compose exec app alembic upgrade head
docker compose exec app pytest -v
\`\`\`

Para chamadas HTTP em desenvolvimento, use \`Authorization: Bearer dev-token\` e o tenant padrão. O bypass não deve ser habilitado em staging ou produção.

\`\`\`bash
curl -X POST http://localhost:8000/api/v1/licitacoes/ \
  -H "Authorization: Bearer dev-token" \
  -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
  -H "Content-Type: application/json" \
  -d '{"numero":"PE-001","descricao":"Compra de equipamentos","valor_estimado":"1000.00"}'
\`\`\`

## Fluxo de arquitetura

\`\`\`mermaid
flowchart LR
    Client[Cliente / API Consumer] --> HTTP[FastAPI adapters]
    HTTP --> UC[Application Use Cases]
    UC --> Domain[Domain Rules + TenantId]
    UC --> Repo[Repository / Cache / Job ports]
    Repo --> DB[(PostgreSQL)]
    Repo --> Cache[(Redis)]
    Repo --> Queue[Celery / Redis broker]
    Queue --> Worker[Celery Worker]
    Worker --> UC
\`\`\`

## Estrutura do repositório

\`\`\`text
app/domain/          Regras de negócio, entidades e portas
app/application/     Casos de uso e DTOs
app/api/             FastAPI, autenticação e schemas
app/infrastructure/  SQLAlchemy, Redis, Celery e Cognito
app/workers/         Consumidores Celery
migrations/          Histórico Alembic
terraform/           Infraestrutura AWS
tests/               Testes automatizados e cenário Locust
\`\`\`
