"""Real API/database integration with an in-memory Supabase HTTP boundary, not live cloud proof."""

import json

import fitz
import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import SupabaseStorage
from test_api import CONTRACT, register, workspace


@pytest.fixture
def cloud_objects(monkeypatch):
    state = {'objects': {}, 'requests': [], 'fail_delete_key': None}

    def handle(request):
        state['requests'].append((request.method, request.url.path))
        assert request.url.host == 'integration.supabase.co'
        assert request.headers['apikey'] == 'sb_secret_test'
        assert 'authorization' not in request.headers
        path = request.url.path
        if request.method == 'POST':
            assert path.startswith('/storage/v1/object/legallens-documents/')
            assert request.headers['x-upsert'] == 'true'
            state['objects'][path.rsplit('/', 1)[1]] = request.content
            return httpx.Response(200, json={})
        if request.method == 'GET':
            assert path.startswith('/storage/v1/object/authenticated/legallens-documents/')
            content = state['objects'].get(path.rsplit('/', 1)[1])
            return httpx.Response(404) if content is None else httpx.Response(200, content=content)
        assert request.method == 'DELETE'
        assert path == '/storage/v1/object/legallens-documents'
        keys = json.loads(request.content)['prefixes']
        if state['fail_delete_key'] in keys:
            return httpx.Response(503, text='Do not expose this private provider response')
        for key in keys:
            state['objects'].pop(key, None)
        return httpx.Response(200, json=[])

    original_init = SupabaseStorage.__init__

    def mock_init(self, *args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(handle)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(SupabaseStorage, '__init__', mock_init)
    return state


def settings_for(test_database_url, directory):
    return Settings(
        _env_file=None,
        database_url=test_database_url,
        storage_dir=directory,
        testing=True,
        serverless=True,
        supabase_url='https://integration.supabase.co',
        supabase_secret_key='sb_secret_test',
        max_upload_mb=3,
        max_pages=30,
        expensive_requests_per_minute=100,
    )


def test_cloud_pdf_report_and_citations_survive_instances(tmp_path, test_database_url, cloud_objects):
    with fitz.open() as pdf:
        pdf.new_page().insert_text((40, 40), CONTRACT.decode(), fontsize=10)
        original = pdf.tobytes()

    with TestClient(create_app(settings_for(test_database_url, tmp_path / 'upload-instance'))) as client:
        register(client)
        w = workspace(client)
        response = client.post(
            f'/api/workspaces/{w}/documents', files={'file': ('source.pdf', original, 'application/pdf')}
        )
        assert response.status_code == 202, response.text
        doc = response.json()
        assert doc['status'] == 'uploaded'
        assert doc['processing_required'] is True
        owner_cookies = dict(client.cookies)
        assert len(cloud_objects['objects']) == 1

    with TestClient(create_app(settings_for(test_database_url, tmp_path / 'processing-instance'))) as client:
        client.cookies.update(owner_cookies)
        response = client.post(f'/api/workspaces/{w}/jobs/{doc["job_id"]}/process')
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'ready'
        analyzed = client.get(f'/api/workspaces/{w}/documents/{doc["id"]}').json()
        citation = analyzed['analysis']['clauses'][0]['citations'][0]
        report = client.post(
            f'/api/workspaces/{w}/reports', json={'format': 'pdf', 'objective': 'Review notice obligations'}
        )
        assert report.status_code == 201, report.text
        report_id = report.json()['id']
        assert len(cloud_objects['objects']) == 2

    with TestClient(create_app(settings_for(test_database_url, tmp_path / 'download-instance'))) as client:
        client.cookies.update(owner_cookies)
        assert client.get(f'/api/workspaces/{w}/documents/{doc["id"]}/file').content == original
        resolved = client.post(f'/api/workspaces/{w}/citations/resolve', json=citation)
        assert resolved.status_code == 200 and resolved.json()['verified']
        preview = client.post(f'/api/workspaces/{w}/citations/preview', json=citation)
        assert preview.status_code == 200, preview.text
        assert preview.content.startswith(b'\x89PNG\r\n\x1a\n')
        report = client.get(f'/api/workspaces/{w}/reports/{report_id}/download')
        assert report.status_code == 200 and report.content.startswith(b'%PDF-')
        with fitz.open(stream=report.content, filetype='pdf') as pdf:
            assert 'not legal advice' in ''.join(page.get_text() for page in pdf)

        client.cookies.clear()
        register(client, 'outsider@example.com')
        storage_requests = len(cloud_objects['requests'])
        for path in (
            f'/api/workspaces/{w}/documents/{doc["id"]}/file',
            f'/api/workspaces/{w}/reports/{report_id}/download',
        ):
            assert client.get(path).status_code == 404
        assert client.post(f'/api/workspaces/{w}/citations/preview', json=citation).status_code == 404
        assert client.delete(f'/api/workspaces/{w}/documents/{doc["id"]}').status_code == 404
        assert len(cloud_objects['requests']) == storage_requests

        client.cookies.clear()
        client.cookies.update(owner_cookies)
        assert client.delete(f'/api/workspaces/{w}/documents/{doc["id"]}').status_code == 204
        assert not cloud_objects['objects']
        assert client.get(f'/api/workspaces/{w}/reports').json() == []
    for directory in ('upload-instance', 'processing-instance', 'download-instance'):
        assert not list((tmp_path / directory).iterdir())


@pytest.mark.parametrize('delete_workspace', [False, True])
def test_cloud_partial_delete_retains_retryable_records(
    tmp_path, test_database_url, cloud_objects, delete_workspace
):
    with TestClient(create_app(settings_for(test_database_url, tmp_path / 'files'))) as client:
        register(client)
        w = workspace(client)
        response = client.post(
            f'/api/workspaces/{w}/documents', files={'file': ('source.txt', CONTRACT, 'text/plain')}
        )
        assert response.status_code == 202
        doc = response.json()
        assert client.post(f'/api/workspaces/{w}/jobs/{doc["job_id"]}/process').status_code == 200
        report = client.post(f'/api/workspaces/{w}/reports', json={'format': 'pdf'}).json()
        report_key = next(key for key in cloud_objects['objects'] if key.endswith('.pdf'))
        cloud_objects['fail_delete_key'] = report_key
        endpoint = f'/api/workspaces/{w}'
        if not delete_workspace:
            endpoint += f'/documents/{doc["id"]}'
        failed = client.delete(endpoint)
        assert failed.status_code == 503, failed.text
        assert 'private provider' not in failed.text
        # Source deletion already succeeded; the report pointer must remain so a retry can finish.
        assert list(cloud_objects['objects']) == [report_key]
        assert client.get(f'/api/workspaces/{w}/documents/{doc["id"]}').status_code == 200
        assert client.get(f'/api/workspaces/{w}/reports').json()[0]['id'] == report['id']
        cloud_objects['fail_delete_key'] = None
        assert client.delete(endpoint).status_code == 204
        assert not cloud_objects['objects']
        assert client.get(f'/api/workspaces/{w}/documents/{doc["id"]}').status_code == 404
