import io
import time

import fitz
import httpx
import pytest
from docx import Document as WordDocument
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.temporary_session import create_session_app, decode, encode, seal, unseal
from test_api import CONTRACT

SECRET = 'test-only-session-secret-with-at-least-32-characters'


def test_empty_vercel_optional_environment_uses_defaults(monkeypatch):
    for name in (
        'SECURE_COOKIES',
        'MAX_UPLOAD_MB',
        'MAX_WORKSPACE_DOCUMENTS',
        'MAX_PAGES',
        'EXPENSIVE_REQUESTS_PER_MINUTE',
        'AUTO_MIGRATE',
        'SERVERLESS',
    ):
        monkeypatch.setenv('LEGALLENS_' + name, '')
    monkeypatch.setenv('LEGALLENS_SESSION_SECRET', SECRET)
    for name in ('MODEL_API_KEY', 'MODEL_BASE_URL', 'MODEL_NAME'):
        monkeypatch.setenv('LEGALLENS_' + name, '')
    settings = Settings(_env_file=None)
    assert settings.max_pages == 200
    assert settings.auto_migrate is True
    assert settings.serverless is False
    with TestClient(create_session_app()) as client:
        assert client.get('/health').status_code == 200
        response = client.post('/api/session', json={'path': '/api/auth/me'})
        assert response.status_code == 200
        assert response.json()['status'] == 401


def test_partial_model_configuration_returns_actionable_error_without_leaking_key():
    settings = Settings(_env_file=None, model_api_key='private-test-key', model_base_url='', model_name='')
    with TestClient(create_session_app(SECRET, settings)) as client:
        for response in [
            client.get('/health'),
            client.post('/api/session', json={'path': '/api/auth/me'}),
        ]:
            assert response.status_code == 503
            assert 'LEGALLENS_MODEL_BASE_URL' in response.json()['detail']
            assert 'LEGALLENS_MODEL_NAME' in response.json()['detail']
            assert 'private-test-key' not in response.text


class BrowserSession:
    def __init__(self):
        self.state = ''
        self.cookies = httpx.Cookies()

    def request(self, method, path, **kwargs):
        request = httpx.Request(method, 'https://testserver' + path, **kwargs)
        body = request.read()
        # A new function instance and new working directory on EVERY call.
        with TestClient(
            create_session_app(SECRET, Settings(_env_file=None)), base_url='https://testserver'
        ) as client:
            client.cookies.update(self.cookies)
            outer = client.post(
                '/api/session',
                json={
                    'path': path,
                    'method': method,
                    'body': encode(body),
                    'state': self.state,
                    'content_type': request.headers.get('content-type', 'application/json'),
                },
            )
            self.cookies.update(client.cookies)
        if outer.status_code != 200:
            return outer
        envelope = outer.json()
        self.state = envelope['state']
        return httpx.Response(
            envelope['status'], headers=envelope['headers'], content=decode(envelope['body'])
        )

    def register(self):
        response = self.request(
            'POST',
            '/api/auth/register',
            json={'email': 'demo@example.com', 'password': 'throwaway-test-password'},
        )
        assert response.status_code == 201, response.text


def test_fresh_instances_upload_analysis_citations_qa_comparison_and_exports():
    browser = BrowserSession()
    browser.register()
    response = browser.request('POST', '/api/workspaces', json={'name': 'Temporary review'})
    assert response.status_code == 201, response.text
    w = response.json()['id']
    prefix = f'/api/workspaces/{w}'
    documents = []
    for data in [CONTRACT, CONTRACT.replace(b'30 days', b'60 days')]:
        response = browser.request(
            'POST', prefix + '/documents', files={'file': ('contract.txt', data, 'text/plain')}
        )
        assert response.status_code == 202, response.text
        doc = response.json()
        assert doc['processing_required']
        result = browser.request('POST', prefix + f'/jobs/{doc["job_id"]}/process')
        assert result.status_code == 200 and result.json()['status'] == 'ready', result.text
        detail = browser.request('GET', prefix + f'/documents/{doc["id"]}').json()
        assert detail['analysis']['clauses']
        citation = detail['analysis']['clauses'][0]['citations'][0]
        resolved = browser.request('POST', prefix + '/citations/resolve', json=citation)
        assert resolved.json()['verified']
        assert browser.request('GET', prefix + f'/documents/{doc["id"]}/file').content == data
        documents.append(doc)
    answer = browser.request(
        'POST', prefix + '/ask', json={'question': 'Can I terminate this agreement early?'}
    )
    assert answer.status_code == 200 and answer.json()['citations'], answer.text
    compared = browser.request(
        'POST', prefix + '/compare', json={'left_id': documents[0]['id'], 'right_id': documents[1]['id']}
    )
    assert compared.status_code == 200 and compared.json()['findings'], compared.text
    for format in ['pdf', 'docx']:
        report = browser.request(
            'POST',
            prefix + '/reports',
            json={'format': format, 'objective': 'Understand termination', 'notes': 'Ask about notice.'},
        )
        assert report.status_code == 201, report.text
        downloaded = browser.request('GET', prefix + f'/reports/{report.json()["id"]}/download')
        assert downloaded.status_code == 200
        if format == 'pdf':
            with fitz.open(stream=downloaded.content, filetype='pdf') as pdf:
                assert 'Ask about notice' in ''.join(page.get_text() for page in pdf)
        else:
            assert WordDocument(io.BytesIO(downloaded.content)).paragraphs
    for endpoint in ['/checklist', '/action-plan/export']:
        result = browser.request('GET', prefix + endpoint)
        assert result.status_code == 200 and len(result.content) > 100
    intruder = BrowserSession()
    intruder.register()
    assert intruder.request('GET', prefix + '/documents').status_code == 404
    intruder.state = browser.state
    assert intruder.request('GET', prefix + '/documents').status_code == 401
    browser.state = ''  # Refresh loses the entire account and workspace.
    assert browser.request('GET', '/api/auth/me').status_code == 401


def test_session_limits_tampering_expiry_and_configuration():
    with TestClient(create_session_app('', Settings(_env_file=None))) as client:
        assert client.get('/health').status_code == 503
    token = seal({'created': time.time(), 'files': {}}, SECRET.encode())
    with pytest.raises(HTTPException):
        unseal('0' + token[1:], SECRET.encode())
    expired = seal({'created': time.time() - 7201, 'files': {}}, SECRET.encode())
    with pytest.raises(HTTPException):
        unseal(expired, SECRET.encode())
    browser = BrowserSession()
    browser.register()
    w = browser.request('POST', '/api/workspaces', json={'name': 'Limits'}).json()['id']
    result = browser.request(
        'POST',
        f'/api/workspaces/{w}/documents',
        files={'file': ('large.txt', b'x' * (1024 * 1024 + 1), 'text/plain')},
    )
    assert result.status_code == 413, result.text
    with TestClient(create_session_app(SECRET, Settings(_env_file=None))) as client:
        assert client.post('/api/session', content=b'x' * 4_000_001).status_code == 413
        assert (
            client.post('/api/session', json={}, headers={'Origin': 'https://attacker.invalid'}).status_code
            == 403
        )
    with pytest.raises(HTTPException) as error:
        seal({'files': {'large': 'x' * 12_000_001}}, SECRET.encode())
    assert error.value.status_code == 413
