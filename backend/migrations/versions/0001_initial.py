"""Initial immutable document and ownership schema.

Revision ID: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def col(name, type_, *constraints, **kwargs):
    return sa.Column(name, type_, *constraints, **kwargs)


def fk(name, table, **kwargs):
    return col(
        name, sa.String(36), sa.ForeignKey(table + '.id', ondelete='CASCADE'), nullable=False, **kwargs
    )


def table(name, *columns):
    op.create_table(
        name,
        col('id', sa.String(36), primary_key=True),
        col('created_at', sa.DateTime(timezone=True), nullable=False),
        *columns,
    )


def upgrade():
    table(
        'users',
        col('email', sa.String(254), nullable=False, unique=True),
        col('password_hash', sa.Text, nullable=False),
    )
    table(
        'session_tokens',
        fk('user_id', 'users', index=True),
        col('token_hash', sa.String(64), nullable=False, unique=True),
        col('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    table(
        'workspaces',
        fk('user_id', 'users', index=True),
        col('name', sa.String(160), nullable=False),
        col('objective', sa.Text, nullable=False),
        col('jurisdiction', sa.String(160), nullable=False),
        col('is_demo', sa.Boolean, nullable=False),
    )
    table(
        'documents',
        fk('workspace_id', 'workspaces', index=True),
        col('name', sa.String(255), nullable=False),
        col('media_type', sa.String(100), nullable=False),
        col('status', sa.String(32), nullable=False),
        col('storage_key', sa.String(80), nullable=False),
        col('page_count', sa.Integer, nullable=False),
        col('version', sa.Integer, nullable=False),
        col('warnings', sa.JSON, nullable=False),
        col('analysis', sa.JSON, nullable=True),
    )
    table(
        'document_versions',
        fk('document_id', 'documents', unique=True),
        col('sha256', sa.String(64), nullable=False),
        col('version', sa.Integer, nullable=False),
    )
    table(
        'document_pages',
        fk('document_id', 'documents', index=True),
        col('number', sa.Integer, nullable=False),
        col('payload', sa.JSON, nullable=False),
    )
    for name in ('document_sections', 'clauses', 'entities', 'risk_findings', 'citations'):
        table(
            name,
            fk('document_id', 'documents', index=True),
            fk('version_id', 'document_versions'),
            col('payload', sa.JSON, nullable=False),
        )
    table(
        'obligations',
        fk('document_id', 'documents', index=True),
        fk('workspace_id', 'workspaces', index=True),
        fk('version_id', 'document_versions'),
        col('payload', sa.JSON, nullable=False),
        col('status', sa.String(16), nullable=False),
    )
    table(
        'analysis_runs',
        fk('workspace_id', 'workspaces', index=True),
        fk('document_id', 'documents', index=True),
        col('status', sa.String(32), nullable=False),
        col('kind', sa.String(16), nullable=False),
        col('error', sa.Text, nullable=True),
        col('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    table(
        'comparisons',
        fk('workspace_id', 'workspaces', index=True),
        fk('left_id', 'documents'),
        fk('right_id', 'documents'),
        col('payload', sa.JSON, nullable=False),
    )
    table('chat_sessions', fk('workspace_id', 'workspaces', index=True))
    table('messages', fk('session_id', 'chat_sessions', index=True), col('payload', sa.JSON, nullable=False))
    table(
        'generated_reports',
        fk('workspace_id', 'workspaces', index=True),
        col('title', sa.String(255), nullable=False),
        col('format', sa.String(8), nullable=False),
        col('storage_key', sa.String(80), nullable=False),
        col('document_ids', sa.JSON, nullable=False),
    )


def downgrade():
    for name in (
        'generated_reports',
        'messages',
        'chat_sessions',
        'comparisons',
        'analysis_runs',
        'obligations',
        'citations',
        'risk_findings',
        'entities',
        'clauses',
        'document_sections',
        'document_pages',
        'document_versions',
        'documents',
        'workspaces',
        'session_tokens',
        'users',
    ):
        op.drop_table(name)
