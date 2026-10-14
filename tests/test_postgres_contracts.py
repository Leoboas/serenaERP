"""PostgreSQL-only checks for constraints SQLite cannot faithfully emulate."""

import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.entities import Licitacao
from app.domain.value_objects import TenantId
from app.infrastructure.persistence.models import AnalysisJobModel, LicitacaoModel, TenantModel
from app.infrastructure.persistence.repositories import SqlAlchemyLicitacaoRepository

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires RUN_POSTGRES_INTEGRATION=1 and an ephemeral PostgreSQL database",
)


@pytest.mark.asyncio
async def test_postgresql_enforces_tenant_constraints_and_supports_outbox_locking() -> None:
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+"):
        pytest.skip("requires PostgreSQL, not a SQLite substitute")

    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_a = uuid4()
    tenant_b = uuid4()
    licitacao_id = uuid4()
    try:
        async with session_factory() as session:
            session.add_all(
                [
                    TenantModel(id=tenant_a, name="PG Tenant A", schema_name=f"pg_a_{tenant_a.hex[:16]}"),
                    TenantModel(id=tenant_b, name="PG Tenant B", schema_name=f"pg_b_{tenant_b.hex[:16]}"),
                ]
            )
            await session.commit()

        async with session_factory() as session:
            repository = SqlAlchemyLicitacaoRepository(session)
            created = await repository.add(
                Licitacao(
                    id=licitacao_id,
                    tenant_id=TenantId(tenant_a),
                    numero="PG-CONTRACT-001",
                    descricao="Contrato de integracao PostgreSQL",
                    valor_estimado=Decimal("10.00"),
                )
            )
            scheduled = await repository.schedule_analysis(TenantId(tenant_a), created.id, uuid4())
            assert scheduled is not None
            _, job = scheduled
            claimed = await repository.claim_analysis_job(
                job.id, TenantId(tenant_a), lock_timeout_seconds=300, max_retries=5
            )
            assert claimed is not None
            assert claimed.tenant_id == TenantId(tenant_a)

        async with session_factory() as session:
            duplicate = LicitacaoModel(
                tenant_id=tenant_a,
                numero="PG-CONTRACT-001",
                descricao="Numero repetido no mesmo tenant",
                valor_estimado=Decimal("20.00"),
                status="ABERTA",
            )
            session.add(duplicate)
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()

        async with session_factory() as session:
            # The composite FK is the database-level backstop against a job in
            # tenant B being pointed at an otherwise valid UUID from tenant A.
            session.add(
                AnalysisJobModel(
                    id=uuid4(),
                    tenant_id=tenant_b,
                    licitacao_id=licitacao_id,
                    correlation_id=uuid4(),
                    status="PENDING",
                    attempt_count=0,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
    finally:
        async with session_factory() as session:
            await session.execute(delete(TenantModel).where(TenantModel.id.in_([tenant_a, tenant_b])))
            await session.commit()
        await engine.dispose()
