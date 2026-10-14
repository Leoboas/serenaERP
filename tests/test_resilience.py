from decimal import Decimal
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.application.dtos import CreateLicitacaoCommand
from app.application.use_cases import CreateLicitacao, GetGastosTotais, RequestLicitacaoAnalysis
from app.db.base import Base
from app.infrastructure.persistence.models import AnalysisJobModel
from app.infrastructure.persistence.repositories import SqlAlchemyLicitacaoRepository
from app.models import Tenant

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


class UnavailableCache:
    async def get(self, _key: str) -> str | None:
        raise ConnectionError("redis unavailable")

    async def set(self, _key: str, _value: str, ttl_seconds: int) -> None:
        raise ConnectionError("redis unavailable")

    async def delete(self, _key: str) -> None:
        raise ConnectionError("redis unavailable")


@pytest_asyncio.fixture
async def resilient_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        session.add(Tenant(id=TENANT_ID, name="Tenant", schema_name="tenant"))
        await session.commit()
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_cache_failure_does_not_fail_a_committed_creation_or_report(resilient_session_factory) -> None:
    async with resilient_session_factory() as session:
        repository = SqlAlchemyLicitacaoRepository(session)
        created = await CreateLicitacao(repository, UnavailableCache()).execute(
            CreateLicitacaoCommand(
                tenant_id=TENANT_ID,
                numero="PE-CACHE-001",
                descricao="Resiliencia de cache",
                valor_estimado=Decimal("10.50"),
            )
        )
        assert created.tenant_id == TENANT_ID

    async with resilient_session_factory() as session:
        report = await GetGastosTotais(
            SqlAlchemyLicitacaoRepository(session), UnavailableCache()
        ).execute(TENANT_ID)
    assert report.total == Decimal("10.50")
    assert report.quantidade == 1


@pytest.mark.asyncio
async def test_request_leaves_a_dispatchable_tenant_bound_outbox_record(
    resilient_session_factory, monkeypatch
) -> None:
    async with resilient_session_factory() as session:
        repository = SqlAlchemyLicitacaoRepository(session)
        created = await CreateLicitacao(repository, UnavailableCache()).execute(
            CreateLicitacaoCommand(
                tenant_id=TENANT_ID,
                numero="PE-OUTBOX-001",
                descricao="Recuperacao de broker",
                valor_estimado=Decimal("200.00"),
            )
        )
        requested = await RequestLicitacaoAnalysis(repository).execute(TENANT_ID, created.id)
    assert requested is not None
    # Application DTOs deliberately expose the transport-friendly string, not
    # the domain enum instance.
    assert requested.status == "EM_ANALISE_IA"

    async with resilient_session_factory() as session:
        job = await session.scalar(select(AnalysisJobModel).where(AnalysisJobModel.licitacao_id == created.id))
        assert job is not None
        assert job.status == "PENDING"
        assert job.dispatch_token is None
        job_id = job.id
        correlation_id = job.correlation_id

    from app.workers import ai_worker

    dispatched: list[tuple[str, list[str]]] = []

    def capture_send_task(name: str, args: list[str]) -> None:
        dispatched.append((name, args))

    monkeypatch.setattr(ai_worker.celery_app, "send_task", capture_send_task)
    count = await ai_worker.dispatch_pending_analysis_jobs(session_factory=resilient_session_factory)
    repeated_count = await ai_worker.dispatch_pending_analysis_jobs(session_factory=resilient_session_factory)

    assert count == 1
    assert repeated_count == 0
    assert dispatched == [
        (
            "serenaerp.analysis.process",
            [str(job_id), str(TENANT_ID), str(correlation_id)],
        )
    ]
