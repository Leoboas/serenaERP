from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NumeroLicitacao = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
DescricaoLicitacao = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=5000)]


class LicitacaoCreate(BaseModel):
    numero: NumeroLicitacao
    descricao: DescricaoLicitacao
    valor_estimado: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class LicitacaoRead(LicitacaoCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    status: str
    data_criacao: datetime


class RelatorioGastos(BaseModel):
    tenant_id: UUID
    total: Decimal
    quantidade: int
