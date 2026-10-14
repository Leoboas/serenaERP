import json
from decimal import Decimal
from uuid import UUID, uuid4

from app.application.dtos import CreateLicitacaoCommand, LicitacaoDTO, ReportDTO
from app.core.observability import log_event
from app.domain.analysis_jobs import AnalysisJob, AnalysisJobCompletionOutcome
from app.domain.entities import Licitacao
from app.domain.repositories import (
    AnalysisJobStore,
    Cache,
    LicitacaoReportRepository,
    LicitacaoRepository,
)
from app.domain.value_objects import TenantId


class CreateLicitacao:
    def __init__(self, repository: LicitacaoRepository, cache: Cache) -> None:
        self.repository = repository
        self.cache = cache

    async def execute(self, command: CreateLicitacaoCommand) -> LicitacaoDTO:
        licitacao = Licitacao(
            tenant_id=TenantId(command.tenant_id),
            numero=command.numero,
            descricao=command.descricao,
            valor_estimado=command.valor_estimado,
        )
        saved = await self.repository.add(licitacao)

        # Reports are an optimization. A cache outage must not turn a committed
        # creation into a client-visible failure and trigger an unsafe retry.
        try:
            await self.cache.delete(f"relatorio:gastos-totais:{command.tenant_id}")
        except Exception as exc:
            log_event(
                "cache_invalidation_failed",
                level=30,
                tenant_id=command.tenant_id,
                entity_id=saved.id,
                error_type=type(exc).__name__,
            )
        return LicitacaoDTO.from_entity(saved)


class ListLicitacoes:
    def __init__(self, repository: LicitacaoRepository) -> None:
        self.repository = repository

    async def execute(self, tenant_id: UUID) -> list[LicitacaoDTO]:
        entities = await self.repository.list_by_tenant(TenantId(tenant_id))
        return [LicitacaoDTO.from_entity(entity) for entity in entities]


class GetLicitacao:
    def __init__(self, repository: LicitacaoRepository) -> None:
        self.repository = repository

    async def execute(self, tenant_id: UUID, licitacao_id: UUID) -> LicitacaoDTO | None:
        entity = await self.repository.get_by_id(TenantId(tenant_id), licitacao_id)
        return LicitacaoDTO.from_entity(entity) if entity else None


class RequestLicitacaoAnalysis:
    def __init__(
        self,
        store: AnalysisJobStore,
    ) -> None:
        self.store = store

    async def execute(
        self,
        tenant_id: UUID,
        licitacao_id: UUID,
        correlation_id: UUID | None = None,
    ) -> LicitacaoDTO | None:
        scheduled = await self.store.schedule_analysis(
            TenantId(tenant_id), licitacao_id, correlation_id or uuid4()
        )
        if scheduled is None:
            return None

        entity, _job = scheduled
        # HTTP only commits the state transition and durable outbox row. A
        # separate relay owns broker I/O, so a slow or unavailable Redis
        # broker cannot block the API event loop or turn a committed request
        # into a transport failure.
        return LicitacaoDTO.from_entity(entity)


class AnalyzeLicitacao:
    def __init__(self, store: AnalysisJobStore) -> None:
        self.store = store

    async def execute(self, job: AnalysisJob) -> AnalysisJobCompletionOutcome:
        # The adapter loads the record and marks both it and the job complete
        # inside one transaction, so a worker crash cannot split the outcome.
        return await self.store.complete_analysis_job(job)


class GetGastosTotais:
    def __init__(self, repository: LicitacaoReportRepository, cache: Cache) -> None:
        self.repository = repository
        self.cache = cache

    async def execute(self, tenant_id: UUID) -> ReportDTO:
        key = f"relatorio:gastos-totais:{tenant_id}"
        try:
            cached = await self.cache.get(key)
            if cached:
                payload = json.loads(cached)
                cached_tenant_id = UUID(payload["tenant_id"])
                if cached_tenant_id != tenant_id:
                    raise ValueError("cache tenant does not match request tenant")
                return ReportDTO(
                    tenant_id=cached_tenant_id,
                    total=Decimal(str(payload["total"])),
                    quantidade=int(payload["quantidade"]),
                )
        except Exception as exc:
            log_event(
                "report_cache_read_failed",
                level=30,
                tenant_id=tenant_id,
                error_type=type(exc).__name__,
            )

        total, quantidade = await self.repository.total_by_tenant(TenantId(tenant_id))
        report = ReportDTO(tenant_id=tenant_id, total=Decimal(total), quantidade=quantidade)
        try:
            await self.cache.set(
                key,
                json.dumps(
                    {
                        "tenant_id": str(report.tenant_id),
                        "total": str(report.total),
                        "quantidade": report.quantidade,
                    }
                ),
                ttl_seconds=60,
            )
        except Exception as exc:
            log_event(
                "report_cache_write_failed",
                level=30,
                tenant_id=tenant_id,
                error_type=type(exc).__name__,
            )
        return report
