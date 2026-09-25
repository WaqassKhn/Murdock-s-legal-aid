"""Exercise real generation through a running API using synthetic demo documents only."""

import argparse
import json
import secrets
import time
from pathlib import Path

import httpx


def run(base_url: str) -> dict:
    started = time.perf_counter()
    result = {'passed': False, 'workflow': 'synthetic live API generation', 'checks': {}}
    workspaces = []
    with httpx.Client(base_url=base_url.rstrip('/') + '/api/', timeout=150) as client:

        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response

        try:
            request(
                'POST',
                'auth/register',
                json={
                    'email': f'live-{secrets.token_hex(8)}@example.test',
                    'password': secrets.token_urlsafe(24),
                },
            )
            workspaces = request('POST', 'demo').json()
            documents = {}
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                documents = {
                    w['id']: request('GET', f'workspaces/{w["id"]}/documents').json() for w in workspaces
                }
                if all(
                    d['status'] in ('ready', 'partially_processed', 'failed')
                    for docs in documents.values()
                    for d in docs
                ):
                    break
                time.sleep(2)
            details = {}
            for w in workspaces:
                details[w['id']] = [
                    request('GET', f'workspaces/{w["id"]}/documents/{d["id"]}').json()
                    for d in documents[w['id']]
                ]
            generated = [
                d
                for docs in details.values()
                for d in docs
                if (d.get('analysis') or {}).get('mode', '').startswith('AI-generated analysis')
            ]
            result['checks']['generated_documents'] = len(generated)
            result['checks']['total_documents'] = sum(map(len, details.values()))
            result['checks']['all_documents_generated'] = len(generated) == 4
            for w in workspaces:
                for d in details[w['id']]:
                    for c in (d.get('analysis') or {}).get('summary_citations', []):
                        assert request('POST', f'workspaces/{w["id"]}/citations/resolve', json=c).json()[
                            'verified'
                        ]
            employment = next(w for w in workspaces if w['name'] == 'Employment agreement')
            prefix = f'workspaces/{employment["id"]}'
            answer = request(
                'POST', prefix + '/ask', json={'question': 'Can I terminate this agreement early?'}
            ).json()
            result['checks']['generated_answer'] = answer[
                'mode'
            ] == 'AI-generated answer · evidence checked' and bool(answer['citations'])
            result['checks']['paraphrased_answer'] = all(
                answer['direct_answer'] != c['excerpt'] for c in answer['citations']
            )
            unknown = request(
                'POST', prefix + '/ask', json={'question': 'What is my dental insurance coverage?'}
            ).json()
            result['checks']['unsupported_abstention'] = unknown['abstained']
            plan = request('GET', prefix + '/action-plan').json()
            result['checks']['clause_lawyer_questions'] = any(
                q['id'].startswith('clause-lawyer-') for q in plan['lawyer_questions']
            )
            report = request(
                'POST', prefix + '/reports', json={'format': 'pdf', 'objective': 'Synthetic consultation'}
            ).json()
            result['checks']['pdf_export'] = request(
                'GET', prefix + f'/reports/{report["id"]}/download'
            ).content.startswith(b'%PDF')
            nda = next(w for w in workspaces if w['name'] == 'NDA version comparison')
            versions = sorted(details[nda['id']], key=lambda d: d['name'])
            comparison = request(
                'POST',
                f'workspaces/{nda["id"]}/compare',
                json={'left_id': versions[0]['id'], 'right_id': versions[1]['id']},
            ).json()
            result['checks']['generated_comparison'] = comparison[
                'mode'
            ] == 'AI-generated comparison · evidence checked' and bool(comparison['findings'])
            result['passed'] = all(
                v for k, v in result['checks'].items() if k not in ('generated_documents', 'total_documents')
            )
        except (httpx.HTTPError, ValueError, KeyError, AssertionError, StopIteration) as error:
            result['error_type'] = type(error).__name__
            if isinstance(error, httpx.HTTPStatusError):
                result['http_status'] = error.response.status_code
        finally:
            for w in workspaces:
                response = client.delete(f'workspaces/{w["id"]}')
                if response.status_code != 204:
                    result['cleanup_failed'] = True
                    result['passed'] = False
    result['elapsed_seconds'] = round(time.perf_counter() - started, 2)
    result['limitations'] = [
        'Synthetic smoke test, not a legal-accuracy assessment.',
        'Created workspace data is deleted; the random test account remains.',
    ]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8010')
    parser.add_argument('--confirm-external-processing', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not args.confirm_external_processing:
        parser.error(
            'Explicit consent is required; synthetic data will reach the configured model and incur calls.'
        )
    result = run(args.base_url)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
