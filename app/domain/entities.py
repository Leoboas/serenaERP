from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.value_objects import TenantId


class LicitacaoStatus(StrEnum):
    ABERTA = "ABERTA"
    EM_ANALISE_IA = "EM_ANALISE_IA"
    ANALISADO = "ANALISADO"
    ALERTA_RISCO = "ALERTA_RISCO"


@dataclass(slots=True)
class Licitacao:
    tenant_id: TenantId
    numero: str
    descricao: str
    valor_estimado: Decimal
    id: UUID = field(default_factory=uuid4)
    status: LicitacaoStatus = LicitacaoStatus.ABERTA
    data_criacao: datetime | None = None

    def solicitar_analise_ia(self) -> None:
        self.status = LicitacaoStatus.EM_ANALISE_IA

    def concluir_analise_ia(self) -> None:
        self.status = (
            LicitacaoStatus.ALERTA_RISCO
            if self.valor_estimado > Decimal(1_000_000)
            else LicitacaoStatus.ANALISADO
        )
