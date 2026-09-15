"""Insere dados sintéticos em lotes para benchmark PostgreSQL."""

import argparse
import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import insert

from app.db.session import AsyncSessionLocal
from app.models import Licitacao, Tenant

TENANT_IDS = [
    uuid.UUID("00000000-0000-0000-0000-000000000001"),
    uuid.UUID("00000000-0000-0000-0000-000000000002"),
]


async def seed(total: int, batch_size: int) -> None:
    async with AsyncSessionLocal() as session:
        for tenant_id in TENANT_IDS:
            await session.execute(
                insert(Tenant).values(
                    id=tenant_id,
                    name=f"Tenant Benchmark {tenant_id.int % 100}",
                    schema_name=f"tenant_{tenant_id.int % 100}",
                    status="ATIVO",
                )
            )
        await session.commit()

        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            rows = [
                {
                    "tenant_id": TENANT_IDS[index % len(TENANT_IDS)],
                    "numero": f"BENCH-{index:07d}",
                    "descricao": f"Registro sintético de benchmark {index}",
                    "valor_estimado": Decimal((index % 100000) + 1),
                    "status": "ABERTA" if index % 10 else "EM_ANALISE_IA",
                }
                for index in range(start, end)
            ]
            await session.execute(insert(Licitacao), rows)
            await session.commit()
            print(f"Inseridos {end}/{total} registros")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--total", type=int, default=500_000)
    parser.add_argument("--batch-size", type=int, default=5_000)
    args = parser.parse_args()
    asyncio.run(seed(args.total, args.batch_size))


if __name__ == "__main__":
    main()
