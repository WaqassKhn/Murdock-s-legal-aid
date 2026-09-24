from evaluation import run as evaluation


def test_empty_samples_fail_instead_of_vacuous_success():
    result = evaluation.metric(0, 0, 'empty fixture')
    assert result['value'] is None
    assert result['denominator'] == 0 and not result['passed']


def test_exact_set_metrics_count_missed_and_spurious_items():
    failures = []
    result = evaluation.set_metrics(
        'sample', {('doc', 'a'), ('doc', 'b')}, {('doc', 'a'), ('doc', 'invented')}, 1, failures
    )
    assert result['sample_precision']['value'] == 0.5
    assert result['sample_recall']['value'] == 0.5
    assert result['sample_set_details']['false_positives'] == 1
    assert result['sample_set_details']['false_negatives'] == 1
    assert failures[0]['unexpected'] == [('doc', 'invented')]


def test_blanket_abstention_fails_answer_coverage(monkeypatch):
    import app.retrieval

    monkeypatch.setattr(app.retrieval, 'configured_embedding_provider', lambda: None)
    monkeypatch.setattr(
        evaluation,
        'answer_question',
        lambda *args, **kwargs: {
            'abstained': True,
            'citations': [],
            'excerpts': [],
            'direct_answer': 'Insufficient evidence.',
        },
    )
    report = evaluation.run()
    assert not report['passed']
    assert report['metrics']['supported_answer_rate']['denominator'] == 10
    assert report['metrics']['citation_coverage_on_answerable_cases']['value'] == 0
    assert report['metrics']['extractive_faithfulness']['value'] == 0
    assert report['metrics']['citation_correctness']['value'] is None
    assert not report['metrics']['embedded_injection_resistance']['passed']
