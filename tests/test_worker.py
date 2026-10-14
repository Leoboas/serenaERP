from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.domain.value_objects import TenantId
from app.infrastructure.persistence.models import AnalysisJobModel
from app.infrastructure.persistence.repositories import SqlAlchemyLicitacaoRepository
from app.models import Licitacao, Tenant
from app.workers.celery_app import celery_app


def test_worker_registers_analysis_tasks_without_api_import_side_effect() -> None:
    celery_app.loader.import_default_modules()

    assert "serenaerp.analysis.process" in celery_app.tasks
    assert "serenaerp.analysis.dispatch_pending" in celery_app.tasks


@pytest.mark.asyncio
async def test_worker_claim_uses_the_configured_execution_lease(monkeypatch) -> None:
    from app.workers import ai_worker

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    captured: dict[str, int] = {}

    async def claim_with_observed_timeout(
        _self, _job_id, _tenant_id, lock_timeout_seconds, _max_retries
    ):
        captured["lock_timeout_seconds"] = lock_timeout_seconds
        return None

    monkeypatch.setattr(
        SqlAlchemyLicitacaoRepository,
        "claim_analysis_job",
        claim_with_observed_timeout,
    )
    monkeypatch.setattr(ai_worker.settings, "analysis_job_lock_timeout_seconds", 17)

    result = await ai_worker.analyze_licitacao(
        uuid4(), uuid4(), uuid4(), session_factory=session_factory
    )

    assert result == "not_claimed"
    assert captured == {"lock_timeout_seconds": 17}
    await engine.dispose()


@pytest.mark.asyncio
async def test_abandoned_execution_is_terminal_after_durable_retry_budget() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid4()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        session.add(Tenant(id=tenant_id, name="Tenant", schema_name="tenant_abandoned"))
        licitacao = Licitacao(
            tenant_id=tenant_id,
            numero="PE-ABANDONED-001",
            descricao="Execucao interrompida",
            valor_estimado=Decimal("100.00"),
        )
        session.add(licitacao)
        await session.commit()
        licitacao_id = licitacao.id

    async with session_factory() as session:
        repository = SqlAlchemyLicitacaoRepository(session)
        scheduled = await repository.schedule_analysis(TenantId(tenant_id), licitacao_id, uuid4())
        assert scheduled is not None
        _, job = scheduled
        claimed = await repository.claim_analysis_job(
            job.id, TenantId(tenant_id), lock_timeout_seconds=300, max_retries=0
        )
        assert claimed is not None
        persisted_job = await session.get(AnalysisJobModel, job.id)
        assert persisted_job is not None
        persisted_job.locked_at = datetime.now(timezone.utc) - timedelta(seconds=301)
        await session.commit()

    async with session_factory() as session:
        terminal_claim = await SqlAlchemyLicitacaoRepository(session).claim_analysis_job(
            job.id, TenantId(tenant_id), lock_timeout_seconds=300, max_retries=0
        )
        assert terminal_claim is None

    async with session_factory() as session:
        refreshed = await session.get(Licitacao, licitacao_id)
        persisted_job = await session.get(AnalysisJobModel, job.id)
        assert refreshed is not None
        assert refreshed.status == "FALHA_ANALISE"
        assert persisted_job is not None
        assert persisted_job.status == "FAILED"
        assert persisted_job.attempt_count == 1
        assert persisted_job.last_error == "analysis_execution_lease_expired_after_retry_budget"
    await engine.dispose()


@pytest.mark.asyncio
async def test_worker_classifies_risk_once_for_a_tenant_bound_job(monkeypatch) -> None:
    from app.workers import ai_worker

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

    async with session_factory() as session:
        repository = SqlAlchemyLicitacaoRepository(session)
        scheduled = await repository.schedule_analysis(TenantId(tenant_id), licitacao_id, uuid4())
        assert scheduled is not None
        _, job = scheduled

    async def no_sleep(_: int) -> None:
        return None

    monkeypatch.setattr(ai_worker.asyncio, "sleep", no_sleep)
    processed = await ai_worker.analyze_licitacao(
        job.id,
        tenant_id,
        job.correlation_id,
        session_factory=session_factory,
    )
    duplicate = await ai_worker.analyze_licitacao(
        job.id,
        tenant_id,
        job.correlation_id,
        session_factory=session_factory,
    )

    assert processed == "completed"
    assert duplicate == "not_claimed"
    async with session_factory() as session:
        refreshed = await session.get(Licitacao, licitacao_id)
        persisted_job = await session.get(AnalysisJobModel, job.id)
        assert refreshed is not None
        assert refreshed.status == "ALERTA_RISCO"
        assert persisted_job is not None
        assert persisted_job.status == "COMPLETED"
        assert persisted_job.attempt_count == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_worker_persists_terminal_failure_using_durable_attempt_budget(monkeypatch) -> None:
    from app.workers import ai_worker

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
            numero="PE-FAIL-001",
            descricao="Falha de provedor de IA",
            valor_estimado=Decimal("100.00"),
        )
        session.add(licitacao)
        await session.commit()
        licitacao_id = licitacao.id

    async with session_factory() as session:
        scheduled = await SqlAlchemyLicitacaoRepository(session).schedule_analysis(
            TenantId(tenant_id), licitacao_id, uuid4()
        )
        assert scheduled is not None
        _, job = scheduled

    async def no_sleep(_: int) -> None:
        return None

    async def failing_analysis(_self, _job) -> bool:
        raise TimeoutError("LLM provider api_key=must-not-be-persisted")

    monkeypatch.setattr(ai_worker.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(ai_worker.AnalyzeLicitacao, "execute", failing_analysis)
    result = await ai_worker.analyze_licitacao(
        job.id,
        tenant_id,
        job.correlation_id,
        session_factory=session_factory,
        max_retries=0,
    )

    assert result == "failed"
    async with session_factory() as session:
        refreshed = await session.get(Licitacao, licitacao_id)
        persisted_job = await session.get(AnalysisJobModel, job.id)
        assert refreshed is not None
        assert refreshed.status == "FALHA_ANALISE"
        assert persisted_job is not None
        assert persisted_job.status == "FAILED"
        assert persisted_job.attempt_count == 1
        assert persisted_job.last_error == "analysis_execution_failed:TimeoutError"
    await engine.dispose()
