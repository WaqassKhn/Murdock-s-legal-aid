"""Clause-parent retrieval with BM25, local concept vectors and reciprocal-rank fusion."""

import hashlib
import logging
import math
import re
from collections import Counter

from .providers import configured_embedding_provider

logger = logging.getLogger(__name__)
STOP = set(
    'a an the this that is are was were will shall must may can i we my me to of and or in on for with it be do does what which who how when if agreement contract document please tell about'.split()
)
CONCEPTS = {
    'termination': 'terminate termination terminating end ending exit cancel cancellation leave early',
    'renewal': 'renew renewal renews extension automatic automatically',
    'payment': 'payment payments pay pays paid fee fees rent invoice salary money late overdue',
    'confidentiality': 'confidential confidentiality secret secrets disclose disclosure private information',
    'intellectual': 'intellectual ownership owner owns copyright produced work product inventions',
    'liability': 'liability liable indemnity indemnify damages loss losses cap unlimited',
    'notice': 'notice notify notification days window period deadline',
    'governing': 'governing jurisdiction law laws court courts',
    'survival': 'survive survives survival after continue continues termination',
}
SYNONYMS = {word: concept for concept, words in CONCEPTS.items() for word in words.split()}


def tokens(text: str) -> list[str]:
    return [x for x in re.findall(r'[a-z0-9]+', text.lower()) if x not in STOP]


def concept_tokens(text: str) -> list[str]:
    return [SYNONYMS.get(t, t) for t in tokens(text)]


def dense_vector(text: str, dimensions: int = 256) -> list[float]:
    """Local deterministic feature projection; explicitly not a learned embedding model."""
    vector = [0.0] * dimensions
    for word in concept_tokens(text):
        digest = hashlib.sha256(word.encode()).digest()
        vector[int.from_bytes(digest[:2], 'little') % dimensions] += 1 if digest[2] % 2 else -1
    norm = math.sqrt(sum(x * x for x in vector)) or 1
    return [x / norm for x in vector]


def similarity(left: str, right: str) -> float:
    return sum(a * b for a, b in zip(dense_vector(left), dense_vector(right)))


def _children(text: str) -> list[str]:
    """Search sentence/paragraph children; always return the enclosing cited clause."""
    parts = [p.strip() for p in re.split(r'\n\s*\n|(?<=[.;])\s+(?=[A-Z])', text) if p.strip()]
    return parts or [text]


INDEX_VERSION = 'clause-child-v2'
ANALYSIS_VERSION = 'extractive-v2'


