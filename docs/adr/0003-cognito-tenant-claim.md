# ADR 0003 — Claim de tenant no Cognito ID token

- Status: Accepted
- Data: 2026-10-14

## Contexto

O serviço precisa obter uma identidade de tenant que não possa ser escolhida
pelo cliente. O atributo custom:tenant_id é a fronteira de autorização
multi-tenant. Cognito não inclui atributos personalizados em access tokens sem
uma customização adicional de token.

## Decisão

A API valida Cognito ID tokens e espera custom:tenant_id neles. O User Pool
define o atributo como obrigatório e imutável. O app client permite leitura
desse atributo, não permite sua escrita, e a criação de usuários é
administrativa; não há auto cadastro público.

A configuração de runtime define COGNITO_TOKEN_USE=id. O verificador valida
assinatura RS256, issuer, audience/client ID, token_use e presença do claim
antes de permitir qualquer endpoint tenant-aware.

## Alternativas consideradas

| Alternativa | Decisão |
| --- | --- |
| Access token sem trigger | Rejeitada. Não transporta o claim necessário por padrão. |
| Access token com pre-token Lambda | Adiada. Acrescenta Lambda, IAM, observabilidade e novo caminho de falha. |
| Tenant controlado somente por header | Rejeitada. Não é uma identidade assinada. |
| Usuário se atribui ao tenant no cadastro | Rejeitada. Permite escalonamento de privilégio. |

## Consequências

Clientes precisam enviar um ID token válido para a API. A equipe de identidade
deve testar emissão, rotação de JWKS, expiração, revogação, recuperação e
provisionamento administrativo em uma conta real.

MFA, grupos/roles de negócio e políticas de sessão não são configurados por
esta decisão. Se a política municipal exigir MFA ou autorização além do tenant,
isso deve ser uma decisão e implementação adicional, com testes de privilégio.

## Validação

Testes unitários cobrem bypass de desenvolvimento, default fail-closed,
verificação de claim e mismatch entre claim/header. Antes de produção, valide
tokens assinados por um User Pool real, inclusive issuer, audience, expiração e
um usuário sem tenant.
