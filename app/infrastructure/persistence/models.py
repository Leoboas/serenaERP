import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.base import Base


class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ATIVO")
    cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)
    licitacoes: Mapped[list["LicitacaoModel"]] = relationship(back_populates="tenant")


class LicitacaoModel(Base):
    __tablename__ = "licitacoes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "numero", name="uq_licitacoes_tenant_numero"),
        # PostgreSQL requires an exact unique target for the composite foreign
        # key from analysis_jobs, even though id is also globally unique.
        UniqueConstraint("tenant_id", "id", name="uq_licitacoes_tenant_id"),
        CheckConstraint("valor_estimado > 0", name="ck_licitacoes_valor_estimado_positive"),
        CheckConstraint(
            "status IN ('ABERTA', 'EM_ANALISE_IA', 'ANALISADO', 'ALERTA_RISCO', 'FALHA_ANALISE')",
            name="ck_licitacoes_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero: Mapped[str] = mapped_column(String(50), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    valor_estimado: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ABERTA", index=True)
    data_criacao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    tenant: Mapped[TenantModel] = relationship(back_populates="licitacoes")


class AnalysisJobModel(Base):
    """Transactional outbox record and idempotency boundary for AI analysis."""

    __tablename__ = "analysis_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "licitacao_id"],
            ["licitacoes.tenant_id", "licitacoes.id"],
            name="fk_analysis_jobs_tenant_licitacao",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "licitacao_id", name="uq_analysis_jobs_tenant_licitacao"),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_analysis_jobs_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_analysis_jobs_attempt_count"),
        CheckConstraint(
            "(dispatch_token IS NULL) = (dispatch_locked_at IS NULL)",
            name="ck_analysis_jobs_dispatch_lease",
        ),
        Index("ix_analysis_jobs_dispatch", "status", "available_at", "dispatch_locked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    licitacao_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_token: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    dispatch_locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatch_token: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
