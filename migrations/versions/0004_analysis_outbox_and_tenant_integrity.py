"""add tenant-scoped analysis outbox and database integrity constraints

Revision ID: 0004_analysis_outbox
Revises: 0003_default_tenant_seed
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_analysis_outbox"
down_revision = "0003_default_tenant_seed"
branch_labels = None
depends_on = None


def _constraint_state(name: str) -> tuple[bool, bool | None]:
    """Return (constraint_exists, standalone_index_is_valid) for safe reruns."""

    bind = op.get_bind()
    constraint_exists = bool(
        bind.scalar(
            sa.text(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = :name AND conrelid = 'licitacoes'::regclass"
                ")"
            ),
            {"name": name},
        )
    )
    index_is_valid = bind.scalar(
        sa.text(
            "SELECT i.indisvalid FROM pg_index i "
            "WHERE i.indexrelid = to_regclass(:qualified_name)"
        ),
        {"qualified_name": f"public.{name}"},
    )
    return constraint_exists, None if index_is_valid is None else bool(index_is_valid)


def _create_unique_constraint_concurrently(name: str, columns: tuple[str, ...]) -> None:
    """Build a tenant key without long write locks and recover a failed rerun."""

    constraint_exists, index_is_valid = _constraint_state(name)
    if constraint_exists:
        return

    column_list = ", ".join(columns)
    with op.get_context().autocommit_block():
        # A busy municipal table must fail the deployment gate quickly rather
        # than silently blocking live API traffic while waiting on DDL locks.
        op.execute("SET lock_timeout = '5s'")
        if index_is_valid is False:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        if index_is_valid is not True:
            op.execute(f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {name} ON licitacoes ({column_list})")

    # A previous attempt can leave a valid standalone index after its short
    # constraint-attachment lock timed out. Reuse it on the next invocation.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"ALTER TABLE licitacoes ADD CONSTRAINT {name} UNIQUE USING INDEX {name}")


def _add_validated_check(name: str, expression: str) -> None:
    """Add/validate a CHECK in a rerunnable, low-blocking sequence."""

    validated = op.get_bind().scalar(
        sa.text(
            "SELECT convalidated FROM pg_constraint "
            "WHERE conname = :name AND conrelid = 'licitacoes'::regclass"
        ),
        {"name": name},
    )
    if validated is None:
        op.execute("SET LOCAL lock_timeout = '5s'")
        op.execute(f"ALTER TABLE licitacoes ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID")
        validated = False
    if not validated:
        op.execute("SET LOCAL lock_timeout = '5s'")
        op.execute(f"ALTER TABLE licitacoes VALIDATE CONSTRAINT {name}")


def upgrade() -> None:
    # Stop with an explicit reason instead of silently rewriting historical data.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM licitacoes WHERE valor_estimado <= 0) THEN
                RAISE EXCEPTION 'Cannot add value constraint: licitacoes.valor_estimado contains non-positive values';
            END IF;
            IF EXISTS (
                SELECT 1 FROM licitacoes
                WHERE status NOT IN ('ABERTA', 'EM_ANALISE_IA', 'ANALISADO', 'ALERTA_RISCO', 'FALHA_ANALISE')
            ) THEN
                RAISE EXCEPTION 'Cannot add status constraint: licitacoes.status contains unsupported values';
            END IF;
            IF EXISTS (
                SELECT 1 FROM licitacoes GROUP BY tenant_id, numero HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'Cannot add tenant business-key constraint: duplicate (tenant_id, numero) values exist';
            END IF;
        END $$;
        """
    )
    _create_unique_constraint_concurrently("uq_licitacoes_tenant_numero", ("tenant_id", "numero"))
    # This exact composite key is required by the cross-tenant-safe outbox FK.
    _create_unique_constraint_concurrently("uq_licitacoes_tenant_id", ("tenant_id", "id"))
    _add_validated_check("ck_licitacoes_valor_estimado_positive", "valor_estimado > 0")
    _add_validated_check(
        "ck_licitacoes_status",
        "status IN ('ABERTA', 'EM_ANALISE_IA', 'ANALISADO', 'ALERTA_RISCO', 'FALHA_ANALISE')",
    )

    op.create_table(
        "analysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("licitacao_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempt_count >= 0", name="ck_analysis_jobs_attempt_count"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_analysis_jobs_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "licitacao_id"],
            ["licitacoes.tenant_id", "licitacoes.id"],
            name="fk_analysis_jobs_tenant_licitacao",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "licitacao_id", name="uq_analysis_jobs_tenant_licitacao"),
    )
    op.create_index("ix_analysis_jobs_tenant_id", "analysis_jobs", ["tenant_id"])
    op.create_index("ix_analysis_jobs_correlation_id", "analysis_jobs", ["correlation_id"])
    op.create_index("ix_analysis_jobs_dispatch", "analysis_jobs", ["status", "available_at"])


def downgrade() -> None:
    op.drop_index("ix_analysis_jobs_dispatch", table_name="analysis_jobs")
    op.drop_index("ix_analysis_jobs_correlation_id", table_name="analysis_jobs")
    op.drop_index("ix_analysis_jobs_tenant_id", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
    op.drop_constraint("ck_licitacoes_status", "licitacoes", type_="check")
    op.drop_constraint("ck_licitacoes_valor_estimado_positive", "licitacoes", type_="check")
    op.drop_constraint("uq_licitacoes_tenant_id", "licitacoes", type_="unique")
    op.drop_constraint("uq_licitacoes_tenant_numero", "licitacoes", type_="unique")
