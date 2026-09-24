import os

from sqlalchemy.engine import make_url
from test_api import client


def test_requested_database_is_actually_used(client):
    requested = os.environ.get('LEGALLENS_TEST_DATABASE_URL', 'sqlite://')
    assert client.app.state.engine.dialect.name == make_url(requested).get_backend_name()
