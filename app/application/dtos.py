from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domain.entities import Licitacao


@dataclass(frozen=True, slots=True)
class CreateLicitacaoCommand:
    tenant_id: UUID
    numero: str
    descricao: str
    valor_estimado: Decimal


@dataclass(frozen=True, slots=True)
class LicitacaoDTO:
    id: UUID
    tenant_id: UUID
    numero: str
    descricao: str
    valor_estimado: Decimal
    status: str
    data_criacao: datetime | None

    @classmethod
    def from_entity(cls, licitacao: Licitacao) -> "LicitacaoDTO":
        return cls(
            id=licitacao.id,
            tenant_id=licitacao.tenant_id.value,
            numero=licitacao.numero,
            descricao=licitacao.descricao,
            valor_estimado=licitacao.valor_estimado,
            status=licitacao.status.value,
            data_criacao=licitacao.data_criacao,
        )


@dataclass(frozen=True, slots=True)
class ReportDTO:
    tenant_id: UUID
    total: Decimal
    quantidade: int
