import threading
import time

import pytest

from sqlalchemy import event

from app.database import Document
from test_api import client, register, upload, workspace
from test_intelligence import document


def test_personal_edits_saved_during_reanalysis_are_not_overwritten(client):
    register(client)
    w = workspace(client)
    source = upload(client, w)
    obligation = client.get(f'/api/workspaces/{w}/obligations').json()[0]
    # A partial document can be retried (ready immutable results otherwise use the cache).
    with client.app.state.sessions() as db:
        db.get(Document, source['id']).status = 'partially_processed'
        db.commit()
    reached, release = threading.Event(), threading.Event()

    def pause_before_replace(connection, cursor, statement, parameters, context, many):
        if statement.startswith('DELETE FROM document_pages'):
            reached.set()
            assert release.wait(10), 'Test did not release processing'

    event.listen(client.app.state.engine, 'before_cursor_execute', pause_before_replace)
    try:
        retry = client.post(f'/api/workspaces/{w}/documents/{source["id"]}/analyze').json()
        assert reached.wait(10), 'Job never reached its persistence stage'
        edits = {
            'user_action': 'Prepare my notice for review',
            'user_notes': 'Keep the original email',
            'status': 'complete',
        }
        response = client.patch(f'/api/workspaces/{w}/action-plan/obligations/{obligation["id"]}', json=edits)
        assert response.status_code == 200
        release.set()
        for _ in range(150):
            job = client.get(f'/api/workspaces/{w}/jobs/{retry["id"]}').json()
            if job['status'] in ('ready', 'failed', 'partially_processed'):
                break
            time.sleep(0.03)
        assert job['status'] == 'ready'
        saved = next(
            o
            for o in client.get(f'/api/workspaces/{w}/action-plan').json()['responsibilities']
            if o['id'] == obligation['id']
        )
        assert {key: saved[key] for key in edits} == edits
        assert saved['action'] == obligation['action']
    finally:
        release.set()
        event.remove(client.app.state.engine, 'before_cursor_execute', pause_before_replace)


def test_secondary_review_pattern_cannot_downgrade_high_attention():
    source = document(
        '1. Liability\nRecipient shall indemnify Discloser for all losses without limit. This obligation survives termination.'
    )
    clause = source['analysis']['clauses'][0]
    assert any(r['severity'] == 'High attention' for r in source['analysis']['risks'])
    assert clause['attention'] == 'High attention'


@pytest.mark.parametrize(
    'body',
    [{'choices': None}, {'choices': [{'message': None}]}, {'choices': [{'message': {'content': None}}]}],
)
def test_malformed_provider_containers_retry_and_return_safe_failure(monkeypatch, body):
    import httpx
    from app.providers import OpenAICompatibleProvider

    calls = []

    def post(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, request=httpx.Request('POST', url), json=body)

    monkeypatch.setattr(httpx, 'post', post)
    provider = OpenAICompatibleProvider('https://synthetic.invalid', 'test-only', 'configured-model')
    with pytest.raises(RuntimeError, match='validated output'):
        provider.answer('What is payment?', [])
    assert len(calls) == 2


def test_personal_task_migration_preserves_legacy_notes(client):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    from app.main import migrate
    from app.database import Obligation

    register(client)
    w = workspace(client)
    upload(client, w)
    item = client.get(f'/api/workspaces/{w}/action-plan').json()['responsibilities'][0]
    edit = {
        'user_action': 'Bring my offer letter',
        'user_notes': 'Discuss the notice period',
        'status': 'complete',
    }
    assert (
        client.patch(f'/api/workspaces/{w}/action-plan/obligations/{item["id"]}', json=edit).status_code
        == 200
    )
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'migrations'))
    with client.app.state.engine.begin() as connection:
        config.attributes['connection'] = connection
        command.downgrade(config, '0002_persistent_index')
    migrate(client.app.state.engine)
    saved = next(
        o
        for o in client.get(f'/api/workspaces/{w}/action-plan').json()['responsibilities']
        if o['id'] == item['id']
    )
    assert {key: saved[key] for key in edit} == edit
    with client.app.state.sessions() as db:
        assert 'user_notes' not in db.get(Obligation, item['id']).payload
