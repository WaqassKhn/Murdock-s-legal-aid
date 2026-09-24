from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Attention = Literal['Low attention', 'Review recommended', 'High attention', 'Insufficient information']


class Schema(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Citation(Schema):
    document_id: str
    page: int = Field(ge=1)
    section: str
    excerpt: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    bbox: list[float] | None = None


class EvidenceField(Schema):
    value: str = 'Not found'
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)


class DocumentMetadata(Schema):
    document_type: EvidenceField = Field(default_factory=EvidenceField)
    parties: EvidenceField = Field(default_factory=EvidenceField)
    effective_date: EvidenceField = Field(default_factory=EvidenceField)
    expiration_date: EvidenceField = Field(default_factory=EvidenceField)
    duration: EvidenceField = Field(default_factory=EvidenceField)
    governing_law: EvidenceField = Field(default_factory=EvidenceField)
    renewal: EvidenceField = Field(default_factory=EvidenceField)
    termination: EvidenceField = Field(default_factory=EvidenceField)
    payment: EvidenceField = Field(default_factory=EvidenceField)
    deadlines: EvidenceField = Field(default_factory=EvidenceField)
    obligations: EvidenceField = Field(default_factory=EvidenceField)
    rights: EvidenceField = Field(default_factory=EvidenceField)
    penalties: EvidenceField = Field(default_factory=EvidenceField)
    dispute_resolution: EvidenceField = Field(default_factory=EvidenceField)
    missing_information: EvidenceField = Field(default_factory=EvidenceField)


class Party(Schema):
    name: str
    role: str
    citations: list[Citation]


class DefinedTerm(Schema):
    term: str
    definition: str
    citations: list[Citation]


class ClauseAnalysis(Schema):
    id: str
    clause_type: str
    original: str
    explanation: str
    affected_parties: list[str] = Field(default_factory=list)
    rights: list[str] = Field(default_factory=list)
    obligations: list[str] = Field(default_factory=list)
    deadlines: list[str] = Field(default_factory=list)
    financial_exposure: list[str] = Field(default_factory=list)
    defined_terms: list[DefinedTerm] = Field(default_factory=list)
    attention: Attention = 'Low attention'
    ambiguities: list[str] = Field(default_factory=list)
    risk_reason: str = ''
    lawyer_question: str = ''
    citations: list[Citation]
    confidence: float = Field(ge=0, le=1)


class Obligation(Schema):
    id: str
    document_id: str
    responsible_party: str
    action: str
    trigger: str
    time_window: str
    recurrence: str
    consequence: str
    status: Literal['open', 'complete'] = 'open'
    citations: list[Citation]
    confidence: float = Field(ge=0, le=1)


class Deadline(Schema):
    expression: str
    trigger: str
    calendar_date: str | None = None
    citations: list[Citation]


class MonetaryTerm(Schema):
    expression: str
    purpose: str
    citations: list[Citation]


class RiskFinding(Schema):
    id: str
    finding: str
    why_it_matters: str
    severity: Attention
    affected_party: str
    confidence: float = Field(ge=0, le=1)
    suggested_clarification: str
    lawyer_question: str
    citations: list[Citation]


class ComparisonFinding(Schema):
    id: str
    clause_type: str
    change_type: Literal['added', 'removed', 'modified']
    before: str
    after: str
    explanation: str
    attention_before: Attention
    attention_after: Attention
    citations: list[Citation]
    warning: str = ''


class ChecklistFinding(Schema):
    clause_type: str
    status: Literal['located', 'not_located']
    citations: list[Citation]
    explanation: str


class GroundedAnswer(Schema):
    direct_answer: str
    explanation: str
    citations: list[Citation]
    excerpts: list[str]
    missing_information: list[str]
    confidence: float = Field(ge=0, le=1)
    follow_up_questions: list[str]
    category: Literal[
        'Document facts', 'System interpretation', 'General legal information', 'Suggested next steps'
    ]
    abstained: bool
    mode: str
    answer_type: Literal['explicit', 'interpreted', 'not_found'] = 'not_found'
    confidence_label: Literal['high', 'medium', 'low'] = 'low'
    verification_step: str = ''
    relevant_clauses: list[Citation] = Field(default_factory=list)


class LawyerQuestion(Schema):
    question: str
    reason: str
    citations: list[Citation]


class LawyerHandoffReport(Schema):
    objective: str
    overview: list[DocumentMetadata]
    important_facts: list[EvidenceField]
    high_attention_clauses: list[ClauseAnalysis]
    unresolved_ambiguities: list[RiskFinding]
    deadlines: list[Deadline]
    conflicting_terms: list[RiskFinding]
    questions: list[LawyerQuestion]
    citations: list[Citation]
    user_notes: str
    disclaimer: str


class DocumentAnalysis(Schema):
    metadata: DocumentMetadata
    summary: str
    meaning: str
    clauses: list[ClauseAnalysis]
    obligations: list[Obligation]
    risks: list[RiskFinding]
    mode: str
