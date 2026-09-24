import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema


@pytest.fixture
def test_database_url(tmp_path):
    configured = os.environ.get('LEGALLENS_TEST_DATABASE_URL')
    if not configured:
        yield f'sqlite:///{tmp_path / "test.db"}'
        return
    url = make_url(configured)
    if url.get_backend_name() != 'postgresql':
        raise ValueError('LEGALLENS_TEST_DATABASE_URL must use PostgreSQL')
    schema = 'legallens_test_' + uuid.uuid4().hex
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    try:
        yield url.update_query_dict({'options': f'-csearch_path={schema}'}).render_as_string(
            hide_password=False
        )
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()
