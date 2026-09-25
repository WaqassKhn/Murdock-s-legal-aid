"""Shared request limits and defense against public database API access."""

from alembic import op
import sqlalchemy as sa

revision = '0004_cloud_guards'
down_revision = '0003_personal_tasks'
branch_labels = None
depends_on = None

TABLES = (
    'users',
    'session_tokens',
    'workspaces',
    'documents',
    'document_versions',
    'document_pages',
    'document_sections',
    'document_chunks',
    'clauses',
    'entities',
    'obligations',
    'risk_findings',
    'comparisons',
    'chat_sessions',
    'messages',
    'citations',
    'analysis_runs',
    'generated_reports',
    'request_limits',
)


def upgrade():
    op.create_table(
        'request_limits',
        sa.Column('key', sa.String(64), primary_key=True),
        sa.Column('window', sa.BigInteger(), primary_key=True),
        sa.Column('count', sa.Integer(), nullable=False),
    )
    if op.get_bind().dialect.name == 'postgresql':
        # The backend connects as the table owner; anonymous Data API roles get no policies.
        for table in TABLES:
            op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    op.drop_table('request_limits')
    # Keep source tables protected; reverting a limiter must not expose private records.
