from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.value_objects import TenantId


class AnalysisJobStatus(StrEnum):
    """Durable lifecycle states for a tenant-bound analysis request."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AnalysisJobCompletionOutcome(StrEnum):
    """Result of a fenced worker completion attempt."""

    COMPLETED = "COMPLETED"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"
    CLAIM_LOST = "CLAIM_LOST"


@dataclass(frozen=True, slots=True)
class AnalysisJob:
    """Tenant-bound durable request to analyse a licitação."""

    id: UUID
    tenant_id: TenantId
    licitacao_id: UUID
    correlation_id: UUID
    status: AnalysisJobStatus = AnalysisJobStatus.PENDING
    attempt_count: int = 0
    lock_token: UUID | None = None
    # Separate from the execution lock: a relay owns this short-lived lease
    # while it hands the durable record to the broker.
    dispatch_token: UUID | None = None
