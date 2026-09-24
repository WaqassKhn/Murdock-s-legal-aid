import json

import httpx
import pytest

from app.providers import OpenAICompatibleProvider


@pytest.mark.parametrize('selected', [[0], [99], [-1], [True], [0, 0]])
def test_model_selects_evidence_without_rewriting_citations(monkeypatch, selected):
    citation = dict(
        document_id='synthetic',
        page=2,
        section='Payment',
        excerpt='Customer must pay USD 500, unless the work is rejected.',
        confidence=0.83,
        bbox=None,
    )

    def post(url, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request('POST', url),
            json={
                'choices': [
                    {'message': {'content': json.dumps({'evidence_ids': selected, 'abstained': False})}}
                ]
            },
        )

    monkeypatch.setattr(httpx, 'post', post)
    provider = OpenAICompatibleProvider('https://example.test', 'synthetic', 'test')
    if selected != [0] or isinstance(selected[0], bool):
        with pytest.raises(RuntimeError):
            provider.answer('What must I pay?', [citation])
    else:
        result = provider.answer('What must I pay?', [citation])
        assert result['citations'] == [citation]
        assert result['direct_answer'] == citation['excerpt']
        assert result['confidence'] == citation['confidence']
