"""add tenant CNPJ and seed the default local tenant"""

import sqlalchemy as sa
from alembic import op


revision = "0003_default_tenant_seed"
down_revision = "0002_reporting_indexes"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("tenants", sa.Column("cnpj", sa.String(length=14), nullable=True))
    op.execute(
        """
        INSERT INTO tenants (id, name, schema_name, status, cnpj)
        VALUES (
            '00000000-0000-0000-0000-000000000001',
            'Prefeitura de Teste (Seed)',
            'prefeitura_teste_seed',
            'ATIVO',
            '00000000000191'
        )
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_column("tenants", "cnpj")
