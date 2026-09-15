"""indexes for tenant reports and active analysis queries"""

import sqlalchemy as sa
from alembic import op

revision = "0002_reporting_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_licitacoes_tenant_status_created",
        "licitacoes",
        ["tenant_id", "status", "data_criacao"],
    )
    op.create_index(
        "ix_licitacoes_active_by_tenant",
        "licitacoes",
        ["tenant_id", "data_criacao"],
        postgresql_where=sa.text("status IN ('ABERTA', 'EM_ANALISE_IA')"),
    )


def downgrade() -> None:
    op.drop_index("ix_licitacoes_active_by_tenant", table_name="licitacoes")
    op.drop_index("ix_licitacoes_tenant_status_created", table_name="licitacoes")
