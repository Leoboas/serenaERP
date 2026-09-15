# EXPLAIN ANALYZE

## Metodologia

Executar no PostgreSQL 15 após o seed, substituindo o UUID pelo tenant avaliado:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COALESCE(SUM(valor_estimado), 0), COUNT(id)
FROM licitacoes
WHERE tenant_id = '00000000-0000-0000-0000-000000000001';
```

## Antes do tuning

A referência pré-índices é um `Seq Scan` em `licitacoes`, com custo proporcional ao total global de registros. O plano deve ser capturado antes de aplicar a revisão `0002_reporting_indexes` e colado abaixo:

```text
PREENCHER AO EXECUTAR CONTRA O POSTGRESQL DO COMPOSE
```

## Depois do tuning

A revisão `0002_reporting_indexes` adiciona `tenant_id, status, data_criacao` e um índice parcial para status ativos. Repetir o mesmo comando e registrar aqui o plano observado:

```text
PREENCHER AO EXECUTAR CONTRA O POSTGRESQL DO COMPOSE
```

O ambiente desta entrega não tinha Docker Desktop ativo, portanto não há números honestos de latência para inventar. A comparação deve ser feita no mesmo volume, com o mesmo tenant e `BUFFERS` habilitado.
