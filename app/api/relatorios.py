from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_id
from app.application.use_cases import GetGastosTotais
from app.infrastructure.cache import RedisCache
from app.infrastructure.persistence.repositories import SqlAlchemyLicitacaoRepository
from app.infrastructure.persistence.session import get_db_session
from app.infrastructure.redis import get_redis
from app.schemas.licitacao import RelatorioGastos

router = APIRouter(prefix="/api/v1/relatorios", tags=["relatorios"])


@router.get("/gastos-totais", response_model=RelatorioGastos)
async def gastos_totais(
    tenant_id: UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> RelatorioGastos:
    redis = await get_redis()
    cache = RedisCache(redis)
    try:
        report = await GetGastosTotais(SqlAlchemyLicitacaoRepository(session), cache).execute(tenant_id)
        return RelatorioGastos.model_validate(report, from_attributes=True)
    finally:
        await cache.close()
