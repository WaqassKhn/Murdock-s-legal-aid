"""Persist version-bound clause children and retrieval vectors."""

from alembic import op
import sqlalchemy as sa

revision = '0002_persistent_index'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False
        ),
        sa.Column(
            'version_id',
            sa.String(36),
            sa.ForeignKey('document_versions.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('payload', sa.JSON(), nullable=False),
    )
    op.create_index('ix_document_chunks_document_id', 'document_chunks', ['document_id'])


def downgrade():
    op.drop_table('document_chunks')
