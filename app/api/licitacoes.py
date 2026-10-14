from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_id
from app.application.dtos import CreateLicitacaoCommand, LicitacaoDTO
from app.application.use_cases import (
    CreateLicitacao,
    GetLicitacao,
    ListLicitacoes,
    RequestLicitacaoAnalysis,
)
from app.core.observability import log_event
from app.domain.entities import InvalidLicitacaoTransition
from app.infrastructure.cache import RedisCache
from app.infrastructure.persistence.repositories import SqlAlchemyLicitacaoRepository
from app.infrastructure.persistence.session import get_db_session
from app.infrastructure.redis import get_redis
from app.schemas.licitacao import LicitacaoCreate, LicitacaoRead

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
    except IntegrityError as exc:
        await session.rollback()
        # The database unique key is the concurrency-safe idempotency boundary
        # for a tenant business number; never expose the driver error.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ja existe uma licitacao com este numero para o tenant",
        ) from exc
    finally:
        try:
            await cache.close()
        except Exception as exc:
            log_event("redis_close_failed", level=30, error_type=type(exc).__name__)


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
    request: Request,
    tenant_id: UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> LicitacaoDTO:
    try:
        licitacao = await RequestLicitacaoAnalysis(
            _repository(session),
        ).execute(tenant_id, licitacao_id, getattr(request.state, "correlation_id", None))
    except InvalidLicitacaoTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A analise de IA nao pode ser solicitada para o estado atual",
        ) from exc
    if licitacao is None:
        raise HTTPException(status_code=404, detail="Licitação não encontrada")
    return licitacao
