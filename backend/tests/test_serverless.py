import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from test_api import register, workspace, CONTRACT


def test_request_processing_survives_app_restart_and_checks_ownership(tmp_path, test_database_url):
    settings = Settings(
        database_url=test_database_url,
        storage_dir=tmp_path / 'files',
        testing=True,
        serverless=True,
        max_upload_mb=3,
    )
    first = create_app(settings)
    with TestClient(first) as client:
        register(client)
        w = workspace(client)
        response = client.post(
            f'/api/workspaces/{w}/documents', files={'file': ('contract.txt', CONTRACT, 'text/plain')}
        )
        assert response.status_code == 202
        doc = response.json()
        assert doc['status'] == 'uploaded'
        assert doc['processing_required'] is True
        cookies = dict(client.cookies)
    with TestClient(create_app(settings)) as client:
        client.cookies.update(cookies)
        assert client.get('/api/capabilities').json()['request_processing'] is True
        result = client.post(f'/api/workspaces/{w}/jobs/{doc["job_id"]}/process')
        assert result.status_code == 200, result.text
        assert result.json()['status'] == 'ready'
        again = client.post(f'/api/workspaces/{w}/jobs/{doc["job_id"]}/process')
        assert again.json()['status'] == 'ready'
        detail = client.get(f'/api/workspaces/{w}/documents/{doc["id"]}').json()
        assert detail['analysis']['clauses']
        assert client.get(f'/api/workspaces/{w}/documents/{doc["id"]}/file').content == CONTRACT
        client.cookies.clear()
        register(client, 'other@example.com')
        assert client.post(f'/api/workspaces/{w}/jobs/{doc["job_id"]}/process').status_code == 404


def test_serverless_rejects_local_production_storage(tmp_path):
    with pytest.raises(ValueError, match='Supabase'):
        create_app(
            Settings(
                serverless=True,
                testing=False,
                database_url='postgresql+psycopg://local/local',
                storage_dir=tmp_path,
            )
        )


def test_postgres_guards_work_across_instances(tmp_path, test_database_url):
    import asyncio
    from fastapi import HTTPException
    from sqlalchemy import text
    from app.cloud_runtime import PostgresRateLimiter, PostgresWorkspaceLocks
    from app.database import database
    from app.main import migrate

    if not test_database_url.startswith('postgresql'):
        pytest.skip('Real PostgreSQL required for distributed guards')
    engine, _ = database(test_database_url, True)
    migrate(engine)
    one, two = PostgresRateLimiter(engine), PostgresRateLimiter(engine)
    one.check('same-account', 1)
    with pytest.raises(HTTPException) as error:
        two.check('same-account', 1)
    assert error.value.status_code == 429

    async def exercise():
        one, two = PostgresWorkspaceLocks(engine), PostgresWorkspaceLocks(engine)
        async with one.hold('same-workspace'):
            with pytest.raises(HTTPException) as error:
                async with two.hold('same-workspace'):
                    pytest.fail('Two workers acquired the same workspace')
            assert error.value.status_code == 409
        async with two.hold('same-workspace'):
            pass

    asyncio.run(exercise())
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE oid = 'documents'::regclass")
        )
    engine.dispose()


def test_serverless_scan_gives_recovery_and_limits_text():
    import fitz
    from app.extraction import extract_document

    pdf = fitz.open()
    pdf.new_page()
    data = pdf.tobytes()
    pdf.close()
    pages = extract_document(data, 'scan.pdf', 'application/pdf', allow_ocr=False)
    assert 'OCR is unavailable' in pages[0]['warning']
    assert pages[0]['quality'] < 0.75
    with pytest.raises(ValueError, match='30'):
        extract_document(b'one\f' * 31, 'text.txt', 'text/plain', max_pages=30)
    with pytest.raises(ValueError, match='100'):
        extract_document(b'x' * 101, 'text.txt', 'text/plain', max_text=100)
