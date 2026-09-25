"""Opt-in paid provider check using only repository-owned synthetic documents.

python evaluation/live.py --confirm-external-processing
Exit 0: at least one verified model answer and all final evidence checks passed.
Exit 2: consent missing. Exit 3: missing/invalid configuration.
Exit 4: provider failure. Exit 5: no verified model output or invalid final evidence.
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.extraction import extract_document
from app.intelligence import analyze_document, answer_question, verify_citation
from app.providers import configured_provider

CASES = (
    ('employment/employment.txt', 'What must employer pay?', 'USD 5,000'),
    ('rental/rental.txt', 'Does the agreement renew automatically?', '60 days'),
    ('nda/nda-v2.txt', 'What is the liability limit?', 'unlimited'),
)


def run(provider, count: int = 3) -> dict:
    started = time.perf_counter()
    results = []
    initial_requests = getattr(provider, 'request_count', None)
    attempts = {'answers': 0}

    class TrackedProvider:
        def answer(self, question, citations):
            attempts['answers'] += 1
            return provider.answer(question, citations)

    for index, (path, question, expected) in enumerate(CASES[:count]):
        data = (ROOT / 'demo' / path).read_bytes()
        if b'SYNTHETIC DEMO' not in data[:200]:
            raise ValueError('The live evaluation accepts only explicitly marked synthetic fixtures.')
        pages = extract_document(data, path, 'text/plain')
        document_id = f'live-synthetic-{index}'
        source = dict(id=document_id, pages=pages, analysis=analyze_document(document_id, pages))
        case_started = time.perf_counter()
        try:
            answer = answer_question(question, [source], provider=TrackedProvider(), embedding_provider=False)
            verified = (
                bool(answer['citations'])
                and not answer['abstained']
                and expected in ' '.join(c['excerpt'] for c in answer['citations'])
                and all(verify_citation(citation, [source]) for citation in answer['citations'])
            )
            model_accepted = answer['mode'] in (
                'Verified extractive model output',
                'AI-generated answer · evidence checked',
            )
            results.append(
                dict(
                    case=path,
                    status='verified_model' if model_accepted else 'extractive_fallback',
                    final_evidence_verified=verified,
                    elapsed_seconds=round(time.perf_counter() - case_started, 3),
                )
            )
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            # Never print provider exception strings, URLs, credentials, prompts or response contents.
            results.append(
                dict(
                    case=path,
                    status='provider_failure',
                    error_type=type(error).__name__,
                    final_evidence_verified=False,
                    elapsed_seconds=round(time.perf_counter() - case_started, 3),
                )
            )
    accepted = sum(row['status'] == 'verified_model' and row['final_evidence_verified'] for row in results)
    fallback = sum(row['status'] == 'extractive_fallback' for row in results)
    failures = sum(row['status'] == 'provider_failure' for row in results)
    final_requests = getattr(provider, 'request_count', None)
    requests = (
        final_requests - initial_requests
        if isinstance(final_requests, int) and isinstance(initial_requests, int)
        else None
    )
    passed = (
        bool(results)
        and not failures
        and accepted > 0
        and all(row['final_evidence_verified'] for row in results)
    )
    status = (
        'provider_failure'
        if failures
        else 'verified'
        if passed and not fallback
        else 'verified_with_fallback'
        if passed
        else 'no_verified_model_output'
    )
    return dict(
        status=status,
        passed=passed,
        executed=True,
        dataset='Synthetic live-provider probe v1',
        cases=len(results),
        provider_answer_attempts=attempts['answers'],
        http_request_attempts=requests,
        accepted_verified_model_outputs=accepted,
        extractive_fallbacks=fallback,
        provider_failures=failures,
        elapsed_seconds=round(time.perf_counter() - started, 3),
        results=results,
        limitations=[
            'This small probe verifies the configured generation service and exact-source contract, not production legal accuracy.',
            'Embeddings remain local; no external embedding calls are made. Retries can incur additional provider charges.',
            'A safe extractive fallback is counted separately and never reported as an accepted model output.',
        ],
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Opt-in live generation check: sends synthetic demo excerpts to the configured provider and may incur charges.',
        epilog='Configuration: LEGALLENS_MODEL_BASE_URL, LEGALLENS_MODEL_API_KEY, LEGALLENS_MODEL_NAME in environment or root .env. Exit codes: 0 verified, 2 consent missing, 3 not configured, 4 provider failure, 5 model verification failure. No private uploads are read.',
    )
    parser.add_argument(
        '--confirm-external-processing',
        action='store_true',
        help='Explicitly permit external processing of synthetic demo text and possible charges.',
    )
    parser.add_argument(
        '--cases',
        type=int,
        choices=(1, 2, 3),
        default=3,
        help='Number of fixed synthetic cases (default 3; up to four HTTP attempts per case including support review).',
    )
    parser.add_argument(
        '--output', type=Path, help='Optional JSON report path. No file is written unless specified.'
    )
    args = parser.parse_args(argv)
    if not args.confirm_external_processing:
        report = dict(
            status='not_run',
            passed=False,
            executed=False,
            http_request_attempts=0,
            reason='Use --confirm-external-processing to permit synthetic text transmission and possible charges.',
        )
        code = 2
    else:
        try:
            provider = configured_provider()
        except ValueError:
            provider = None
        if provider is None:
            report = dict(
                status='not_configured',
                passed=False,
                executed=False,
                http_request_attempts=0,
                reason='Configure the model base URL, API key, and model name; no requests were sent.',
            )
            code = 3
        else:
            report = run(provider, args.cases)
            code = 0 if report['passed'] else 4 if report['provider_failures'] else 5
    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    return code


if __name__ == '__main__':
    sys.exit(main())
