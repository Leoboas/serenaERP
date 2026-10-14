import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.analysis_jobs import AnalysisJob, AnalysisJobCompletionOutcome, AnalysisJobStatus
from app.domain.entities import Licitacao, LicitacaoStatus
from app.domain.repositories import AnalysisJobStore, LicitacaoReportRepository, LicitacaoRepository
from app.domain.value_objects import TenantId
from app.infrastructure.persistence.models import AnalysisJobModel, LicitacaoModel


class SqlAlchemyLicitacaoRepository(
    LicitacaoRepository, LicitacaoReportRepository, AnalysisJobStore
):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _safe_error_code(error_code: str) -> str:
        """Persist a bounded machine code, never arbitrary provider exception text."""

        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_:-]{0,119}", error_code):
            return error_code
        return "analysis_failed"

    @staticmethod
    def _to_domain(model: LicitacaoModel) -> Licitacao:
        return Licitacao(
            id=model.id,
            tenant_id=TenantId(model.tenant_id),
            numero=model.numero,
            descricao=model.descricao,
            valor_estimado=Decimal(model.valor_estimado),
            status=LicitacaoStatus(model.status),
            data_criacao=model.data_criacao,
        )

    @staticmethod
    def _to_job(model: AnalysisJobModel) -> AnalysisJob:
        return AnalysisJob(
            id=model.id,
            tenant_id=TenantId(model.tenant_id),
            licitacao_id=model.licitacao_id,
            correlation_id=model.correlation_id,
            status=AnalysisJobStatus(model.status),
            attempt_count=model.attempt_count,
            lock_token=model.lock_token,
            dispatch_token=model.dispatch_token,
        )

    @staticmethod
    def _dispatchable_condition(now: datetime, stale_before: datetime):
        """Return jobs whose broker relay lease is absent or has expired."""

        pending = and_(
            AnalysisJobModel.status == AnalysisJobStatus.PENDING.value,
            AnalysisJobModel.available_at <= now,
        )
        abandoned_execution = and_(
            AnalysisJobModel.status == AnalysisJobStatus.PROCESSING.value,
            AnalysisJobModel.locked_at.is_not(None),
            AnalysisJobModel.locked_at <= stale_before,
        )
        relay_lease_available = or_(
            AnalysisJobModel.dispatch_locked_at.is_(None),
            AnalysisJobModel.dispatch_locked_at <= stale_before,
        )
        return and_(or_(pending, abandoned_execution), relay_lease_available)

    @staticmethod
    def _to_model(entity: Licitacao) -> LicitacaoModel:
        return LicitacaoModel(
            id=entity.id,
            tenant_id=entity.tenant_id.value,
            numero=entity.numero,
            descricao=entity.descricao,
            valor_estimado=entity.valor_estimado,
            status=entity.status.value,
            data_criacao=entity.data_criacao,
        )

    async def add(self, licitacao: Licitacao) -> Licitacao:
        model = self._to_model(licitacao)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        await self.session.commit()
        return self._to_domain(model)

    async def list_by_tenant(self, tenant_id: TenantId) -> list[Licitacao]:
        result = await self.session.scalars(
            select(LicitacaoModel)
            .where(LicitacaoModel.tenant_id == tenant_id.value)
            .order_by(LicitacaoModel.data_criacao.desc())
        )
        return [self._to_domain(model) for model in result]

    async def get_by_id(self, tenant_id: TenantId, licitacao_id: UUID) -> Licitacao | None:
        model = await self.session.scalar(
            select(LicitacaoModel).where(
                LicitacaoModel.id == licitacao_id,
                LicitacaoModel.tenant_id == tenant_id.value,
            )
        )
        return self._to_domain(model) if model else None

    async def save(self, licitacao: Licitacao) -> Licitacao:
        # The entity carries its TenantId. Never update by globally-known UUID alone.
        model = await self.session.scalar(
            select(LicitacaoModel).where(
                LicitacaoModel.id == licitacao.id,
                LicitacaoModel.tenant_id == licitacao.tenant_id.value,
            )
        )
        if model is None:
            raise ValueError("licitacao not found for tenant-scoped update")
        model.status = licitacao.status.value
        await self.session.flush()
        await self.session.refresh(model)
        await self.session.commit()
        return self._to_domain(model)

    async def total_by_tenant(self, tenant_id: TenantId) -> tuple[Decimal, int]:
        total, quantidade = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(LicitacaoModel.valor_estimado), 0),
                    func.count(LicitacaoModel.id),
                ).where(LicitacaoModel.tenant_id == tenant_id.value)
            )
        ).one()
        return Decimal(total), quantidade

    async def schedule_analysis(
        self, tenant_id: TenantId, licitacao_id: UUID, correlation_id: UUID
    ) -> tuple[Licitacao, AnalysisJob] | None:
        """Persist the state change and outbox record in one database transaction."""

        now = datetime.now(timezone.utc)
        async with self.session.begin():
            model = await self.session.scalar(
                select(LicitacaoModel)
                .where(
                    LicitacaoModel.id == licitacao_id,
                    LicitacaoModel.tenant_id == tenant_id.value,
                )
                .with_for_update()
            )
            if model is None:
                return None

            entity = self._to_domain(model)
            entity.solicitar_analise_ia()
            model.status = entity.status.value
            job_model = AnalysisJobModel(
                id=uuid4(),
                tenant_id=tenant_id.value,
                licitacao_id=licitacao_id,
                correlation_id=correlation_id,
                status=AnalysisJobStatus.PENDING.value,
                attempt_count=0,
                available_at=now,
            )
            self.session.add(job_model)
            await self.session.flush()
            job = self._to_job(job_model)

        return entity, job

    async def claim_analysis_job(
        self,
        job_id: UUID,
        tenant_id: TenantId,
        lock_timeout_seconds: int,
        max_retries: int,
    ) -> AnalysisJob | None:
        """Atomically claim a pending or abandoned job before invoking the AI adapter."""

        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=lock_timeout_seconds)
        pending = and_(
            AnalysisJobModel.status == AnalysisJobStatus.PENDING.value,
            AnalysisJobModel.available_at <= now,
        )
        abandoned = and_(
            AnalysisJobModel.status == AnalysisJobStatus.PROCESSING.value,
            AnalysisJobModel.locked_at.is_not(None),
            AnalysisJobModel.locked_at <= stale_before,
        )
        async with self.session.begin():
            model = await self.session.scalar(
                select(AnalysisJobModel)
                .where(
                    AnalysisJobModel.id == job_id,
                    AnalysisJobModel.tenant_id == tenant_id.value,
                    or_(pending, abandoned),
                )
                .with_for_update()
            )
            if model is None:
                return None
            # A task killed outside the worker's exception handler never gets
            # to record fail_analysis_job. Bound that failure mode here too:
            # an initial attempt plus max_retries is the full durable budget.
            if model.attempt_count > max_retries:
                model.status = AnalysisJobStatus.FAILED.value
                model.completed_at = now
                model.locked_at = None
                model.lock_token = None
                model.dispatch_locked_at = None
                model.dispatch_token = None
                model.last_error = "analysis_execution_lease_expired_after_retry_budget"
                licitacao_model = await self.session.scalar(
                    select(LicitacaoModel)
                    .where(
                        LicitacaoModel.id == model.licitacao_id,
                        LicitacaoModel.tenant_id == tenant_id.value,
                    )
                    .with_for_update()
                )
                if (
                    licitacao_model is not None
                    and licitacao_model.status == LicitacaoStatus.EM_ANALISE_IA.value
                ):
                    licitacao_model.status = LicitacaoStatus.FALHA_ANALISE.value
                return None
            model.status = AnalysisJobStatus.PROCESSING.value
            model.attempt_count += 1
            model.locked_at = now
            model.lock_token = uuid4()
            # Once a worker owns the execution lease, the broker relay lease
            # no longer needs to suppress delivery attempts.
            model.dispatch_locked_at = None
            model.dispatch_token = None
            await self.session.flush()
            return self._to_job(model)

    async def claim_analysis_job_dispatch(
        self, job_id: UUID, tenant_id: TenantId, lease_seconds: int
    ) -> AnalysisJob | None:
        """Atomically lease a row so concurrent relays publish it at most once.

        The lease is intentionally recoverable rather than permanent: a relay
        can crash after claiming the row and before handing it to Redis.
        """

        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=lease_seconds)
        async with self.session.begin():
            model = await self.session.scalar(
                select(AnalysisJobModel)
                .where(
                    AnalysisJobModel.id == job_id,
                    AnalysisJobModel.tenant_id == tenant_id.value,
                    self._dispatchable_condition(now, stale_before),
                )
                .with_for_update(skip_locked=True)
            )
            if model is None:
                return None
            model.dispatch_locked_at = now
            model.dispatch_token = uuid4()
            await self.session.flush()
            return self._to_job(model)

    async def release_analysis_job_dispatch(self, job: AnalysisJob) -> bool:
        """Release only the relay lease owned by this publisher attempt."""

        if job.dispatch_token is None:
            return False
        async with self.session.begin():
            model = await self.session.scalar(
                select(AnalysisJobModel)
                .where(
                    AnalysisJobModel.id == job.id,
                    AnalysisJobModel.tenant_id == job.tenant_id.value,
                    AnalysisJobModel.dispatch_token == job.dispatch_token,
                )
                .with_for_update()
            )
            if model is None:
                return False
            model.dispatch_locked_at = None
            model.dispatch_token = None
            return True

    async def complete_analysis_job(self, job: AnalysisJob) -> AnalysisJobCompletionOutcome:
        """Commit the domain result and completion marker atomically."""

        now = datetime.now(timezone.utc)
        async with self.session.begin():
            job_model = await self.session.scalar(
                select(AnalysisJobModel)
                .where(
                    AnalysisJobModel.id == job.id,
                    AnalysisJobModel.tenant_id == job.tenant_id.value,
                    AnalysisJobModel.status == AnalysisJobStatus.PROCESSING.value,
                    AnalysisJobModel.lock_token == job.lock_token,
                )
                .with_for_update()
            )
            if job_model is None:
                return AnalysisJobCompletionOutcome.CLAIM_LOST

            licitacao_model = await self.session.scalar(
                select(LicitacaoModel)
                .where(
                    LicitacaoModel.id == job.licitacao_id,
                    LicitacaoModel.tenant_id == job.tenant_id.value,
                )
                .with_for_update()
            )
            if licitacao_model is None or licitacao_model.status != LicitacaoStatus.EM_ANALISE_IA.value:
                job_model.status = AnalysisJobStatus.FAILED.value
                job_model.last_error = "analysis_target_incompatible_state"
                job_model.completed_at = now
                job_model.locked_at = None
                job_model.lock_token = None
                job_model.dispatch_locked_at = None
                job_model.dispatch_token = None
                return AnalysisJobCompletionOutcome.TERMINAL_FAILURE

            entity = self._to_domain(licitacao_model)
            entity.concluir_analise_ia()
            licitacao_model.status = entity.status.value
            job_model.status = AnalysisJobStatus.COMPLETED.value
            job_model.completed_at = now
            job_model.locked_at = None
            job_model.lock_token = None
            job_model.dispatch_locked_at = None
            job_model.dispatch_token = None
            job_model.last_error = None
            return AnalysisJobCompletionOutcome.COMPLETED

    async def fail_analysis_job(
        self, job: AnalysisJob, error_code: str, retry_delay_seconds: int | None
    ) -> bool:
        """Record a retry or a terminal failure while retaining tenant ownership."""

        now = datetime.now(timezone.utc)
        async with self.session.begin():
            job_model = await self.session.scalar(
                select(AnalysisJobModel)
                .where(
                    AnalysisJobModel.id == job.id,
                    AnalysisJobModel.tenant_id == job.tenant_id.value,
                    AnalysisJobModel.status == AnalysisJobStatus.PROCESSING.value,
                    AnalysisJobModel.lock_token == job.lock_token,
                )
                .with_for_update()
            )
            if job_model is None:
                return False

            job_model.last_error = self._safe_error_code(error_code)
            job_model.locked_at = None
            job_model.lock_token = None
            job_model.dispatch_locked_at = None
            job_model.dispatch_token = None
            if retry_delay_seconds is not None:
                job_model.status = AnalysisJobStatus.PENDING.value
                job_model.available_at = now + timedelta(seconds=retry_delay_seconds)
                return True

            job_model.status = AnalysisJobStatus.FAILED.value
            job_model.completed_at = now
            licitacao_model = await self.session.scalar(
                select(LicitacaoModel)
                .where(
                    LicitacaoModel.id == job.licitacao_id,
                    LicitacaoModel.tenant_id == job.tenant_id.value,
                )
                .with_for_update()
            )
            if licitacao_model is not None and licitacao_model.status == LicitacaoStatus.EM_ANALISE_IA.value:
                licitacao_model.status = LicitacaoStatus.FALHA_ANALISE.value
            return True

    async def list_dispatchable_analysis_jobs(
        self, limit: int, lock_timeout_seconds: int
    ) -> list[AnalysisJob]:
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=lock_timeout_seconds)
        async with self.session.begin():
            models = await self.session.scalars(
                select(AnalysisJobModel)
                .where(self._dispatchable_condition(now, stale_before))
                .order_by(AnalysisJobModel.available_at, AnalysisJobModel.created_at)
                .limit(limit)
            )
            return [self._to_job(model) for model in models]
