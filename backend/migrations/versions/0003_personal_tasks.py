"""Separate personal planning from replaceable source analysis."""

from alembic import op
import sqlalchemy as sa

revision = '0003_personal_tasks'
down_revision = '0002_persistent_index'
branch_labels = None
depends_on = None


def task_table():
    return sa.table(
        'obligations',
        sa.column('id', sa.String()),
        sa.column('payload', sa.JSON()),
        sa.column('user_action', sa.Text()),
        sa.column('user_notes', sa.Text()),
    )


def upgrade():
    op.add_column('obligations', sa.Column('user_action', sa.Text(), nullable=False, server_default=''))
    op.add_column('obligations', sa.Column('user_notes', sa.Text(), nullable=False, server_default=''))
    # Earlier builds stored personal fields alongside extracted facts.
    table, connection = task_table(), op.get_bind()
    for row in connection.execute(sa.select(table.c.id, table.c.payload)).mappings():
        source = dict(row['payload'])
        action, notes = source.pop('user_action', ''), source.pop('user_notes', '')
        connection.execute(
            table.update()
            .where(table.c.id == row['id'])
            .values(payload=source, user_action=action, user_notes=notes)
        )


def downgrade():
    table, connection = task_table(), op.get_bind()
    for row in connection.execute(sa.select(table)).mappings():
        connection.execute(
            table.update()
            .where(table.c.id == row['id'])
            .values(
                payload={**row['payload'], 'user_action': row['user_action'], 'user_notes': row['user_notes']}
            )
        )
    op.drop_column('obligations', 'user_notes')
    op.drop_column('obligations', 'user_action')
