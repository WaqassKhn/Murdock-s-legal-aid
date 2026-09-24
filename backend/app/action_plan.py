"""Evidence-linked preparation with user edits stored separately from extracted facts."""

import html
import re
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from .api import owned_workspace, serialize_mutation, session, user
from .database import Document, Obligation

router = APIRouter(prefix='/api', dependencies=[Depends(serialize_mutation)])
DISCLAIMER = (
    'LegalLens provides document-based legal information, not legal advice. Laws and outcomes depend on jurisdiction and circumstances. '
    'Consult a qualified legal professional before making important decisions. AI-generated results may be incomplete or incorrect.'
)
UNSPECIFIED = {'', 'not found', 'not specified', 'none', 'unknown', 'not stated'}


class ActionEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    user_action: str | None = Field(default=None, max_length=2000)
    user_notes: str | None = Field(default=None, max_length=4000)
    status: Literal['open', 'complete'] | None = None

    @model_validator(mode='after')
    def explicit_non_null_edit(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError(
                'Provide at least one non-null edit. Use an empty string to clear a personal field.'
            )
        return self


def obligation_json(item: Obligation, names: dict[str, str] | None = None) -> dict:
    return {
        **item.payload,
        'id': item.id,
        'document_id': item.document_id,
        'status': item.status,
        'user_action': item.user_action,
        'user_notes': item.user_notes,
        'document_name': (names or {}).get(item.document_id, ''),
    }


def deadline_kind(expression: str) -> tuple[str, str | None, str]:
    """Only an unambiguous ISO date occupying the entire expression becomes a calendar date."""
    expression = expression.strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', expression):
        try:
            return (
                'dated',
                date.fromisoformat(expression).isoformat(),
                'Explicit date stated in the document; verify the cited context.',
            )
        except ValueError:
            return 'unclear', None, 'This date expression is invalid; clarify the intended date.'
    if re.search(
        r'\b(after|before|within|days?|weeks?|months?|years?|notice|termination|renewal|annually|monthly|expiry|expiration)\b',
        expression,
        re.I,
    ):
        return (
            'relative',
            None,
            'Relative or recurring source wording. No calendar date is calculated without a confirmed trigger.',
        )
    return (
        'unclear',
        None,
        'The source wording is preserved. Confirm its meaning and any applicable calendar date.',
    )


def build_action_plan(db, workspace) -> dict:
    documents = list(
        db.scalars(
            select(Document).where(Document.workspace_id == workspace.id).order_by(Document.created_at)
        )
    )
    names = {doc.id: doc.name for doc in documents}
    items = list(
        db.scalars(
            select(Obligation)
            .where(Obligation.workspace_id == workspace.id)
            .order_by(Obligation.created_at, Obligation.id)
        )
    )
    responsibilities = [obligation_json(item, names) for item in items]
    timeline, questions, lawyer_questions, negotiation_prompts, risks, evidence = [], [], [], [], [], []
    seen_events, seen_evidence = set(), set()

    def add_evidence(citations):
        for citation in citations:
            # Artifacts must remain inside this workspace even if an old stored payload is malformed.
            if citation.get('document_id') not in names:
                continue
            key = (
                citation.get('document_id'),
                citation.get('page'),
                citation.get('section'),
                citation.get('excerpt'),
            )
            if key not in seen_evidence:
                seen_evidence.add(key)
                evidence.append(citation)

    def add_event(identifier, document_id, title, expression, trigger, citations, status='open'):
        if not isinstance(expression, str) or expression.strip().lower() in UNSPECIFIED:
            return
        key = (document_id, expression, tuple((c.get('page'), c.get('section')) for c in citations))
        if key in seen_events:
            return
        seen_events.add(key)
        kind, calendar_date, explanation = deadline_kind(expression)
        timeline.append(
            {
                'id': identifier,
                'document_id': document_id,
                'document_name': names[document_id],
                'title': title,
                'expression': expression,
                'trigger': trigger,
                'calendar_date': calendar_date,
                'kind': kind,
                'explanation': explanation,
                'status': status,
                'citations': citations,
            }
        )
        add_evidence(citations)

    for item in responsibilities:
        citations = [c for c in item.get('citations', []) if c.get('document_id') == item['document_id']]
        item['citations'] = citations
        add_evidence(citations)
        add_event(
            item['id'],
            item['document_id'],
            item['action'],
            item.get('time_window', ''),
            item.get('trigger', ''),
            citations,
            item['status'],
        )
        if item.get('responsible_party', '').strip().lower() in UNSPECIFIED:
            questions.append(
                {
                    'id': f'party-{item["id"]}',
                    'question': 'Who is responsible for this obligation?',
                    'reason': item['action'],
                    'document_id': item['document_id'],
                    'citations': citations,
                }
            )

    for doc in documents:
        analysis = doc.analysis or {}
        for key in ('effective_date', 'expiration_date'):
            field = analysis.get('metadata', {}).get(key, {})
            citations = [c for c in field.get('citations', []) if c.get('document_id') == doc.id]
            if citations:
                add_event(
                    f'{doc.id}-{key}',
                    doc.id,
                    key.replace('_', ' ').title(),
                    field.get('value', ''),
                    'As stated in source',
                    citations,
                )
        for clause in analysis.get('clauses', []):
            citations = [c for c in clause.get('citations', []) if c.get('document_id') == doc.id]
            for index, expression in enumerate(clause.get('deadlines', [])):
                add_event(
                    f'{clause["id"]}-{index}',
                    doc.id,
                    clause.get('clause_type', 'Clause').replace('_', ' ').title(),
                    expression,
                    'Confirm the trigger in the cited clause',
                    citations,
                )
            for index, ambiguity in enumerate(clause.get('ambiguities', [])):
                questions.append(
                    {
                        'id': f'ambiguity-{clause["id"]}-{index}',
                        'question': f'Can you clarify: {ambiguity}',
                        'reason': 'An ambiguity identified in the document analysis; independently review the source.',
                        'document_id': doc.id,
                        'citations': citations,
                    }
                )
        for risk in analysis.get('risks', []):
            citations = [c for c in risk.get('citations', []) if c.get('document_id') == doc.id]
            finding = {**risk, 'document_id': doc.id, 'document_name': doc.name, 'citations': citations}
            risks.append(finding)
            clarification = risk.get('suggested_clarification', '')
            if clarification:
                questions.append(
                    {
                        'id': f'clarify-{risk["id"]}',
                        'question': clarification,
                        'reason': risk.get('finding', ''),
                        'document_id': doc.id,
                        'citations': citations,
                    }
                )
                negotiation_prompts.append(
                    {
                        'id': f'discuss-{risk["id"]}',
                        'question': f'Would the parties be willing to clarify this point in writing? {clarification}',
                        'reason': 'A discussion prompt, not a recommendation to accept, reject, or change a legal term.',
                        'document_id': doc.id,
                        'citations': citations,
                    }
                )
            if risk.get('lawyer_question'):
                lawyer_questions.append(
                    {
                        'id': f'lawyer-{risk["id"]}',
                        'question': risk['lawyer_question'],
                        'reason': risk.get('why_it_matters', ''),
                        'document_id': doc.id,
                        'citations': citations,
                    }
                )
            add_evidence(citations)
    if responsibilities and not lawyer_questions:
        first = responsibilities[0]
        lawyer_questions.append(
            {
                'id': f'lawyer-{first["id"]}',
                'question': 'What should I clarify about this obligation before relying on my understanding?',
                'reason': first['action'],
                'document_id': first['document_id'],
                'citations': first['citations'],
            }
        )
    timeline.sort(
        key=lambda event: (
            event['calendar_date'] is None,
            event['calendar_date'] or '',
            event['document_name'],
        )
    )
    return {
        'workspace_id': workspace.id,
        'workspace_name': workspace.name,
        'objective': workspace.objective,
        'responsibilities': responsibilities,
        'timeline': timeline,
        'open_questions': questions,
        'lawyer_questions': lawyer_questions,
        'negotiation_prompts': negotiation_prompts,
        'risks': risks,
        'preparation_evidence': evidence,
        'disclaimer': DISCLAIMER,
    }


@router.get('/workspaces/{w}/action-plan')
def get_action_plan(w: str, current=Depends(user), db=Depends(session)):
    workspace = owned_workspace(db, current.id, w)
    return build_action_plan(db, workspace)


@router.patch('/workspaces/{w}/action-plan/obligations/{o}')
def edit_action(w: str, o: str, payload: ActionEdit, current=Depends(user), db=Depends(session)):
    owned_workspace(db, current.id, w)
    item = db.scalar(select(Obligation).where(Obligation.id == o, Obligation.workspace_id == w))
    if not item:
        raise HTTPException(404, 'Obligation not found in this workspace.')
    changes = payload.model_dump(exclude_unset=True)
    if 'status' in changes:
        item.status = changes.pop('status')
    for field, value in changes.items():
        setattr(item, field, value)
    db.commit()
    document = db.get(Document, item.document_id)
    return obligation_json(item, {document.id: document.name})


def markdown_text(value) -> str:
    text = html.escape(str(value), quote=False)
    text = re.sub(r'([\\`*_{}\[\]()#+!|~-])', r'\\\1', text)
    return text.replace('\r', '').replace('\n', '\n> ')


def render_markdown(plan: dict) -> str:
    lines = [
        '# LegalLens Action Center',
        '',
        f'Workspace: {markdown_text(plan["workspace_name"])}',
        '',
        DISCLAIMER,
        '',
        f'User objective: {markdown_text(plan["objective"] or "Not supplied")}',
        '',
        '## Responsibilities and personal checklist',
        '',
    ]
    for item in plan['responsibilities']:
        lines += [
            f'- [{"x" if item["status"] == "complete" else " "}] Document obligation: {markdown_text(item["action"])}',
            f'  Responsible party: {markdown_text(item.get("responsible_party", "Not specified"))}',
            f'  Time window: {markdown_text(item.get("time_window", "Not specified"))}',
            f'  Trigger: {markdown_text(item.get("trigger", "Not specified"))}',
            f'  User-authored action (not document evidence): {markdown_text(item["user_action"] or "Not supplied")}',
            f'  User notes (not document evidence): {markdown_text(item["user_notes"] or "Not supplied")}',
            '',
        ]
        lines += citation_markdown(item['citations'])
    lines += [
        '## Timeline',
        '',
        'Relative expressions are not converted to calendar dates without a confirmed trigger.',
        '',
    ]
    for event in plan['timeline']:
        lines += [
            f'- {markdown_text(event["title"])}: {markdown_text(event["expression"])}',
            f'  {markdown_text(event["explanation"])}',
            '',
        ]
        lines += citation_markdown(event['citations'])
    for key, title in (
        ('open_questions', 'Open questions'),
        ('lawyer_questions', 'Questions for a lawyer'),
        ('negotiation_prompts', 'Discussion prompts for the parties'),
    ):
        lines += [f'## {title}', '', 'Suggested preparation questions, not legal instructions.', '']
        for question in plan[key]:
            lines += [
                f'- {markdown_text(question["question"])}',
                f'  {markdown_text(question["reason"])}',
                '',
            ]
            lines += citation_markdown(question['citations'])
        if not plan[key]:
            lines += [
                'None identified. This is not a finding that the document is complete or risk-free.',
                '',
            ]
    lines += ['## Preparation evidence', ''] + citation_markdown(plan['preparation_evidence'])
    return '\n'.join(lines)


def citation_markdown(citations: list[dict]) -> list[str]:
    lines = []
    for citation in citations:
        lines += [
            f'Source document: {citation["document_id"]}; page {citation["page"]}; section {markdown_text(citation["section"])}',
            f'> {markdown_text(citation["excerpt"])}',
            '',
        ]
    return lines


@router.get('/workspaces/{w}/action-plan/export')
def export_action_plan(w: str, current=Depends(user), db=Depends(session)):
    workspace = owned_workspace(db, current.id, w)
    return Response(
        render_markdown(build_action_plan(db, workspace)),
        media_type='text/markdown',
        headers={'Content-Disposition': 'attachment; filename="legallens-action-plan.md"'},
    )
