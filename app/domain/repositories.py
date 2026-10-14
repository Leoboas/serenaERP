from abc import ABC, abstractmethod
from decimal import Decimal
from uuid import UUID

from app.domain.analysis_jobs import AnalysisJob, AnalysisJobCompletionOutcome
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


class AnalysisJobStore(ABC):
    @abstractmethod
    async def schedule_analysis(
        self, tenant_id: TenantId, licitacao_id: UUID, correlation_id: UUID
    ) -> tuple[Licitacao, AnalysisJob] | None:
        raise NotImplementedError

    @abstractmethod
    async def claim_analysis_job(
        self,
        job_id: UUID,
        tenant_id: TenantId,
        lock_timeout_seconds: int,
        max_retries: int,
    ) -> AnalysisJob | None:
        raise NotImplementedError

    @abstractmethod
    async def claim_analysis_job_dispatch(
        self, job_id: UUID, tenant_id: TenantId, lease_seconds: int
    ) -> AnalysisJob | None:
        """Lease a durable outbox record before publishing it to the broker."""

        raise NotImplementedError

    @abstractmethod
    async def release_analysis_job_dispatch(self, job: AnalysisJob) -> bool:
        """Release a relay lease after a synchronous broker publish failure."""

        raise NotImplementedError

    @abstractmethod
    async def complete_analysis_job(self, job: AnalysisJob) -> AnalysisJobCompletionOutcome:
        raise NotImplementedError

    @abstractmethod
    async def fail_analysis_job(
        self, job: AnalysisJob, error_code: str, retry_delay_seconds: int | None
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def list_dispatchable_analysis_jobs(
        self, limit: int, lock_timeout_seconds: int
    ) -> list[AnalysisJob]:
        raise NotImplementedError