def embedding_signature(provider) -> str:
    if not provider:
        return 'local-concept-256-v1'
    identity = (
        f'{type(provider).__name__}:{getattr(provider, "base_url", "")}:{getattr(provider, "model", "")}'
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def analysis_signature(provider) -> str:
    return f'{ANALYSIS_VERSION}:{INDEX_VERSION}:{embedding_signature(provider)}'


def build_index(document: dict, provider=None) -> list[dict]:
    """Offsets are relative to the cited parent clause, never fabricated page offsets."""
    rows = []
    for clause in (document.get('analysis') or {}).get('clauses', []):
        offset = 0
        for number, child in enumerate(_children(clause['original'])):
            start = clause['original'].index(child, offset)
            offset = start + len(child)
            source = clause['citations'][0]
            rows.append(
                {
                    'child_id': clause['id'] + ':' + str(number),
                    'clause_id': clause['id'],
                    'document_id': document['id'],
                    'document_name': document.get('name', ''),
                    'page': source['page'],
                    'section': source['section'],
                    'start': start,
                    'end': offset,
                    'child_text': child,
                    'terms': tokens(child),
                    'local_vector': dense_vector(child),
                    'index_version': INDEX_VERSION,
                    'embedding_signature': embedding_signature(provider),
                }
            )
    if provider and rows:
        if len(rows) > 4000 or any(len(row['child_text']) > 16000 for row in rows):
            raise ValueError(
                'Document exceeds hosted embedding budget. Use local retrieval or shorter source documents.'
            )
        vectors = provider.embed([row['child_text'] for row in rows])
        if len(vectors) != len(rows) or len({len(vector) for vector in vectors}) != 1:
            raise ValueError('Embedding provider returned an invalid vector batch.')
        for row, vector in zip(rows, vectors):
            row['hosted_vector'] = vector
    return rows


def retrieve(question, documents, limit=6, filters=None, embedding_provider=None) -> list[dict]:
    filters = filters or {}
    provider = configured_embedding_provider() if embedding_provider is None else embedding_provider
    rows = []
    for document in documents:
        if filters.get('workspace_id') and document.get('workspace_id') != filters['workspace_id']:
            continue
        if filters.get('document_id') and document['id'] != filters['document_id']:
            continue
        if filters.get('version') and document.get('version') != filters['version']:
            continue
        clauses = {clause['id']: clause for clause in (document.get('analysis') or {}).get('clauses', [])}
        indexed = document.get('index')
        # Non-persisted documents are supported for tests and the standalone evaluator.
        if indexed is None:
            indexed = build_index(document, provider)
        for child in indexed:
            clause = clauses.get(child['clause_id'])
            if not clause:
                continue
            if filters.get('clause_type') and clause['clause_type'] != filters['clause_type']:
                continue
            if filters.get('page') and not any(c['page'] == filters['page'] for c in clause['citations']):
                continue
            rows.append({**child, 'clause': clause, 'document_id': document['id']})
    if not rows:
        return []
    query = tokens(question)
    average = sum(len(row['terms']) for row in rows) / len(rows) or 1
    frequency = Counter(word for row in rows for word in set(row['terms']))
    for row in rows:
        counts = Counter(row['terms'])
        row['keyword_score'] = sum(
            math.log(1 + (len(rows) - frequency[t] + 0.5) / (frequency[t] + 0.5))
            * counts[t]
            * 2.5
            / (counts[t] + 1.5 * (0.25 + 0.75 * len(row['terms']) / average))
            for t in query
            if counts[t]
        )
        row['score'] = 0.0
    mode = 'local_concept_bm25_rrf'
    if provider and all(
        row.get('hosted_vector') and row.get('embedding_signature') == embedding_signature(provider)
        for row in rows
    ):
        vectors = provider.embed([question])
        if len(vectors) != 1 or any(len(row['hosted_vector']) != len(vectors[0]) for row in rows):
            raise ValueError('Embedding provider returned an invalid vector batch.')
        dense, candidates = vectors[0], [row['hosted_vector'] for row in rows]
        mode = 'hosted_dense_bm25_rrf'
    else:
        dense = dense_vector(question)
        candidates = [row['local_vector'] for row in rows]
        if provider:
            mode = 'local_concept_bm25_rrf_index_refresh_required'
    for row, vector in zip(rows, candidates):
        row['dense_score'] = sum(a * b for a, b in zip(dense, vector))
    for key in ('keyword_score', 'dense_score'):
        for rank, row in enumerate(sorted(rows, key=lambda x: x[key], reverse=True), 1):
            row['score'] += 1 / (60 + rank)
    # Rerank using query concept coverage while returning the complete clause parent.
    concepts = set(concept_tokens(question))
    for row in rows:
        coverage = len(concepts & set(concept_tokens(row['child_text']))) / max(1, len(concepts))
        row['relevance'] = coverage
        row['score'] += coverage * 0.03
        del row['terms']
        row.pop('local_vector', None)
        row.pop('hosted_vector', None)
    result, seen = [], set()
    for row in sorted(rows, key=lambda x: x['score'], reverse=True):
        key = (row['document_id'], row['clause']['id'])
        if key not in seen:
            row['retrieval_mode'] = mode
            result.append(row)
            seen.add(key)
        if len(result) >= min(limit, 20):
            break
    logger.info(
        'retrieval candidates=%d returned=%d mode=%s ids_scores=%s',
        len(rows),
        len(result),
        mode,
        [(row['document_id'], row['child_id'], round(row['score'], 5)) for row in result],
    )
    return result
