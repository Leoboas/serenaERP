from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_id
from app.application.dtos import CreateLicitacaoCommand, LicitacaoDTO
from app.application.use_cases import (
    CreateLicitacao,
    GetLicitacao,
    ListLicitacoes,
    RequestLicitacaoAnalysis,
)
from app.infrastructure.cache import RedisCache
from app.infrastructure.messaging import CeleryAnalysisJobPublisher
from app.infrastructure.persistence.repositories import SqlAlchemyLicitacaoRepository
from app.infrastructure.persistence.session import get_db_session
from app.infrastructure.redis import get_redis
from app.schemas.licitacao import LicitacaoCreate, LicitacaoRead
from app.workers.ai_worker import analisar_licitacao  # noqa: F401

router = APIRouter(prefix="/api/v1/licitacoes", tags=["licitacoes"])


def _repository(session: AsyncSession) -> SqlAlchemyLicitacaoRepository:
    return SqlAlchemyLicitacaoRepository(session)


@router.post("/", response_model=LicitacaoRead, status_code=status.HTTP_201_CREATED)
async def criar_licitacao(
    payload: LicitacaoCreate,
    tenant_id: UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> LicitacaoDTO:
    redis = await get_redis()
    cache = RedisCache(redis)
    try:
        use_case = CreateLicitacao(_repository(session), cache)
        return await use_case.execute(
            CreateLicitacaoCommand(
                tenant_id=tenant_id,
                numero=payload.numero,
                descricao=payload.descricao,
                valor_estimado=payload.valor_estimado,
            )
        )
    finally:
        await cache.close()


@router.get("/", response_model=list[LicitacaoRead])
async def listar_licitacoes(
    tenant_id: UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[LicitacaoDTO]:
    return await ListLicitacoes(_repository(session)).execute(tenant_id)


@router.get("/{licitacao_id}", response_model=LicitacaoRead)
async def obter_licitacao(
    licitacao_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> LicitacaoDTO:
    licitacao = await GetLicitacao(_repository(session)).execute(tenant_id, licitacao_id)
    if licitacao is None:
        raise HTTPException(status_code=404, detail="Licitação não encontrada")
    return licitacao


@router.post("/{licitacao_id}/analisar-ia", response_model=LicitacaoRead)
async def solicitar_analise_ia(
    licitacao_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> LicitacaoDTO:
    publisher = CeleryAnalysisJobPublisher()
    licitacao = await RequestLicitacaoAnalysis(_repository(session), publisher).execute(
        tenant_id, licitacao_id
    )
    if licitacao is None:
        raise HTTPException(status_code=404, detail="Licitação não encontrada")
    return licitacao
