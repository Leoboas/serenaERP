from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Licitacao, Tenant
from app.workers import ai_worker


@pytest.mark.asyncio
async def test_worker_classifica_risco(monkeypatch) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        session.add(Tenant(id=tenant_id, name="Tenant", schema_name="tenant"))
        licitacao = Licitacao(
            tenant_id=tenant_id,
            numero="PE-900",
            descricao="Auditoria de risco",
            valor_estimado=Decimal("1000001.00"),
        )
        session.add(licitacao)
        await session.commit()
        licitacao_id = licitacao.id

    monkeypatch.setattr(ai_worker, "AsyncSessionLocal", session_factory)
    async def no_sleep(_: int) -> None:
        return None

    monkeypatch.setattr(ai_worker.asyncio, "sleep", no_sleep)
    await ai_worker.analyze_licitacao(licitacao_id)

    async with session_factory() as session:
        refreshed = await session.get(Licitacao, licitacao_id)
        assert refreshed is not None
        assert refreshed.status == "ALERTA_RISCO"
    await engine.dispose()
