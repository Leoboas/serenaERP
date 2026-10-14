"""add recoverable relay lease to the analysis outbox

Revision ID: 0005_outbox_dispatch_lease
Revises: 0004_analysis_outbox
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_outbox_dispatch_lease"
down_revision = "0004_analysis_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The execution lease and broker-relay lease are deliberately distinct.
    # A broker publish may succeed without a worker starting the job yet.
    op.add_column("analysis_jobs", sa.Column("dispatch_locked_at", sa.DateTime(timezone=True)))
    op.add_column("analysis_jobs", sa.Column("dispatch_token", postgresql.UUID(as_uuid=True)))
    # Keep this revision fully transactional. Unlike licitacoes in 0004,
    # analysis_jobs is introduced immediately before it and can safely trade a
    # short lock for all-or-nothing retryability if a deployment is interrupted.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        "ALTER TABLE analysis_jobs ADD CONSTRAINT ck_analysis_jobs_dispatch_lease "
        "CHECK ((dispatch_token IS NULL) = (dispatch_locked_at IS NULL)) NOT VALID"
    )
    op.execute("ALTER TABLE analysis_jobs VALIDATE CONSTRAINT ck_analysis_jobs_dispatch_lease")
    op.drop_index("ix_analysis_jobs_dispatch", table_name="analysis_jobs")
    op.create_index(
        "ix_analysis_jobs_dispatch",
        "analysis_jobs",
        ["status", "available_at", "dispatch_locked_at"],
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_index("ix_analysis_jobs_dispatch", table_name="analysis_jobs")
    op.create_index("ix_analysis_jobs_dispatch", "analysis_jobs", ["status", "available_at"])
    op.drop_constraint("ck_analysis_jobs_dispatch_lease", "analysis_jobs", type_="check")
    op.drop_column("analysis_jobs", "dispatch_token")
    op.drop_column("analysis_jobs", "dispatch_locked_at")
