from uuid import UUID

from app.domain.repositories import AnalysisJobPublisher
from app.workers.ai_worker import analisar_licitacao


class CeleryAnalysisJobPublisher(AnalysisJobPublisher):
    def publish(self, licitacao_id: UUID) -> None:
        analisar_licitacao.delay(str(licitacao_id))
