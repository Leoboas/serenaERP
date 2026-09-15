from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Licitacao, LicitacaoStatus
from app.domain.repositories import LicitacaoReportRepository, LicitacaoRepository
from app.domain.value_objects import TenantId
from app.infrastructure.persistence.models import LicitacaoModel


class SqlAlchemyLicitacaoRepository(LicitacaoRepository, LicitacaoReportRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        await self.session.commit()
        await self.session.refresh(model)
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

    async def get_by_id_unscoped(self, licitacao_id: UUID) -> Licitacao | None:
        model = await self.session.scalar(
            select(LicitacaoModel).where(LicitacaoModel.id == licitacao_id)
        )
        return self._to_domain(model) if model else None

    async def save(self, licitacao: Licitacao) -> Licitacao:
        model = await self.session.scalar(
            select(LicitacaoModel).where(LicitacaoModel.id == licitacao.id)
        )
        if model is None:
            raise ValueError("Licitação não encontrada para atualização")
        model.status = licitacao.status.value
        await self.session.commit()
        await self.session.refresh(model)
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
