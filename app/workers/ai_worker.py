import asyncio
from uuid import UUID

from app.application.use_cases import AnalyzeLicitacao
from app.infrastructure.persistence.repositories import SqlAlchemyLicitacaoRepository
from app.infrastructure.persistence.session import AsyncSessionLocal
from app.workers.celery_app import celery_app


async def analyze_licitacao(licitacao_id: UUID) -> None:
    await asyncio.sleep(2)
    async with AsyncSessionLocal() as session:
        await AnalyzeLicitacao(SqlAlchemyLicitacaoRepository(session)).execute(licitacao_id)


@celery_app.task(name="analisar_licitacao")
def analisar_licitacao(licitacao_id: str) -> None:
    asyncio.run(analyze_licitacao(UUID(licitacao_id)))
