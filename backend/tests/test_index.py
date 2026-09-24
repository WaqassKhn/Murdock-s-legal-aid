from sqlalchemy import select, func

from test_api import client, register, workspace, upload
from app.retrieval import retrieve


def test_ingestion_persists_index_and_deletion_cascades(client):
    from app.database import DocumentChunk

    register(client)
    w = workspace(client)
    doc = upload(client, w)
    with client.app.state.sessions() as db:
        chunks = list(db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == doc['id'])))
        assert chunks
        payloads = [row.payload for row in chunks]
        for row in payloads:
            parent = next(c for c in doc['analysis']['clauses'] if c['id'] == row['clause_id'])
            assert parent['original'][row['start'] : row['end']] == row['child_text']
            assert row['page'] >= 1 and row['local_vector']
    doc['index'] = payloads
    first = retrieve('What must the employer pay?', [doc], embedding_provider=False)
    second = retrieve('What must the employer pay?', [doc], embedding_provider=False)
    assert first == second and first[0]['clause']['clause_type'] == 'Payment'
    assert client.delete(f'/api/workspaces/{w}/documents/{doc["id"]}').status_code == 204
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(DocumentChunk)) == 0


def test_hosted_index_embeds_source_once_and_only_queries_afterward():
    from app.retrieval import build_index
    from test_intelligence import document

    class CountingProvider:
        model = 'test-model'
        base_url = 'https://synthetic.invalid'

        def __init__(self):
            self.calls = []

        def embed(self, texts):
            self.calls.append(texts)
            return [[1.0, 0.0] for _ in texts]

    provider = CountingProvider()
    doc = document('1. Payment\nCustomer must pay USD 500 within 30 days.')
    doc['index'] = build_index(doc, provider)
    source_calls = len(provider.calls)
    retrieve('What is payment?', [doc], embedding_provider=provider)
    retrieve('When is payment?', [doc], embedding_provider=provider)
    assert len(provider.calls) == source_calls + 2
    assert provider.calls[-2:] == [['What is payment?'], ['When is payment?']]


def test_unchanged_analysis_reuses_index(client, monkeypatch):
    import app.extraction

    register(client)
    w = workspace(client)
    doc = upload(client, w)

    def unexpected(*args, **kwargs):
        raise AssertionError('Unchanged source was reparsed')

    monkeypatch.setattr(app.extraction, 'extract_document', unexpected)
    response = client.post(f'/api/workspaces/{w}/documents/{doc["id"]}/analyze')
    assert response.status_code == 202
    assert response.json()['status'] == 'ready'
    assert client.get(f'/api/workspaces/{w}/documents/{doc["id"]}').json()['status'] == 'ready'


def test_encrypted_pdf_failure_has_specific_recovery_and_error_code(client):
    import fitz
    import time

    register(client)
    w = workspace(client)
    with fitz.open() as pdf:
        pdf.new_page().insert_text((30, 30), 'Private synthetic example')
        data = pdf.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='synthetic-owner', user_pw='synthetic-user'
        )
    doc = client.post(
        f'/api/workspaces/{w}/documents', files={'file': ('locked.pdf', data, 'application/pdf')}
    ).json()
    for _ in range(150):
        job = client.get(f'/api/workspaces/{w}/jobs/{doc["job_id"]}').json()
        if job['status'] == 'failed':
            break
        time.sleep(0.03)
    assert job['status'] == 'failed'
    assert 'unlocked copy' in job['error']
    assert job['error_code'] == 'DOCUMENT_PROCESSING_FAILED'


def test_blank_text_rejected_before_creating_analysis(client):
    register(client)
    w = workspace(client)
    response = client.post(
        f'/api/workspaces/{w}/documents', files={'file': ('blank.txt', b' \n\t ', 'text/plain')}
    )
    assert response.status_code == 422
    assert client.get(f'/api/workspaces/{w}/documents').json() == []
