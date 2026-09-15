"""initial tenant and licitacao tables"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("schema_name", sa.String(length=63), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.UniqueConstraint("schema_name"),
    )
    op.create_table(
        "licitacoes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("numero", sa.String(length=50), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("valor_estimado", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("data_criacao", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_licitacoes_tenant_id", "licitacoes", ["tenant_id"])
    op.create_index("ix_licitacoes_status", "licitacoes", ["status"])


def downgrade() -> None:
    op.drop_index("ix_licitacoes_status", table_name="licitacoes")
    op.drop_index("ix_licitacoes_tenant_id", table_name="licitacoes")
    op.drop_table("licitacoes")
    op.drop_table("tenants")
