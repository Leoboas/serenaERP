from abc import ABC, abstractmethod
from decimal import Decimal
from uuid import UUID

from app.domain.entities import Licitacao
from app.domain.value_objects import TenantId


class LicitacaoRepository(ABC):
    @abstractmethod
    async def add(self, licitacao: Licitacao) -> Licitacao:
        raise NotImplementedError

    @abstractmethod
    async def list_by_tenant(self, tenant_id: TenantId) -> list[Licitacao]:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, tenant_id: TenantId, licitacao_id: UUID) -> Licitacao | None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id_unscoped(self, licitacao_id: UUID) -> Licitacao | None:
        raise NotImplementedError

    @abstractmethod
    async def save(self, licitacao: Licitacao) -> Licitacao:
        raise NotImplementedError


class LicitacaoReportRepository(ABC):
    @abstractmethod
    async def total_by_tenant(self, tenant_id: TenantId) -> tuple[Decimal, int]:
        raise NotImplementedError


class Cache(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        raise NotImplementedError


class AnalysisJobPublisher(ABC):
    @abstractmethod
    def publish(self, licitacao_id: UUID) -> None:
        raise NotImplementedError
