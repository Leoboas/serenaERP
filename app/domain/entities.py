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
    FALHA_ANALISE = "FALHA_ANALISE"


class InvalidLicitacaoTransition(ValueError):
    """Raised when an analysis state transition would duplicate or corrupt work."""


@dataclass(slots=True)
class Licitacao:
    tenant_id: TenantId
    numero: str
    descricao: str
    valor_estimado: Decimal
    id: UUID = field(default_factory=uuid4)
    status: LicitacaoStatus = LicitacaoStatus.ABERTA
    data_criacao: datetime | None = None

    def __post_init__(self) -> None:
        if not self.numero.strip():
            raise ValueError("numero da licitacao nao pode ser vazio")
        if not self.descricao.strip():
            raise ValueError("descricao da licitacao nao pode ser vazia")
        if self.valor_estimado <= Decimal("0"):
            raise ValueError("valor estimado deve ser maior que zero")

    def solicitar_analise_ia(self) -> None:
        if self.status is not LicitacaoStatus.ABERTA:
            raise InvalidLicitacaoTransition(
                f"não é possível solicitar análise para licitação em estado {self.status}"
            )
        self.status = LicitacaoStatus.EM_ANALISE_IA

    def concluir_analise_ia(self) -> None:
        if self.status is not LicitacaoStatus.EM_ANALISE_IA:
            raise InvalidLicitacaoTransition(
                f"não é possível concluir análise para licitação em estado {self.status}"
            )
        self.status = (
            LicitacaoStatus.ALERTA_RISCO
            if self.valor_estimado > Decimal(1_000_000)
            else LicitacaoStatus.ANALISADO
        )

    def falhar_analise_ia(self) -> None:
        if self.status is not LicitacaoStatus.EM_ANALISE_IA:
            raise InvalidLicitacaoTransition(
                f"não é possível registrar falha para licitação em estado {self.status}"
            )
        self.status = LicitacaoStatus.FALHA_ANALISE
