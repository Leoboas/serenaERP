import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.application.use_cases import AnalyzeLicitacao
from app.core.config import get_settings
from app.core.observability import log_event
from app.domain.analysis_jobs import AnalysisJobCompletionOutcome
from app.domain.value_objects import TenantId
from app.infrastructure.persistence.repositories import SqlAlchemyLicitacaoRepository
from app.workers.celery_app import celery_app

settings = get_settings()


def _worker_session_factory() -> tuple[async_sessionmaker[AsyncSession], object]:
    """Create an unpooled engine for one Celery asyncio.run invocation.

    Celery tasks are synchronous and each task gets a fresh event loop through
    asyncio.run. Reusing asyncpg pooled connections across those loops causes
    intermittent "attached to a different loop" failures, so this worker uses
    NullPool and disposes the engine after every task.
    """

    engine = create_async_engine(settings.database_url, pool_pre_ping=True, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def analyze_licitacao(
    job_id: UUID,
    tenant_id: UUID,
    correlation_id: UUID,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    max_retries: int | None = None,
) -> str:
    """Claim and process a tenant-bound durable job exactly once per lock."""

    engine = None
    if session_factory is None:
        session_factory, engine = _worker_session_factory()
    if max_retries is None:
        max_retries = settings.analysis_job_max_retries

    try:
        async with session_factory() as session:
            repository = SqlAlchemyLicitacaoRepository(session)
            job = await repository.claim_analysis_job(
                job_id,
                TenantId(tenant_id),
                settings.analysis_job_lock_timeout_seconds,
                max_retries,
            )
            if job is None:
                log_event(
                    "analysis_job_not_claimed",
                    tenant_id=tenant_id,
                    job_id=job_id,
                    correlation_id=correlation_id,
                )
                return "not_claimed"

            try:
                # Placeholder for the future LLM adapter. It stays behind the
                # durable claim and therefore cannot run twice concurrently.
                await asyncio.sleep(2)
                completion_outcome = await AnalyzeLicitacao(repository).execute(job)
                if completion_outcome == AnalysisJobCompletionOutcome.CLAIM_LOST:
                    raise RuntimeError("analysis result could not be committed for the claimed job")
                if completion_outcome == AnalysisJobCompletionOutcome.TERMINAL_FAILURE:
                    log_event(
                        "analysis_job_terminal_failure",
                        level=40,
                        tenant_id=job.tenant_id.value,
                        job_id=job.id,
                        correlation_id=job.correlation_id,
                        attempt_count=job.attempt_count,
                    )
                    return "failed"
            except Exception as exc:
                # Retry ownership lives in the durable record, not in the
                # per-delivery Celery counter. A duplicate broker message
                # therefore cannot reset the retry budget indefinitely.
                retry_delay_seconds = _retry_delay_for_attempt(job.attempt_count, max_retries)
                try:
                    recorded = await repository.fail_analysis_job(
                        job,
                        f"analysis_execution_failed:{type(exc).__name__}",
                        retry_delay_seconds,
                    )
                except Exception:
                    log_event(
                        "analysis_job_failure_recording_failed",
                        level=40,
                        tenant_id=job.tenant_id.value,
                        job_id=job.id,
                        correlation_id=job.correlation_id,
                        error_type=type(exc).__name__,
                    )
                    raise
                if not recorded:
                    # Do not acknowledge an outcome we could not associate
                    # with our execution lease; the stale lease is recoverable
                    # by the outbox relay.
                    raise
                log_event(
                    "analysis_job_failed",
                    level=40,
                    tenant_id=job.tenant_id.value,
                    job_id=job.id,
                    correlation_id=job.correlation_id,
                    attempt_count=job.attempt_count,
                    error_type=type(exc).__name__,
                    retry_scheduled=retry_delay_seconds is not None,
                )
                return "retry_scheduled" if retry_delay_seconds is not None else "failed"

            log_event(
                "analysis_job_completed",
                tenant_id=job.tenant_id.value,
                job_id=job.id,
                correlation_id=job.correlation_id,
                attempt_count=job.attempt_count,
            )
            return "completed"
    finally:
        if engine is not None:
            await engine.dispose()


def _retry_delay_for_attempt(attempt_count: int, max_retries: int) -> int | None:
    """Return the next durable retry delay, or finish after the retry budget."""

    if attempt_count > max_retries:
        return None
    return min(30 * (2 ** (attempt_count - 1)), 900)


@celery_app.task(
    name="serenaerp.analysis.process",
)
def analisar_licitacao(
    job_id: str,
    tenant_id: str,
    correlation_id: str,
) -> str:
    return asyncio.run(
        analyze_licitacao(
            UUID(job_id),
            UUID(tenant_id),
            UUID(correlation_id),
        )
    )


async def dispatch_pending_analysis_jobs(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> int:
    """Relay committed outbox records to Celery; safe to run repeatedly."""

    engine = None
    if session_factory is None:
        session_factory, engine = _worker_session_factory()
    try:
        async with session_factory() as session:
            repository = SqlAlchemyLicitacaoRepository(session)
            jobs = await repository.list_dispatchable_analysis_jobs(
                limit=100,
                lock_timeout_seconds=settings.analysis_job_lock_timeout_seconds,
            )
            dispatched = 0
            for job in jobs:
                dispatch_job = await repository.claim_analysis_job_dispatch(
                    job.id,
                    job.tenant_id,
                    settings.analysis_job_lock_timeout_seconds,
                )
                if dispatch_job is None:
                    continue
                try:
                    celery_app.send_task(
                        "serenaerp.analysis.process",
                        args=[
                            str(dispatch_job.id),
                            str(dispatch_job.tenant_id.value),
                            str(dispatch_job.correlation_id),
                        ],
                    )
                except Exception:
                    try:
                        await repository.release_analysis_job_dispatch(dispatch_job)
                    except Exception:
                        log_event(
                            "analysis_outbox_release_failed",
                            level=40,
                            tenant_id=dispatch_job.tenant_id.value,
                            job_id=dispatch_job.id,
                            correlation_id=dispatch_job.correlation_id,
                        )
                    log_event(
                        "analysis_outbox_publish_failed",
                        level=40,
                        tenant_id=dispatch_job.tenant_id.value,
                        job_id=dispatch_job.id,
                        correlation_id=dispatch_job.correlation_id,
                    )
                    continue
                dispatched += 1
        if dispatched:
            log_event("analysis_outbox_dispatched", count=dispatched)
        return dispatched
    finally:
        if engine is not None:
            await engine.dispose()


@celery_app.task(
    name="serenaerp.analysis.dispatch_pending",
)
def dispatch_analysis_outbox() -> int:
    return asyncio.run(dispatch_pending_analysis_jobs())
