import json
import math
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .schemas import GroundedAnswer


class EvidenceSelection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    evidence_ids: list[StrictInt] = Field(max_length=3)
    abstained: bool


class AnswerProvider(Protocol):
    def answer(self, question: str, citations: list[dict]) -> dict | None: ...


def strict_json_schema(schema: dict) -> dict:
    """Normalize a copy for strict providers without changing Pydantic's local defaults."""

    def normalize(node):
        if isinstance(node, list):
            return [normalize(value) for value in node]
        if not isinstance(node, dict):
            return node
        result = {key: normalize(value) for key, value in node.items() if key != 'default'}
        if result.get('type') == 'object' or 'properties' in result:
            result['additionalProperties'] = False
            result['required'] = list(result.get('properties', {}))
        return result

    return normalize(schema)


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAICompatibleEmbeddings:
    def __init__(self, base_url: str, api_key: str, model: str):
        if not base_url.startswith('https://'):
            raise ValueError('Embedding provider URLs must use HTTPS.')
        self.base_url, self.api_key, self.model = base_url.rstrip('/'), api_key, model

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        try:
            for start in range(0, len(texts), 64):
                batch = texts[start : start + 64]
                response = httpx.post(
                    self.base_url + '/embeddings',
                    headers={'Authorization': 'Bearer ' + self.api_key},
                    json={'model': self.model, 'input': batch, 'encoding_format': 'float'},
                    timeout=30,
                )
                response.raise_for_status()
                rows = sorted(response.json()['data'], key=lambda item: item['index'])
                if [item['index'] for item in rows] != list(range(len(batch))):
                    raise ValueError('Embedding response indexes do not match requested inputs.')
                for row in rows:
                    vector = [float(x) for x in row['embedding']]
                    if not vector or len(vector) > 16384 or not all(math.isfinite(x) for x in vector):
                        raise ValueError(
                            'Embedding vectors must have finite numeric values and bounded dimensions.'
                        )
                    norm = math.sqrt(sum(x * x for x in vector))
                    if norm == 0:
                        raise ValueError('Embedding vectors cannot be zero.')
                    vectors.append([x / norm for x in vector])
            if len({len(v) for v in vectors}) > 1:
                raise ValueError('Embedding dimensions must be consistent.')
            return vectors
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            raise RuntimeError(
                f'Embedding provider failed validation ({type(error).__name__}). Retry or disable hosted embeddings.'
            ) from None


def configured_embedding_provider(settings=None) -> EmbeddingProvider | None:
    from .config import Settings

    settings = settings or Settings()
    model = settings.embedding_model
    if not model:
        return None
    url = settings.embedding_base_url or settings.model_base_url
    key = settings.embedding_api_key or settings.model_api_key
    if not url or not key:
        raise ValueError('Hosted embeddings require a base URL and API key.')
    return OpenAICompatibleEmbeddings(url, key, model)


class OpenAICompatibleProvider:
    """No tools, bounded retries, schema validation, and no content in logs."""

    def __init__(self, base_url: str, api_key: str, model: str):
        if not base_url.startswith('https://'):
            raise ValueError('Model provider URLs must use HTTPS.')
        self.base_url, self.api_key, self.model = base_url.rstrip('/'), api_key, model
        self.request_count = 0

    def answer(self, question: str, citations: list[dict]) -> dict | None:
        prompt = (
            Path(__file__)
            .with_name('prompts')
            .joinpath('evidence_selection_v2.txt')
            .read_text(encoding='utf-8')
        )
        payload = dict(
            model=self.model,
            temperature=0,
            max_tokens=2500,
            response_format={
                'type': 'json_schema',
                'json_schema': {
                    'name': 'evidence_selection',
                    'strict': True,
                    'schema': strict_json_schema(EvidenceSelection.model_json_schema()),
                },
            },
            messages=[
                {'role': 'system', 'content': prompt},
                {
                    'role': 'user',
                    'content': json.dumps(
                        {
                            'question': question,
                            'untrusted_evidence': [
                                {'evidence_id': index, 'citation': citation}
                                for index, citation in enumerate(citations)
                            ],
                        }
                    ),
                },
            ],
        )
        last_error = None
        for _ in range(2):
            try:
                self.request_count += 1
                response = httpx.post(
                    self.base_url + '/chat/completions',
                    headers={'Authorization': 'Bearer ' + self.api_key},
                    json=payload,
                    timeout=45,
                )
                response.raise_for_status()
                data = response.json()['choices'][0]['message']['content']
                selection = EvidenceSelection.model_validate_json(data)
                indexes = selection.evidence_ids
                if len(set(indexes)) != len(indexes) or any(i < 0 or i >= len(citations) for i in indexes):
                    raise ValueError('Model selected an invalid evidence reference.')
                if selection.abstained:
                    return None
                if not indexes:
                    raise ValueError('Source-backed answers require evidence.')
                # The model chooses relevance; only the server copies provenance and complete clauses.
                selected = [citations[i] for i in indexes]
                return GroundedAnswer(
                    direct_answer=selected[0]['excerpt'],
                    explanation=selected[0]['excerpt'],
                    citations=selected,
                    excerpts=[c['excerpt'] for c in selected],
                    confidence=min(c['confidence'] for c in selected),
                    missing_information=[],
                    follow_up_questions=[],
                    category='Document facts',
                    abstained=False,
                    mode='Verified extractive model output',
                ).model_dump()
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
                last_error = type(error).__name__
        raise RuntimeError(
            f'Model provider could not produce validated output ({last_error}). Retry or use extractive mode.'
        )


def configured_provider(settings=None) -> AnswerProvider | None:
    from .config import Settings
    from .generation import GenerativeProvider

    settings = settings or Settings()
    url, key, model = settings.model_base_url, settings.model_api_key, settings.model_name
    return GenerativeProvider(url, key, model) if all((url, key, model)) and not settings.testing else None
