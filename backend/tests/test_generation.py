import pytest

from app.config import Settings
from app.generation import Claim, GenerativeProvider, Judgment, Review, resolve
from app.providers import configured_provider
from test_api import client, register, upload, workspace


def test_generated_demo_workflow_and_reports(client, monkeypatch):
    from app.generation import AnalysisDraft, AnswerDraft, Claim, ClauseDraft, Review
    from app.database import Workspace

    provider = GenerativeProvider('https://example.test', 'synthetic', 'test')

    def structured(task, data, schema):
        if schema is Review:
            return Review(
                judgments=[Judgment(claim_id=c['claim_id'], supported=True) for c in data['claims']]
            )
        if schema is AnalysisDraft:
            rows = data['clauses']

            def claim(row, text):
                return Claim(text=text, evidence_ids=[row['evidence_id']])

            return AnalysisDraft(
                summary=claim(rows[0], 'This document describes an employment relationship.'),
                meaning=claim(rows[0], 'Review the responsibilities described in the agreement.'),
                clauses=[
                    ClauseDraft(
                        clause_id=r['clause_id'],
                        explanation=claim(r, 'Plain-language interpretation of this clause.'),
                        review_note=claim(r, 'Review how this clause applies to your circumstances.'),
                        lawyer_question=claim(r, 'What should I clarify about this clause?'),
                    )
                    for r in rows
                ],
            )
        assert schema is AnswerDraft
        return AnswerDraft(
            abstained=False,
            answer=Claim(text='The employer has a recurring payment responsibility.', evidence_ids=[0]),
            explanation=Claim(text='The payment clause describes what the employer owes.', evidence_ids=[0]),
            questions=[],
        )

    monkeypatch.setattr(provider, 'structured', structured)
    monkeypatch.setattr('app.jobs.configured_provider', lambda _: provider)
    client.app.state.answer_provider = provider
    register(client)
    w = workspace(client)
    with client.app.state.sessions() as db:
        db.get(Workspace, w).is_demo = True
        db.commit()
    document = upload(client, w)
    assert document['analysis']['mode'].startswith('AI-generated analysis')
    assert document['analysis']['summary_citations']
    answer = client.post(f'/api/workspaces/{w}/ask', json={'question': 'What must employer pay?'}).json()
    assert answer['category'] == 'System interpretation'
    assert answer['answer_type'] == 'interpreted'
    assert answer['mode'] == 'AI-generated answer · evidence checked'
    assert answer['direct_answer'] not in answer['citations'][0]['excerpt']
    plan = client.get(f'/api/workspaces/{w}/action-plan').json()
    assert any(q['id'].startswith('clause-lawyer-') for q in plan['lawyer_questions'])
    from app.reports import report_sections

    sections = report_sections(
        dict(name='demo', objective='', jurisdiction='unknown'), [document], '', '', []
    )
    assert any(title == 'Questions to prepare for your lawyer' and lines for title, lines in sections)


def test_transport_schema_keeps_local_length_validation():
    from pydantic import ValidationError
    from app.generation import transport_schema

    assert 'maxLength' not in str(transport_schema(Claim))
    with pytest.raises(ValidationError):
        Claim(text='x' * 3001, evidence_ids=[0])
    assert len(Claim(text='Document overview.', evidence_ids=list(range(9))).evidence_ids) == 9


def test_configured_model_uses_generation_not_only_selection():
    settings = Settings(model_base_url='https://example.test', model_api_key='synthetic', model_name='test')
    assert isinstance(configured_provider(settings), GenerativeProvider)


def test_generation_rejects_invented_numbers_and_evidence():
    evidence = [dict(excerpt='Customer must pay USD 500 within 30 days.')]
    with pytest.raises(ValueError):
        resolve(Claim(text='You owe USD 600.', evidence_ids=[0]), evidence)
    with pytest.raises(ValueError):
        resolve(Claim(text='You owe USD 500.', evidence_ids=[1]), evidence)


def test_generation_rejects_failed_semantic_review(monkeypatch):
    provider = GenerativeProvider('https://example.test', 'synthetic', 'test')
    monkeypatch.setattr(
        provider, 'structured', lambda *a: Review(judgments=[Judgment(claim_id=0, supported=False)])
    )
    with pytest.raises(ValueError, match='grounded'):
        provider.check(
            [Claim(text='The customer never has to pay.', evidence_ids=[0])],
            [dict(excerpt='Customer must pay USD 500.')],
        )


def test_partial_analysis_omits_bad_claim_without_discarding_supported_text(monkeypatch):
    provider = GenerativeProvider('https://example.test', 'synthetic', 'test')

    def review(task, data, schema):
        assert [c['claim_id'] for c in data['claims']] == [1]
        return Review(judgments=[Judgment(claim_id=1, supported=True)])

    monkeypatch.setattr(provider, 'structured', review)
    rejected = provider.check(
        [
            Claim(text='The cost is USD 600.', evidence_ids=[0]),
            Claim(text='The cost is USD 500.', evidence_ids=[0]),
        ],
        [dict(excerpt='Customer must pay USD 500.')],
        partial=True,
    )
    assert rejected == {0}


def test_comparison_review_receives_version_direction_and_rejects_reversal(monkeypatch):
    from app.generation import ComparisonDraft, ChangeDraft

    provider = GenerativeProvider('https://example.test', 'synthetic', 'test')

    def structured(task, data, schema):
        if schema is ComparisonDraft:
            return ComparisonDraft(
                changes=[
                    ChangeDraft(
                        finding_id='change',
                        explanation=Claim(
                            text='Document A requires 60 days and Document B requires 30 days.',
                            evidence_ids=[0, 1],
                        ),
                    )
                ]
            )
        context = data['comparison_versions'][0]
        assert context['before'] == 'Notice is 30 days.'
        assert context['after'] == 'Notice is 60 days.'
        return Review(judgments=[Judgment(claim_id=0, supported=False)])

    monkeypatch.setattr(provider, 'structured', structured)
    with pytest.raises(ValueError, match='grounded'):
        provider.compare(
            [
                dict(
                    id='change',
                    before='Notice is 30 days.',
                    after='Notice is 60 days.',
                    citations=[dict(excerpt='Notice is 30 days.'), dict(excerpt='Notice is 60 days.')],
                )
            ]
        )
