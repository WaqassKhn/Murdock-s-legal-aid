"""Action Center keeps personal planning separate from source-backed obligations."""

from test_api import client, register, upload, workspace


def test_action_plan_persists_user_edits_without_rewriting_source(client):
    register(client)
    w = workspace(client)
    document = upload(client, w)
    response = client.get(f'/api/workspaces/{w}/action-plan')
    assert response.status_code == 200, response.text
    plan = response.json()
    obligation = plan['responsibilities'][0]
    original = obligation['action']
    edits = {
        'user_action': 'Ask payroll to confirm the first payment.',
        'user_notes': 'Bring the offer email.',
        'status': 'complete',
    }
    changed = client.patch(f'/api/workspaces/{w}/action-plan/obligations/{obligation["id"]}', json=edits)
    assert changed.status_code == 200, changed.text
    assert changed.json()['action'] == original
    assert changed.json()['citations'] == obligation['citations']
    saved = client.get(f'/api/workspaces/{w}/action-plan').json()['responsibilities'][0]
    for key, value in edits.items():
        assert saved[key] == value
    source = client.get(f'/api/workspaces/{w}/documents/{document["id"]}').json()
    assert source['analysis'] == document['analysis']
    export = client.get(f'/api/workspaces/{w}/action-plan/export')
    assert export.status_code == 200
    assert export.headers['content-type'].startswith('text/markdown')
    assert 'attachment;' in export.headers['content-disposition']
    assert 'User-authored action' in export.text and edits['user_action'] in export.text
    assert 'Document obligation' in export.text and 'not legal advice' in export.text
    assert document['id'] in export.text


def test_action_plan_preserves_relative_deadlines_and_evidence(client):
    register(client)
    w = workspace(client)
    doc = upload(client, w)
    plan = client.get(f'/api/workspaces/{w}/action-plan').json()
    assert plan['responsibilities']
    relative = [
        event
        for event in plan['timeline']
        if 'after' in event['expression'].lower() or 'notice' in event['expression'].lower()
    ]
    assert relative
    assert all(event['calendar_date'] is None for event in relative)
    assert all(event['kind'] == 'relative' for event in relative)
    assert all(event['explanation'] for event in relative)
    assert plan['lawyer_questions']
    assert plan['preparation_evidence']
    for citation in plan['preparation_evidence']:
        assert citation['document_id'] == doc['id']
        assert client.post(f'/api/workspaces/{w}/citations/resolve', json=citation).status_code == 200


def test_action_plan_rejects_source_mutation_and_unbounded_or_null_edits(client):
    register(client)
    w = workspace(client)
    upload(client, w)
    obligation = client.get(f'/api/workspaces/{w}/obligations').json()[0]
    path = f'/api/workspaces/{w}/action-plan/obligations/{obligation["id"]}'
    for payload in (
        {'action': 'Forged source'},
        {'citations': []},
        {'user_notes': 'x' * 4001},
        {'user_action': None},
        {'status': 'waived'},
        {},
    ):
        assert client.patch(path, json=payload).status_code == 422
    assert (
        client.patch(path, json={'user_action': 'Personal action', 'user_notes': 'Context'}).status_code
        == 200
    )
    assert client.patch(path, json={'user_action': ''}).json()['user_action'] == ''
    saved = next(
        item
        for item in client.get(f'/api/workspaces/{w}/action-plan').json()['responsibilities']
        if item['id'] == obligation['id']
    )
    assert saved['user_notes'] == 'Context'


def test_action_plan_cannot_read_or_mutate_another_workspace_or_account(client):
    register(client)
    w = workspace(client)
    upload(client, w)
    item = client.get(f'/api/workspaces/{w}/obligations').json()[0]
    other = workspace(client, 'Separate workspace')
    assert (
        client.patch(
            f'/api/workspaces/{other}/action-plan/obligations/{item["id"]}',
            json={'user_notes': 'Cross-workspace write'},
        ).status_code
        == 404
    )
    assert client.get(f'/api/workspaces/{other}/action-plan').json()['responsibilities'] == []
    client.post('/api/auth/logout')
    assert client.get(f'/api/workspaces/{w}/action-plan').status_code == 401
    register(client, 'other-owner@example.test')
    for suffix in ('action-plan', 'action-plan/export'):
        assert client.get(f'/api/workspaces/{w}/{suffix}').status_code == 404
    assert (
        client.patch(
            f'/api/workspaces/{w}/action-plan/obligations/{item["id"]}',
            json={'user_notes': 'Cross-owner write'},
        ).status_code
        == 404
    )


def test_markdown_export_escapes_user_content_and_keeps_source_distinct(client):
    register(client)
    w = workspace(client)
    upload(client, w)
    item = client.get(f'/api/workspaces/{w}/obligations').json()[0]
    response = client.patch(
        f'/api/workspaces/{w}/action-plan/obligations/{item["id"]}',
        json={
            'user_notes': '<script>alert(1)</script>\n# Forged authority\n[click](https://invalid.example)'
        },
    )
    assert response.status_code == 200
    text = client.get(f'/api/workspaces/{w}/action-plan/export').text
    assert '<script>' not in text
    assert '\n# Forged authority' not in text
    assert '[click](https://invalid.example)' not in text
