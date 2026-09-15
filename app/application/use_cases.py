import json
from decimal import Decimal
from uuid import UUID

from app.application.dtos import CreateLicitacaoCommand, LicitacaoDTO, ReportDTO
from app.domain.entities import Licitacao
from app.domain.repositories import (
    AnalysisJobPublisher,
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
        await self.cache.delete(f"relatorio:gastos-totais:{command.tenant_id}")
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
    def __init__(self, repository: LicitacaoRepository, publisher: AnalysisJobPublisher) -> None:
        self.repository = repository
        self.publisher = publisher

    async def execute(self, tenant_id: UUID, licitacao_id: UUID) -> LicitacaoDTO | None:
        entity = await self.repository.get_by_id(TenantId(tenant_id), licitacao_id)
        if entity is None:
            return None
        entity.solicitar_analise_ia()
        saved = await self.repository.save(entity)
        self.publisher.publish(saved.id)
        return LicitacaoDTO.from_entity(saved)


class AnalyzeLicitacao:
    def __init__(self, repository: LicitacaoRepository) -> None:
        self.repository = repository

    async def execute(self, licitacao_id: UUID) -> None:
        entity = await self.repository.get_by_id_unscoped(licitacao_id)
        if entity is None:
            return
        entity.concluir_analise_ia()
        await self.repository.save(entity)


class GetGastosTotais:
    def __init__(self, repository: LicitacaoReportRepository, cache: Cache) -> None:
        self.repository = repository
        self.cache = cache

    async def execute(self, tenant_id: UUID) -> ReportDTO:
        key = f"relatorio:gastos-totais:{tenant_id}"
        cached = await self.cache.get(key)
        if cached:
            payload = json.loads(cached)
            return ReportDTO(
                tenant_id=UUID(payload["tenant_id"]),
                total=Decimal(payload["total"]),
                quantidade=payload["quantidade"],
            )
        total, quantidade = await self.repository.total_by_tenant(TenantId(tenant_id))
        report = ReportDTO(tenant_id=tenant_id, total=Decimal(total), quantidade=quantidade)
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
        return report
