"""Measure the real offline API workflow using temporary synthetic data only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def require(response, status=200):
    if response.status_code != status:
        raise RuntimeError(
            f'Workflow failed: {response.request.method} {response.request.url.path} returned {response.status_code}, expected {status}'
        )
    return response.json()


def index_snapshot(engine) -> dict:
    from sqlalchemy import text

    with engine.connect() as connection:
        rows = [
            tuple(row)
            for row in connection.execute(
                text('SELECT id, document_id, version_id, payload FROM document_chunks ORDER BY id')
            )
        ]
    encoded = json.dumps(rows, sort_keys=True, default=str).encode()
    return {'row_count': len(rows), 'fingerprint': hashlib.sha256(encoded).hexdigest()}


def timed(call):
    start = time.perf_counter()
    value = call()
    return value, round((time.perf_counter() - start) * 1000, 3)


def benchmark() -> dict:
    from fastapi.testclient import TestClient

    outgoing_attempts = []

    def block_network(*args, **kwargs):
        outgoing_attempts.append(1)
        raise AssertionError('Offline benchmark attempted an external HTTP request.')

    async def block_async_network(*args, **kwargs):
        block_network(*args, **kwargs)

    with tempfile.TemporaryDirectory(prefix='legallens-benchmark-') as directory:
        temporary = Path(directory)
        overrides = {
            'LEGALLENS_DATABASE_URL': f'sqlite:///{temporary / "benchmark.db"}',
            'LEGALLENS_STORAGE_DIR': str(temporary / 'files'),
            'LEGALLENS_MODEL_BASE_URL': '',
            'LEGALLENS_MODEL_API_KEY': '',
            'LEGALLENS_MODEL_NAME': '',
            'LEGALLENS_EMBEDDING_BASE_URL': '',
            'LEGALLENS_EMBEDDING_API_KEY': '',
            'LEGALLENS_EMBEDDING_MODEL': '',
            'LEGALLENS_EXPENSIVE_REQUESTS_PER_MINUTE': '1000',
        }
        with (
            patch.dict(os.environ, overrides),
            patch('httpx.HTTPTransport.handle_request', block_network),
            patch('httpx.AsyncHTTPTransport.handle_async_request', block_async_network),
        ):
            # Import only after overriding configuration: main also constructs its default app.
            from app.config import Settings
            from app.main import app as default_app, create_app

            app = create_app(Settings(testing=True))
            try:
                with TestClient(app) as client:
                    require(
                        client.post(
                            '/api/auth/register',
                            json={
                                'email': 'benchmark@example.invalid',
                                'password': 'synthetic-benchmark-password',
                            },
                        ),
                        201,
                    )
                    workspaces = {}
                    for name in ('employment', 'rental', 'nda'):
                        workspaces[name] = require(
                            client.post('/api/workspaces', json={'name': f'SYNTHETIC benchmark {name}'}), 201
                        )['id']
                    ingestion, documents = [], {}
                    for source in sorted((ROOT / 'demo').glob('*/*.txt')):
                        w = workspaces[source.parent.name]
                        start = time.perf_counter()
                        uploaded = require(
                            client.post(
                                f'/api/workspaces/{w}/documents',
                                files={'file': (source.name, source.read_bytes(), 'text/plain')},
                            ),
                            202,
                        )
                        deadline = time.monotonic() + 60
                        while True:
                            doc = require(client.get(f'/api/workspaces/{w}/documents/{uploaded["id"]}'))
                            if doc['status'] == 'failed':
                                raise RuntimeError(f'Ingestion failed for synthetic file {source.name}.')
                            if doc['status'] in ('ready', 'partially_processed'):
                                break
                            if time.monotonic() >= deadline:
                                raise TimeoutError(f'Ingestion exceeded 60 seconds for {source.name}.')
                            time.sleep(0.01)
                        if not doc.get('analysis', {}).get('clauses'):
                            raise AssertionError(f'No clauses extracted from {source.name}.')
                        documents[source.name] = doc
                        ingestion.append(
                            {
                                'file': source.relative_to(ROOT).as_posix(),
                                'source_bytes': source.stat().st_size,
                                'elapsed_ms': round((time.perf_counter() - start) * 1000, 3),
                                'status': doc['status'],
                                'pages': doc['page_count'],
                                'clauses': len(doc['analysis']['clauses']),
                            }
                        )
                    before = index_snapshot(app.state.engine)
                    if not before['row_count']:
                        raise AssertionError('No persisted retrieval chunks found.')
                    questions = []
                    cases = [
                        ('employment', 'employment.txt', 'Can I terminate this agreement early?', False),
                        ('rental', 'rental.txt', 'Is there an automatic renewal?', False),
                        ('nda', 'nda-v1.txt', 'What information must remain confidential?', False),
                        ('employment', 'employment.txt', 'What is my pension contribution rate?', True),
                    ]
                    for group, filename, question, expected_abstention in cases:
                        for repeat in range(3):
                            answer, elapsed = timed(
                                lambda: require(
                                    client.post(
                                        f'/api/workspaces/{workspaces[group]}/ask',
                                        json={
                                            'question': question,
                                            'document_ids': [documents[filename]['id']],
                                        },
                                    )
                                )
                            )
                            if answer['abstained'] != expected_abstention:
                                raise AssertionError(
                                    f'Unexpected abstention result for synthetic question: {question}'
                                )
                            if not expected_abstention and not answer['citations']:
                                raise AssertionError('Supported answer lacks citations.')
                            for citation in answer['citations']:
                                if not require(
                                    client.post(
                                        f'/api/workspaces/{workspaces[group]}/citations/resolve',
                                        json=citation,
                                    )
                                )['verified']:
                                    raise AssertionError('Answer citation failed verification.')
                            questions.append(
                                {
                                    'file': filename,
                                    'question': question,
                                    'repeat': repeat + 1,
                                    'elapsed_ms': elapsed,
                                    'abstained': answer['abstained'],
                                    'verified_citations': len(answer['citations']),
                                }
                            )
                    after = index_snapshot(app.state.engine)
                    if before != after:
                        raise AssertionError('Persisted index changed during repeated questions.')
                    comparison, comparison_ms = timed(
                        lambda: require(
                            client.post(
                                f'/api/workspaces/{workspaces["nda"]}/compare',
                                json={
                                    'left_id': documents['nda-v1.txt']['id'],
                                    'right_id': documents['nda-v2.txt']['id'],
                                },
                            )
                        )
                    )
                    if not comparison['findings']:
                        raise AssertionError('NDA comparison produced no differences.')
                    plan, plan_ms = timed(
                        lambda: require(client.get(f'/api/workspaces/{workspaces["rental"]}/action-plan'))
                    )
                    if not plan['responsibilities'] or not plan['timeline']:
                        raise AssertionError('Action plan lacks responsibilities or timeline.')
                    item = plan['responsibilities'][0]
                    require(
                        client.patch(
                            f'/api/workspaces/{workspaces["rental"]}/action-plan/obligations/{item["id"]}',
                            json={'user_notes': 'Synthetic benchmark note', 'status': 'complete'},
                        )
                    )
                    saved = require(client.get(f'/api/workspaces/{workspaces["rental"]}/action-plan'))
                    if not any(
                        row['id'] == item['id']
                        and row['status'] == 'complete'
                        and row['user_notes'] == 'Synthetic benchmark note'
                        for row in saved['responsibilities']
                    ):
                        raise AssertionError('Action Center edit did not persist.')
                    export = client.get(f'/api/workspaces/{workspaces["rental"]}/action-plan/export')
                    if export.status_code != 200 or 'Synthetic benchmark note' not in export.text:
                        raise AssertionError('Action Center Markdown export failed.')
                    report, report_ms = timed(
                        lambda: require(
                            client.post(
                                f'/api/workspaces/{workspaces["rental"]}/reports',
                                json={
                                    'format': 'pdf',
                                    'objective': 'Prepare synthetic consultation',
                                    'notes': 'Synthetic benchmark only',
                                },
                            ),
                            201,
                        )
                    )
                    pdf = client.get(
                        f'/api/workspaces/{workspaces["rental"]}/reports/{report["id"]}/download'
                    )
                    if pdf.status_code != 200 or not pdf.content.startswith(b'%PDF-'):
                        raise AssertionError('Consultation PDF export failed.')
                    for workspace in workspaces.values():
                        deleted = client.delete(f'/api/workspaces/{workspace}')
                        if deleted.status_code != 204:
                            raise AssertionError('Workspace cleanup API failed.')
                    if index_snapshot(app.state.engine)['row_count'] != 0 or list(
                        (temporary / 'files').iterdir()
                    ):
                        raise AssertionError('Deletion left chunks or source/export files behind.')
            finally:
                default_app.state.engine.dispose()
    if outgoing_attempts:
        raise AssertionError('Offline benchmark attempted network access.')
    latencies = [item['elapsed_ms'] for item in questions]
    return {
        'measured_at_utc': datetime.now(timezone.utc).isoformat(),
        'conditions': {
            'os': platform.system(),
            'os_release': platform.release(),
            'machine': platform.machine(),
            'python': platform.python_version(),
            'logical_cpus': os.cpu_count(),
            'fastapi': version('fastapi'),
            'sqlalchemy': version('sqlalchemy'),
            'mode': 'Offline deterministic extractive analysis; local concept vectors and BM25',
            'transport': 'FastAPI TestClient in process; no browser, HTTP network, TLS, OCR, or live model latency',
            'storage': 'Temporary SQLite database and files; deleted at exit',
            'ingestion_poll_interval_ms': 10,
            'concurrency': 'Sequential API requests; application background processing thread',
            'repetitions_per_question': 3,
        },
        'ingestion': ingestion,
        'questions': questions,
        'question_latency_ms': {
            'median': round(statistics.median(latencies), 3),
            'maximum': max(latencies),
            'sample_count': len(latencies),
        },
        'persisted_index': {
            'rows_before_questions': before['row_count'],
            'rows_after_questions': after['row_count'],
            'ids_and_payloads_unchanged': before == after,
            'method': 'Compare row IDs, source/version IDs, and complete payload SHA-256 before and after twelve questions; does not alone prove zero CPU recomputation',
        },
        'external_http_attempt_count': len(outgoing_attempts),
        'model_call_count': 0,
        'model_call_method': 'All six model/embedding settings explicitly blank; httpx sync/async HTTP transports blocked and counted. This is offline execution, not live-model evidence.',
        'comparison': {'elapsed_ms': comparison_ms, 'finding_count': len(comparison['findings'])},
        'action_plan': {
            'elapsed_ms': plan_ms,
            'responsibilities': len(plan['responsibilities']),
            'timeline_entries': len(plan['timeline']),
            'edit_persistence': 'passed',
            'markdown_export': 'passed',
        },
        'pdf_report': {'generation_elapsed_ms': report_ms, 'download_bytes': len(pdf.content)},
        'workspace_deletion': 'passed; zero remaining chunks or stored files',
        'interpretation': 'One small synthetic local run. These measurements are not throughput, production capacity, model quality, or real-world legal accuracy estimates.',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs' / 'benchmark.json')
    args = parser.parse_args()
    report = benchmark()
    rendered = json.dumps(report, indent=2) + '\n'
    args.output.write_text(rendered, encoding='utf-8')
    print(rendered, end='')


if __name__ == '__main__':
    main()
