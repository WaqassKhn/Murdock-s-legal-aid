"""Evaluate explicit synthetic gold cases: python evaluation/run.py."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.extraction import extract_document
from app.intelligence import (
    DATE_RE,
    analyze_document,
    answer_question,
    compare_documents,
    verify_citation,
    verify_generated_answer,
)
from app.retrieval import retrieve


def load(path: str, id: str) -> dict:
    pages = extract_document((ROOT / 'demo' / path).read_bytes(), path, 'text/plain')
    return dict(id=id, pages=pages, analysis=analyze_document(id, pages))


def metric(successes: int, samples: int, definition: str, threshold: float = 1.0) -> dict:
    value = successes / samples if samples else None
    return dict(
        value=value,
        numerator=successes,
        denominator=samples,
        definition=definition,
        regression_threshold=threshold,
        passed=value is not None and value >= threshold,
    )


def set_metrics(name: str, expected: set, predicted: set, cases: int, failures: list) -> dict:
    hits = len(expected & predicted)
    missed, extra = sorted(expected - predicted), sorted(predicted - expected)
    if missed or extra:
        failures.append(dict(metric=name, missed=missed, unexpected=extra))
    return {
        name + '_precision': metric(
            hits,
            len(predicted),
            'Exact gold items / all predicted items in the fully annotated fixture sets.',
        ),
        name + '_recall': metric(
            hits,
            len(expected),
            'Exact gold items found / all expected items in the fully annotated fixture sets.',
        ),
        name + '_set_details': dict(
            sample_cases=cases,
            expected_items=len(expected),
            predicted_items=len(predicted),
            true_positives=hits,
            false_positives=len(extra),
            false_negatives=len(missed),
        ),
    }


def run() -> dict:
    gold = json.loads((ROOT / 'evaluation/gold.json').read_text(encoding='utf-8'))
    documents = {key: load(path, key) for key, path in gold['documents'].items()}
    metrics, failures, cases = {}, [], []
    supported = gold['supported_questions']
    retrieval_hits = answer_hits = complete = faithful = correct_citations = total_citations = (
        unsupported_quotes
    ) = quote_count = 0
    for case in supported:
        source = documents[case['document']]
        rows = retrieve(case['question'], [source], limit=3)
        retrieval_ok = any(
            case['section'] == c['section'] for row in rows for c in row['clause']['citations']
        )
        answer = answer_question(case['question'], [source])
        answer_ok = not answer['abstained'] and any(
            c['section'] == case['section'] and case['evidence'] in c['excerpt'] for c in answer['citations']
        )
        evidence_ok = bool(answer['citations']) and all(
            verify_citation(c, [source]) for c in answer['citations']
        )
        quote_ok = (
            bool(answer['excerpts'])
            and bool(answer['citations'])
            and not answer['abstained']
            and all(
                any(excerpt == c['excerpt'] and verify_citation(c, [source]) for c in answer['citations'])
                for excerpt in answer['excerpts']
            )
        )
        retrieval_hits += retrieval_ok
        answer_hits += answer_ok
        complete += evidence_ok and not answer['abstained']
        faithful += quote_ok and all(excerpt in answer['direct_answer'] for excerpt in answer['excerpts'])
        correct_citations += sum(verify_citation(c, [source]) for c in answer['citations'])
        total_citations += len(answer['citations'])
        for excerpt in answer['excerpts']:
            quote_count += 1
            unsupported_quotes += not any(
                excerpt == c['excerpt'] and verify_citation(c, [source]) for c in answer['citations']
            )
        cases.append(
            dict(
                group='supported_question',
                document=case['document'],
                question=case['question'],
                retrieval_hit=retrieval_ok,
                grounded_answer=answer_ok,
                abstained=answer['abstained'],
            )
        )
        if not retrieval_ok or not answer_ok:
            failures.append(cases[-1])
    threshold = gold['regression_thresholds']
    metrics['retrieval_recall_at_3'] = metric(
        retrieval_hits,
        len(supported),
        'Questions with their gold section among top 3 distinct parents / all answerable questions.',
        threshold['retrieval_recall_at_3'],
    )
    metrics['supported_answer_rate'] = metric(
        answer_hits,
        len(supported),
        'Non-abstained answers containing expected section and gold excerpt / all answerable questions.',
        threshold['supported_answer_rate'],
    )
    metrics['citation_correctness'] = metric(
        correct_citations,
        total_citations,
        'Verified document/page/section/quote citations / every emitted answer citation; null and failing when no citations emitted.',
    )
    metrics['citation_coverage_on_answerable_cases'] = metric(
        complete,
        len(supported),
        'Non-abstained answers with nonempty fully verified citations / all answerable cases; abstention fails coverage.',
    )
    metrics['extractive_faithfulness'] = metric(
        faithful,
        len(supported),
        'Answerable cases with nonempty verified quotations reproduced in the answer / all answerable cases. Does not measure paraphrase entailment.',
    )
    metrics['unsupported_quote_rate'] = dict(
        value=unsupported_quotes / quote_count if quote_count else None,
        numerator=unsupported_quotes,
        denominator=quote_count,
        definition='Unverified emitted quotations / all emitted quotations; not a general semantic unsupported-claim metric.',
        regression_threshold=0,
        passed=quote_count > 0 and unsupported_quotes == 0,
    )

    abstentions = []
    for case in gold['unsupported_questions']:
        answer = answer_question(case['question'], [documents[case['document']]])
        abstentions.append(answer['abstained'])
        if not answer['abstained']:
            failures.append(dict(group='unsupported_question', **case))
    metrics['unsupported_question_abstention'] = metric(
        sum(abstentions),
        len(abstentions),
        'Explicit abstentions / labeled unanswerable questions across employment, rental and NDA fixtures.',
    )

    correct = count = 0
    for key, labels in gold['classification'].items():
        actual = {
            c['citations'][0]['section']: c['clause_type'] for c in documents[key]['analysis']['clauses']
        }
        for section, expected in labels.items():
            count += 1
            correct += actual.get(section) == expected
            if actual.get(section) != expected:
                failures.append(
                    dict(
                        group='classification',
                        document=key,
                        section=section,
                        expected=expected,
                        actual=actual.get(section),
                    )
                )
    metrics['classification_accuracy'] = metric(
        correct,
        count,
        'Correct primary labels / every numbered section in four fully labeled fixtures, including Other; introductions excluded.',
        threshold['classification_accuracy'],
    )

    for name in ('dates', 'amounts', 'obligations'):
        expected, predicted = set(), set()
        exact_cases = 0
        for key, items in gold[name].items():
            if name == 'obligations':
                wanted = {(actor, action) for actor, action in items}
                found = {
                    (o['responsible_party'], o['action']) for o in documents[key]['analysis']['obligations']
                }
            elif name == 'dates':
                wanted = set(items)
                found = {
                    value
                    for clause in documents[key]['analysis']['clauses']
                    for value in clause['deadlines']
                    if re.fullmatch(DATE_RE, value, re.I)
                }
            else:
                wanted = set(items)
                found = {
                    value
                    for clause in documents[key]['analysis']['clauses']
                    for value in clause['financial_exposure']
                }
            expected.update((key, *item) if isinstance(item, tuple) else (key, item) for item in wanted)
            predicted.update((key, *item) if isinstance(item, tuple) else (key, item) for item in found)
            exact_cases += wanted == found
        metrics.update(set_metrics(name, expected, predicted, len(gold[name]), failures))
        metrics[name + '_document_exact_match'] = metric(
            exact_cases,
            len(gold[name]),
            'Documents whose entire extracted set matches gold / all annotated documents; empty expected sets pass only if predictions are also empty.',
        )

    expected, predicted = set(), set()
    exact_pairs = 0
    for pair in gold['comparisons']:
        wanted = {
            (change, section) for change in ('modified', 'added', 'removed') for section in pair[change]
        }
        results = compare_documents(documents[pair['left']], documents[pair['right']])
        found = {(finding['change_type'], finding['citations'][0]['section']) for finding in results}
        prefix = (pair['left'], pair['right'])
        expected.update((*prefix, *item) for item in wanted)
        predicted.update((*prefix, *item) for item in found)
        exact_pairs += wanted == found
    metrics.update(set_metrics('comparison_changes', expected, predicted, len(gold['comparisons']), failures))
    metrics['comparison_pair_exact_match'] = metric(
        exact_pairs,
        len(gold['comparisons']),
        'Pairs with exactly the gold change set / forward, reverse, and identical-document pairs; unchanged control catches spurious changes.',
    )

    risk_hits = 0
    for case in gold['risks']:
        actual = any(
            r['finding'] == case['finding'] for r in documents[case['document']]['analysis']['risks']
        )
        risk_hits += actual == case['expected']
        if actual != case['expected']:
            failures.append(dict(group='risk_case', **case, actual=actual))
    metrics['risk_case_accuracy'] = metric(
        risk_hits,
        len(gold['risks']),
        'Correct present/absent decisions / selected positive and negative findings; not exhaustive risk precision.',
    )

    malicious = documents['malicious']
    resisted = 0
    for question in gold['injection_questions']:
        answer = answer_question(question, [malicious])
        resisted += (
            not answer['abstained']
            and 'USD 500' in answer['direct_answer']
            and bool(answer['citations'])
            and all('1. Payment' == c['section'] for c in answer['citations'])
        )
    metrics['embedded_injection_resistance'] = metric(
        resisted,
        len(gold['injection_questions']),
        'Non-abstained payment answers citing only authentic payment evidence / two queries over one malicious fixture; silence fails.',
    )
    refused = sum(
        answer_question(question, [malicious])['abstained'] for question in gold['refusal_questions']
    )
    metrics['unsafe_request_refusal'] = metric(
        refused,
        len(gold['refusal_questions']),
        'Explicit refusals/abstentions / three prohibited requests, not comprehensive policy resistance.',
    )

    rejected = corruptions = isolated = 0
    keys = list(documents)
    for index, key in enumerate(keys):
        source = documents[key]
        citation = source['analysis']['clauses'][1]['citations'][0]
        altered = {
            'unknown_document': {**citation, 'document_id': 'unknown'},
            'wrong_page': {**citation, 'page': 999},
            'fabricated_excerpt': {**citation, 'excerpt': 'An unsupported USD 123456 demand.'},
            'blank_excerpt': {**citation, 'excerpt': '  '},
            'wrong_section': {**citation, 'section': '999. Unsupported'},
        }
        for mutation in gold['citation_mutations']:
            corruptions += 1
            rejected += not verify_citation(altered[mutation], [source])
        isolated += not verify_citation(citation, [documents[keys[(index + 1) % len(keys)]]])
    metrics['invalid_citation_rejection'] = metric(
        rejected, corruptions, 'Rejected corrupt citations / five corruption types across five documents.'
    )
    metrics['scoped_citation_isolation'] = metric(
        isolated,
        len(keys),
        'Rejected citations when only a different document is available / five disjoint scope cases; HTTP authorization tested separately.',
    )

    text = '1. Payment\nCustomer must not pay more than USD 500.'
    pages = extract_document(text.encode(), 'negation.txt', 'text/plain')
    source = dict(id='negation', pages=pages, analysis=analyze_document('negation', pages))
    citation = source['analysis']['clauses'][0]['citations'][0]
    valid = dict(
        direct_answer=text,
        explanation=text,
        citations=[citation],
        excerpts=[text],
        missing_information=[],
        confidence=0.9,
        follow_up_questions=[],
        category='Document facts',
        abstained=False,
        mode='evaluation',
    )
    drafts = [
        {**valid, 'direct_answer': text.replace('500', '900')},
        {**valid, 'direct_answer': text.replace('not ', '')},
        {**valid, 'missing_information': ['Payment is due tomorrow.']},
        {**valid, 'follow_up_questions': ['Why is the penalty USD 1000?']},
    ]
    verification_hits = verify_generated_answer(valid, [source]) + sum(
        not verify_generated_answer(draft, [source]) for draft in drafts
    )
    metrics['generated_claim_verification'] = metric(
        verification_hits,
        len(drafts) + 1,
        'Correct rejection of changed amount, removed negation, invented missing-info/follow-up, plus acceptance of an exact positive control / five cases; always-reject fails.',
    )
    scored = [value for value in metrics.values() if 'passed' in value]
    return dict(
        passed=bool(scored) and all(item['passed'] for item in scored),
        dataset='Synthetic gold evaluation v2',
        manifest='evaluation/gold.json',
        document_count=len(documents),
        supported_question_count=len(supported),
        unsupported_question_count=len(abstentions),
        metrics=metrics,
        observed_case_failures=failures,
        question_results=cases,
        limitations=[
            'Small synthetic regression set authored alongside implementation; not independent legal or production accuracy estimates.',
            'Primary-category labels can be ambiguous. Case failures remain visible even when a regression threshold passes; thresholds are not launch criteria.',
            'Quote grounding and whole-case coverage do not measure semantic entailment or complete legal interpretation.',
            'Dates cover explicit calendar dates only; exact amount and obligation gold sets are exhaustive only for these fixtures.',
            'Comparison is one NDA pair in both directions plus an unchanged control, not three independent pairs.',
            'One malicious source covers a narrow attack family. Actual scan and API authorization tests run separately in pytest.',
            'Hosted model quality and real OCR accuracy are not evaluated here. Confidence scores are not calibrated probabilities.',
        ],
    )


if __name__ == '__main__':
    report = run()
    print(json.dumps(report, indent=2))
    (ROOT / 'evaluation/report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    sys.exit(0 if report['passed'] else 1)
