"""Generate interpretations, resolve evidence on the server, and review each claim."""

import copy
import json
import re
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .providers import OpenAICompatibleProvider, strict_json_schema
from .schemas import DocumentAnalysis, GroundedAnswer

MODE = 'AI-generated answer · evidence checked'
VERSION = 'grounded-generation-v1'


class Output(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Claim(Output):
    text: str = Field(min_length=1, max_length=3000)
    evidence_ids: list[StrictInt] = Field(min_length=1, max_length=48)


class AnswerDraft(Output):
    abstained: bool
    answer: Claim | None
    explanation: Claim | None
    questions: list[Claim] = Field(max_length=3)


class ClauseDraft(Output):
    clause_id: str
    explanation: Claim
    review_note: Claim
    lawyer_question: Claim


class AnalysisDraft(Output):
    summary: Claim
    meaning: Claim
    clauses: list[ClauseDraft] = Field(max_length=48)


class ChangeDraft(Output):
    finding_id: str
    explanation: Claim


class ComparisonDraft(Output):
    changes: list[ChangeDraft] = Field(max_length=40)


class Judgment(Output):
    claim_id: StrictInt
    supported: bool


class Review(Output):
    judgments: list[Judgment] = Field(max_length=160)


class VerifiedGenerativeAnswer(dict):
    """Internal result type created only after generation and grounding checks."""


def transport_schema(schema: type[Output]) -> dict:
    # Gemini's compatibility endpoint rejects some nested length bounds. Local Pydantic
    # validation still enforces every bound; the transport schema keeps types and shape.
    def simplify(value):
        if isinstance(value, list):
            return [simplify(v) for v in value]
        if isinstance(value, dict):
            return {
                k: simplify(v)
                for k, v in value.items()
                if k not in {'minLength', 'maxLength', 'minItems', 'maxItems', 'title'}
            }
        return value

    return simplify(strict_json_schema(schema.model_json_schema()))


def resolve(claim: Claim, evidence: list[dict]) -> list[dict]:
    ids = claim.evidence_ids
    if len(set(ids)) != len(ids) or any(i < 0 or i >= len(evidence) for i in ids):
        raise ValueError('Invalid evidence references')
    sources = [evidence[i] for i in ids]
    source_text = ' '.join(c['excerpt'] for c in sources)

    def numbers(text):
        return set(re.findall(r'\b\d[\d,]*(?:\.\d+)?\b', text))

    if not numbers(claim.text) <= numbers(source_text):
        raise ValueError('Generated numeric value is not in cited evidence')
    if re.search(
        r'\b(?:is|are|clearly|definitely)\s+(?:illegal|unenforceable|enforceable|lawful)|'
        r'\b(?:you should|you must|I recommend you)\s+(?:sign|sue|breach|ignore|reject)|'
        r'\bguarantee(?:d|s)?\b|\b(?:as your lawyer|system prompt|api key)\b',
        claim.text,
        re.I,
    ):
        raise ValueError('Generated text exceeded the document-information boundary')
    return sources


class GenerativeProvider(OpenAICompatibleProvider):
    def structured(self, task: str, data: dict, schema: type[Output]) -> Output:
        prompt = Path(__file__).with_name('prompts').joinpath('grounded_generation_v1.txt').read_text('utf-8')
        payload = {
            'model': self.model,
            'temperature': 0,
            'max_tokens': 10000,
            'messages': [
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': json.dumps({'task': task, 'untrusted_data': data})},
            ],
            'response_format': {
                'type': 'json_schema',
                'json_schema': {
                    'name': schema.__name__,
                    'strict': True,
                    'schema': transport_schema(schema),
                },
            },
        }
        for _ in range(2):
            try:
                self.request_count += 1
                response = httpx.post(
                    self.base_url + '/chat/completions',
                    headers={'Authorization': 'Bearer ' + self.api_key},
                    json=payload,
                    timeout=60,
                )
                response.raise_for_status()
                return schema.model_validate_json(response.json()['choices'][0]['message']['content'])
            except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError):
                continue
        raise RuntimeError(
            'AI generation was unavailable or returned invalid structured output. Retry analysis.'
        )

    def check(
        self,
        claims: list[Claim],
        evidence: list[dict],
        question_indexes=(),
        comparison_context=None,
        partial=False,
    ) -> set[int]:
        rows, rejected = [], set()
        for i, c in enumerate(claims):
            try:
                sources = resolve(c, evidence)
            except ValueError:
                if not partial:
                    raise
                rejected.add(i)
                continue
            rows.append(
                dict(
                    claim_id=i,
                    text=c.text,
                    kind='question' if i in question_indexes else 'interpretation',
                    evidence=sources,
                )
            )
        if not rows:
            return rejected
        review = self.structured(
            'Independently check EVERY claim against only its attached evidence. Mark supported false for '
            'unsupported facts, dates, amounts, altered conditions, may/must changes, omitted material exceptions, '
            'unverified absence claims, legal conclusions or document instructions. Questions are supported only '
            'when relevant and their factual premises are supported. Asking about a missing detail does not assert it exists or is absent. Return every claim_id exactly once.',
            {'claims': rows, 'comparison_versions': comparison_context or []},
            Review,
        )
        ids = [j.claim_id for j in review.judgments]
        rejected.update(j.claim_id for j in review.judgments if not j.supported)
        if sorted(ids) != sorted(row['claim_id'] for row in rows) or (
            not partial and rejected - set(question_indexes)
        ):
            raise ValueError('An AI interpretation could not be grounded in its evidence')
        return rejected

    def answer(self, question: str, citations: list[dict]) -> dict | None:
        draft = self.structured(
            'Answer the question in plain English with a direct answer, a useful explanation, and up to three '
            'questions to clarify. Generate a paraphrase, not a copied clause. Preserve conditions and uncertainty. '
            'Set abstained true with null answer/explanation and no questions if evidence is insufficient.',
            {'question': question, 'evidence': list(enumerate(citations))},
            AnswerDraft,
        )
        if draft.abstained:
            return VerifiedGenerativeAnswer(
                GroundedAnswer(
                    direct_answer='I could not find enough information in the uploaded documents to answer this reliably.',
                    explanation='The retrieved clauses do not establish the requested answer.',
                    citations=[],
                    excerpts=[],
                    missing_information=['Supporting information was not found.'],
                    confidence=0,
                    follow_up_questions=[],
                    category='Document facts',
                    abstained=True,
                    mode=MODE,
                ).model_dump()
            )
        if draft.answer is None or draft.explanation is None:
            raise ValueError('Answer and explanation are required')
        claims = [draft.answer, draft.explanation, *draft.questions]
        rejected = self.check(claims, citations, range(2, len(claims)))
        draft.questions = [c for i, c in enumerate(draft.questions, start=2) if i not in rejected]
        claims = [draft.answer, draft.explanation, *draft.questions]
        selected_ids = list(dict.fromkeys(i for c in claims for i in c.evidence_ids))
        selected = [citations[i] for i in selected_ids]
        return VerifiedGenerativeAnswer(
            GroundedAnswer(
                direct_answer=draft.answer.text,
                explanation=draft.explanation.text,
                citations=selected,
                excerpts=[c['excerpt'] for c in selected],
                missing_information=[],
                confidence=min(0.85, *(c['confidence'] for c in selected)),
                follow_up_questions=[c.text for c in draft.questions],
                category='System interpretation',
                abstained=False,
                mode=MODE,
            ).model_dump()
        )

    def analyze(self, analysis: dict) -> dict:
        from .intelligence import INJECTION

        clauses = [
            c for c in analysis['clauses'] if c['confidence'] >= 0.65 and not INJECTION.search(c['original'])
        ]
        if not clauses or len(clauses) > 48 or sum(len(c['original']) for c in clauses) > 40000:
            raise ValueError(
                'AI analysis requires readable evidence within the 48-clause/40,000-character limit'
            )
        evidence = [c['citations'][0] for c in clauses]
        draft = self.structured(
            'Explain this document for an ordinary person. Provide a short summary, what it means for the reader, '
            'and ONE entry for EVERY supplied clause_id: plain-language explanation, neutral review note, '
            'and a specific useful lawyer question. Each clause entry must cite only its own evidence_id. '
            'Do not invent missing protections or make legal-effect judgments.',
            {
                'clauses': [
                    dict(clause_id=c['id'], evidence_id=i, evidence=evidence[i])
                    for i, c in enumerate(clauses)
                ]
            },
            AnalysisDraft,
        )
        if sorted(c.clause_id for c in draft.clauses) != sorted(c['id'] for c in clauses):
            raise ValueError('Generated clause coverage did not match the document')
        by_id = {c['id']: i for i, c in enumerate(clauses)}
        claims = [draft.summary, draft.meaning]
        for item in draft.clauses:
            for claim in (item.explanation, item.review_note, item.lawyer_question):
                if claim.evidence_ids != [by_id[item.clause_id]]:
                    raise ValueError('Clause interpretation cited a different clause')
                claims.append(claim)
        rejected = self.check(claims, evidence, range(4, len(claims), 3), partial=True)
        if len(rejected) == len(claims):
            raise ValueError('No generated interpretation passed evidence checks')
        result = copy.deepcopy(analysis)
        result.update(
            summary=draft.summary.text if 0 not in rejected else analysis['summary'],
            meaning=draft.meaning.text if 1 not in rejected else analysis['meaning'],
            summary_citations=resolve(draft.summary, evidence) if 0 not in rejected else [],
            meaning_citations=resolve(draft.meaning, evidence) if 1 not in rejected else [],
            mode=f'AI-generated analysis ({self.model}) · evidence checked',
        )
        generated = {c.clause_id: (i, c) for i, c in enumerate(draft.clauses)}
        if rejected:
            result['mode'] += ' · mixed with local extraction'
            result['generation_warnings'] = [
                f'{len(rejected)} AI interpretations did not pass evidence checks and were omitted; those fields retain local extraction or no question. Other generated interpretations passed automated checks.'
            ]
        for clause in result['clauses']:
            if entry := generated.get(clause['id']):
                index, item = entry
                for offset, field, claim in (
                    (2, 'explanation', item.explanation),
                    (3, 'risk_reason', item.review_note),
                    (4, 'lawyer_question', item.lawyer_question),
                ):
                    if index * 3 + offset not in rejected:
                        clause[field] = claim.text
                    elif field == 'lawyer_question':
                        clause[field] = ''
        return DocumentAnalysis.model_validate(result).model_dump()

    def compare(self, findings: list[dict]) -> list[dict]:
        if not findings:
            return findings
        if len(findings) > 40:
            raise ValueError('AI comparison supports at most 40 changed clauses')
        evidence, rows, allowed = [], [], {}
        for finding in findings:
            ids = list(range(len(evidence), len(evidence) + len(finding['citations'])))
            evidence.extend(finding['citations'])
            allowed[finding['id']] = set(ids)
            rows.append(
                dict(
                    finding_id=finding['id'],
                    before=finding['before'],
                    after=finding['after'],
                    evidence_ids=ids,
                )
            )
        draft = self.structured(
            'Explain the practical meaning of EVERY change for an ordinary reader. '
            'Call the before version Document A and the after version Document B, never Version 1 or Version 2. '
            'Preserve which version says what. Cite both versions when both exist. Explain changed responsibilities '
            'and limitations, without legal conclusions.',
            {'changes': rows, 'evidence': list(enumerate(evidence))},
            ComparisonDraft,
        )
        if sorted(c.finding_id for c in draft.changes) != sorted(allowed):
            raise ValueError('Comparison coverage mismatch')
        for item in draft.changes:
            if set(item.explanation.evidence_ids) != allowed[item.finding_id]:
                raise ValueError('Comparison must cite the exact versions being compared')
        rejected = self.check(
            [c.explanation for c in draft.changes], evidence, comparison_context=rows, partial=True
        )
        if len(rejected) == len(draft.changes):
            raise ValueError('No generated comparison interpretation could be grounded in its evidence')
        explanations = {
            c.finding_id: c.explanation.text for i, c in enumerate(draft.changes) if i not in rejected
        }
        return [
            {**f, 'explanation': explanations[f['id']]}
            if f['id'] in explanations
            else {
                **f,
                'warning': (
                    f.get('warning', '')
                    + ' AI explanation omitted after evidence checks. Showing deterministic source differences for this change.'
                ).strip(),
            }
            for f in findings
        ]


def generation_signature(settings) -> str:
    return f'{VERSION}:{settings.model_base_url}:{settings.model_name}' if settings.model_name else 'local'
