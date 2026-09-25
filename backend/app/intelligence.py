import hashlib
import re
from difflib import SequenceMatcher

from .retrieval import concept_tokens, retrieve, similarity, tokens
from .schemas import ChecklistFinding, Citation, ComparisonFinding, DocumentAnalysis, GroundedAnswer

MODE = 'Deterministic evidence extraction · local concept retrieval'
ABSTENTION = 'I could not find enough information in the uploaded documents to answer this reliably.'
CLASSIFIERS = [
    ('Non-compete', r'non[- ]?compet|competing business'),
    ('Non-solicitation', r'non[- ]?solicit'),
    ('Intellectual property', r'intellectual property|copyright|ownership|inventions|work product'),
    ('Indemnity', r'indemni'),
    ('Liability', r'liabil|liable|damages'),
    ('Arbitration', r'arbitrat'),
    ('Governing law', r'governing law|governed by|jurisdiction'),
    ('Dispute resolution', r'dispute|mediat'),
    ('Data protection', r'data protection|personal data'),
    ('Privacy', r'privacy'),
    ('Confidentiality', r'confidential|non.?disclosure'),
    ('Force majeure', r'force majeure|beyond.{0,15}control'),
    ('Warranty', r'warrant'),
    ('Assignment', r'assignment|assign this'),
    ('Exclusivity', r'exclusiv'),
    ('Renewal', r'renew|extension'),
    ('Termination', r'terminat|cancel'),
    ('Notice periods', r'notice'),
    ('Penalties', r'penalt|late fee|late payment'),
    ('Payment', r'payment|pay\b|rent\b|deposit|salary|invoice'),
]
DATE_RE = r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b'
WINDOW_RE = r'\b(?:within\s+|at least\s+|no later than\s+)?\d+\s+(?:business\s+|calendar\s+)?(?:days?|weeks?|months?|years?)(?:\s+(?:after|before|from|following|of)\s+[^.;\n]{1,90})?'
AMOUNT_RE = (
    r'(?:[$£€]\s?\d[\d,]*(?:\.\d{1,2})?|\b(?:USD|GBP|EUR|INR)\s+\d[\d,]*(?:\.\d{1,2})?|\b\d+(?:\.\d+)?\s*%)'
)
INJECTION = re.compile(
    r'ignore (?:all |previous |prior )*instructions|system prompt|developer message|reveal.{0,25}(?:secret|password|key)|\b(?:assistant|system)\s*:|<\|(?:im_start|system)',
    re.I,
)


def ident(*values: str) -> str:
    return hashlib.sha256('|'.join(values).encode()).hexdigest()[:24]


def normalized(text: str) -> str:
    return ' '.join(text.split())


def verify_citation(citation: dict, documents: list[dict]) -> bool:
    try:
        checked = Citation.model_validate(citation)
    except ValueError:
        return False
    if not normalized(checked.excerpt):
        return False
    for document in documents:
        if document['id'] == checked.document_id:
            for page in document['pages']:
                if page['number'] == checked.page:
                    if normalized(checked.excerpt) not in normalized(page['text']):
                        return False
                    if checked.bbox is not None and checked.bbox != _source_bbox(page, checked.excerpt):
                        return False
                    analysis = document.get('analysis')
                    if analysis and not any(
                        c['section'] == checked.section
                        and normalized(checked.excerpt) in normalized(c['excerpt'])
                        for clause in analysis.get('clauses', [])
                        for c in clause['citations']
                    ):
                        return False
                    return True
    return False


def classify(text: str) -> str:
    # Favor section heading over incidental terms inside its body.
    heading = text.split('\n')[0][:100]
    for source in (heading, text):
        for kind, pattern in CLASSIFIERS:
            if re.search(pattern, source, re.I):
                return kind
    return 'Other'


def sections(pages: list[dict]) -> list[tuple[dict, str, str]]:
    result = []
    for page in pages:
        text = page['text'].strip()
        if not text:
            continue
        # Each page retains provenance; numbered headings delimit parents. Blank paragraphs provide fallback.
        pieces = re.split(r'\n(?=\s*(?:\d+(?:\.\d+)*[.)]?\s+[A-Z]|(?:SECTION|ARTICLE)\s+\w+))', text)
        if len(pieces) == 1:
            pieces = re.split(r'\n\s*\n', text)
        for index, piece in enumerate(pieces, 1):
            piece = piece.strip()
            if not piece:
                continue
            heading = piece.split('\n')[0]
            match = re.match(r'\s*((?:\d+(?:\.\d+)*[.)]?|(?:SECTION|ARTICLE)\s+\w+)\s+[^\n]{1,100})', heading)
            section = match.group(1) if match else f'Page {page["number"]}, paragraph {index}'
            result.append((page, section, piece))
    return result


def _actor(sentence: str) -> str:
    match = re.search(
        r'(?:^|[.;]\s+)(?:The\s+)?([A-Z][\w &,-]{1,60}?)\s+(?:shall|must|agrees to|is required to|will)\b',
        sentence,
    )
    return match.group(1).strip() if match else 'Not clearly stated'


def _sentences(text: str) -> list[str]:
    body = _clause_body(text)
    return [s.strip() for s in re.split(r'(?<=[.;])\s+(?=[A-Z])|\n', body) if s.strip()]


def _clause_body(text: str) -> str:
    heading, separator, body = text.partition('\n')
    is_heading = re.match(r'^\s*(?:\d+(?:\.\d+)*[.)]?\s+|(?:SECTION|ARTICLE)\s+\w+)', heading)
    if (
        separator
        and is_heading
        and len(heading) <= 120
        and not re.search(r'\b(?:shall|must|may|means)\b', heading, re.I)
    ):
        return body.strip()
    return text.strip()


def _simplify_wording(text: str) -> str:
    """Change only an allowlist of phrases, retaining complete conditions and quoted terms."""
    replacements = {
        'prior to': 'before',
        'subsequent to': 'after',
        'in the event that': 'if',
        'for the purpose of': 'for',
        'shall': 'must',
        'terminate': 'end',
    }
    pattern = re.compile(r'\b(?:' + '|'.join(re.escape(phrase) for phrase in replacements) + r')\b', re.I)

    def replace(match: re.Match) -> str:
        original = match.group(0)
        replacement = replacements[original.lower()]
        if original.isupper():
            return replacement.upper()
        if original[0].isupper():
            return replacement[0].upper() + replacement[1:]
        return replacement

    quoted = r'("[^"\n]*"|“[^”\n]*”|(?<!\w)\x27[^\x27\n]+\x27(?!\w)|‘[^’\n]*’)'
    parts = re.split(quoted, text)
    return ''.join(part if index % 2 else pattern.sub(replace, part) for index, part in enumerate(parts))


def _explanation(original: str) -> str:
    if INJECTION.search(original):
        return 'This section contains text resembling instructions to the system. It remains untrusted document evidence and is not used to generate an explanation.'
    return 'Simplified wording: ' + _simplify_wording(_clause_body(original))


def _defined_terms(document_id: str, page: dict, section: str, original: str) -> list[dict]:
    body = _clause_body(original)
    sentences = [
        sentence.strip()
        for sentence in re.split(r'(?<=[.;])\s+(?=[A-Z"“\x27‘])|\n', body)
        if sentence.strip()
    ]
    pattern = re.compile(
        r'^(?:["“\x27‘](?P<quoted>[^"”\x27’\n]{1,100})["”\x27’]|(?P<plain>[A-Z][A-Za-z-]*(?:\s+[A-Z][A-Za-z-]*){0,7}))\s+means\s+(?P<definition>.+)$'
    )
    result = []
    for sentence in sentences:
        match = pattern.match(sentence)
        if match and not INJECTION.search(sentence):
            term = match.group('quoted') or match.group('plain')
            if term in {'This', 'That', 'It', 'What', 'Which'}:
                continue
            result.append(
                dict(
                    term=term,
                    definition=match.group('definition'),
                    citations=[_citation(document_id, page, section, sentence)],
                )
            )
    return result


def _summary(clauses: list[dict], obligation_count: int) -> str:
    selected = []
    seen = set()
    for clause in clauses:
        kind = clause['clause_type']
        if kind != 'Other' and kind not in seen and not INJECTION.search(clause['original']):
            citation = clause['citations'][0]
            selected.append(f'{kind} (page {citation["page"]}, {citation["section"]})')
            seen.add(kind)
        if len(selected) == 4:
            break
    overview = (
        'Located sections cover ' + '; '.join(selected) + '.'
        if selected
        else 'No main clause category was confidently located; review the source text.'
    )
    return f'{overview} The tracker contains {obligation_count} explicit obligation statements. Open each cited section for its wording, conditions, and exceptions.'


def _source_bbox(page: dict, excerpt: str) -> list[float] | None:
    target = normalized(excerpt)
    blocks = [b for b in page.get('blocks', []) if b.get('bbox') and normalized(b['text'])]
    for index, block in enumerate(blocks):
        if target in normalized(block['text']):
            return block['bbox']
        collected, words = [], ''
        for following in blocks[index:]:
            words = normalized(words + ' ' + following['text'])
            if not target.startswith(words):
                break
            collected.append(following['bbox'])
            if words == target:
                return [
                    min(b[0] for b in collected),
                    min(b[1] for b in collected),
                    max(b[2] for b in collected),
                    max(b[3] for b in collected),
                ]
    return None


def _citation(document_id: str, page: dict, section: str, text: str) -> dict:
    bbox = _source_bbox(page, text)
    return dict(
        document_id=document_id,
        page=page['number'],
        section=section,
        excerpt=text,
        confidence=min(0.96, page.get('quality', 1)),
        bbox=bbox,
    )


def analyze_document(document_id: str, pages: list[dict]) -> dict:
    clauses, obligations, risks = [], [], []
    for occurrence, (page, section, original) in enumerate(sections(pages)):
        citation = _citation(document_id, page, section, original)
        kind = classify(original)
        sentences = _sentences(original)
        required = [
            s
            for s in sentences
            if re.search(r'\b(shall|must|agrees to|is required to|will)\b', s, re.I)
            and not INJECTION.search(s)
        ]
        rights = [
            s
            for s in sentences
            if re.search(r'\b(may|entitled to|has the right)\b', s, re.I) and not INJECTION.search(s)
        ]
        windows = re.findall(WINDOW_RE, original, re.I)
        dates = re.findall(DATE_RE, original, re.I)
        amounts = re.findall(AMOUNT_RE, original)
        attention = 'Insufficient information' if page.get('quality', 1) < 0.75 else 'Low attention'
        ambiguities = []
        if windows:
            ambiguities.append(
                'Relative periods remain as written. A calendar date requires a confirmed trigger date.'
            )
        clause = dict(
            id=ident(document_id, str(page['number']), str(occurrence), section, original),
            clause_type=kind,
            original=original,
            explanation=_explanation(original),
            affected_parties=sorted(set(_actor(s) for s in required)),
            rights=rights,
            obligations=required,
            deadlines=dates + windows,
            financial_exposure=amounts,
            defined_terms=_defined_terms(document_id, page, section, original),
            attention=attention,
            ambiguities=ambiguities,
            citations=[citation],
            confidence=citation['confidence'],
        )
        clauses.append(clause)
        clause['risk_reason'], clause['lawyer_question'] = _clause_guidance(kind, original)
        for sentence_index, sentence in enumerate(required):
            local_windows = re.findall(WINDOW_RE, sentence, re.I)
            local_dates = re.findall(DATE_RE, sentence, re.I)
            trigger_match = re.search(r'\b(?:after|before|following|upon|when)\s+([^.;\n]+)', sentence, re.I)
            obligations.append(
                dict(
                    id=ident(
                        document_id,
                        str(page['number']),
                        str(occurrence),
                        str(sentence_index),
                        section,
                        sentence,
                    ),
                    document_id=document_id,
                    responsible_party=_actor(sentence),
                    action=sentence,
                    trigger=trigger_match.group(0) if trigger_match else 'Not stated; confirm trigger',
                    time_window='; '.join(local_dates + local_windows) or 'Not stated',
                    recurrence=next(
                        iter(
                            re.findall(
                                r'\b(?:monthly|annually|weekly|each month|each year)\b', sentence, re.I
                            )
                        ),
                        'Not stated',
                    ),
                    consequence=sentence
                    if re.search(r'late fee|penalty|failure to|if .{0,30}fail', sentence, re.I)
                    else 'Not established in this obligation; review penalty clauses separately',
                    status='open',
                    citations=[_citation(document_id, page, section, sentence)],
                    confidence=citation['confidence'],
                )
            )
        patterns = [
            (
                r'unlimited|without (?:any )?limit|all losses|any and all',
                'Broad liability wording',
                'High attention',
                'The wording may allocate substantial financial exposure. Its effect depends on the full agreement and applicable law.',
            ),
            (
                r'non[- ]?compete|competing business',
                'Post-employment restriction',
                'Review recommended',
                'The scope, duration, and applicable law merit professional review.',
            ),
            (
                r'sole discretion.{0,80}(?:change|modify)|(?:change|modify).{0,80}sole discretion',
                'Unilateral modification wording',
                'Review recommended',
                'Clarify how changes are communicated and whether agreement is required.',
            ),
            (
                r'auto(?:matic|matically).{0,30}renew|renews automatically',
                'Automatic renewal',
                'Review recommended',
                'Confirm the notice window and record the trigger date before calculating a deadline.',
            ),
            (
                r'survive|survives|survival',
                'Continuing obligations',
                'Review recommended',
                'Confirm which duties continue and for how long.',
            ),
        ]
        for pattern, finding, severity, why in patterns:
            if re.search(pattern, original, re.I | re.S):
                risks.append(_risk(document_id, finding, why, severity, [citation]))
                attention_order = {
                    'Low attention': 0,
                    'Review recommended': 1,
                    'High attention': 2,
                    'Insufficient information': 3,
                }
                clause['attention'] = max((clause['attention'], severity), key=attention_order.get)
        if INJECTION.search(original):
            risks.append(
                _risk(
                    document_id,
                    'Instructions embedded in source text',
                    'This text is treated only as document content and is excluded from answer evidence.',
                    'High attention',
                    [citation],
                )
            )
    metadata = {}
    field_patterns = {
        'document_type': r'\b(?:employment|rental|lease|non.?disclosure|NDA|service|loan|insurance|privacy|terms of service)\b',
        'parties': r'\bbetween\b|\bparties\b',
        'effective_date': r'effective|commence|start date',
        'expiration_date': r'expir|end date|ends on',
        'governing_law': r'governing law|governed by|jurisdiction',
        'renewal': r'renew',
        'termination': r'terminat',
        'payment': r'payment|pay\b|rent\b|deposit|salary',
        'deadlines': WINDOW_RE + '|' + DATE_RE,
        'obligations': r'\bshall\b|\bmust\b',
        'rights': r'\bmay\b|entitled|right to',
        'penalties': r'penalt|late fee|damages',
        'dispute_resolution': r'dispute|arbitrat|mediat',
    }
    for field, pattern in field_patterns.items():
        matches = [
            c
            for c in clauses
            if re.search(pattern, c['original'], re.I) and not INJECTION.search(c['original'])
        ]
        metadata[field] = dict(
            value='\n\n'.join(c['original'] for c in matches[:3]) if matches else 'Not found',
            citations=[c['citations'][0] for c in matches[:3]],
            confidence=min((c['confidence'] for c in matches[:3]), default=0),
        )
    duration_clauses = [
        clause
        for clause in clauses
        if not INJECTION.search(clause['original'])
        and (
            re.search(
                r'\b(?:agreement|contract|employment|tenancy|lease)\s+(?:shall\s+|will\s+)?(?:lasts?|continues?|remains? in (?:effect|force))\s+(?:for\s+)?\d+\s+(?:days?|weeks?|months?|years?)\b',
                clause['original'],
                re.I,
            )
            or re.search(
                r'\b(?:initial )?term\s+(?:of (?:this |the )?(?:agreement|contract)\s+)?(?:is|shall be|will be|of)\s+\d+\s+(?:days?|weeks?|months?|years?)\b',
                clause['original'],
                re.I,
            )
        )
    ]
    metadata['duration'] = dict(
        value='\n\n'.join(clause['original'] for clause in duration_clauses[:3])
        if duration_clauses
        else 'Not found',
        citations=[clause['citations'][0] for clause in duration_clauses[:3]],
        confidence=min((clause['confidence'] for clause in duration_clauses[:3]), default=0),
    )
    missing = [
        name.replace('_', ' ')
        for name in ('governing_law', 'termination', 'effective_date', 'expiration_date')
        if metadata[name]['value'] == 'Not found'
    ]
    metadata['missing_information'] = dict(value='Not found', citations=[], confidence=0)
    if clauses:
        for field in missing:
            risks.append(
                _risk(
                    document_id,
                    f'{field.capitalize()} not located',
                    'This is an extraction coverage check, not proof that the term is absent. Review all pages and referenced materials.',
                    'Insufficient information',
                    [],
                )
            )
    risks.extend(_deterministic_checks(document_id, clauses))
    return DocumentAnalysis.model_validate(
        dict(
            metadata=metadata,
            summary=_summary(clauses, len(obligations)),
            meaning='Use the cited wording to understand the terms, confirm missing information, and prepare questions for a qualified legal professional. Automated extraction may miss context or exceptions.',
            clauses=clauses,
            obligations=obligations,
            risks=risks,
            mode=MODE,
        )
    ).model_dump()


def _clause_guidance(kind: str, original: str) -> tuple[str, str]:
    if INJECTION.search(original):
        return (
            'Instructions embedded in the source are untrusted and excluded from answer evidence.',
            'Can you confirm the authenticity and purpose of this source text?',
        )
    guidance = {
        'Payment': (
            'Payment wording should be checked for the responsible party, amount, trigger, and exceptions.',
            'Which payment amount, trigger, and exceptions apply to me under this wording?',
        ),
        'Termination': (
            'Ending an agreement may involve conditions and continuing duties; review the complete cited provision.',
            'What conditions and continuing duties should I check before relying on this termination wording?',
        ),
        'Renewal': (
            'Renewal wording should be read with any notice requirements and exceptions.',
            'How do the renewal and notice requirements interact, and which trigger date should I confirm?',
        ),
        'Notice periods': (
            'A notice window may depend on delivery method and a trigger date.',
            'How should the notice method, trigger date, and time window be confirmed?',
        ),
        'Confidentiality': (
            'Review the stated confidentiality scope alongside exclusions and duration.',
            'Which information, exclusions, and time limits does this confidentiality wording cover?',
        ),
        'Intellectual property': (
            'Ownership wording should be read with its definitions and any exceptions.',
            'What work and pre-existing materials are covered by this ownership wording?',
        ),
        'Liability': (
            'Review the stated liability allocation with any limits and exceptions.',
            'Which losses, limits, and exceptions does this liability wording cover?',
        ),
        'Indemnity': (
            'The indemnity wording may allocate costs; its scope needs contextual review.',
            'Which events, parties, and limits are covered by this indemnity wording?',
        ),
        'Non-compete': (
            'The stated restriction should be reviewed for scope, duration, and applicable law.',
            'How should I understand the scope and duration of this restriction under the applicable law?',
        ),
        'Governing law': (
            'A named governing law does not by itself resolve every jurisdiction or forum question.',
            'Does this governing-law provision address the forum and issues relevant to my situation?',
        ),
        'Penalties': (
            'Review the stated charge together with the event that triggers it and any exceptions.',
            'Which event triggers this charge, and what exceptions or limits should I check?',
        ),
    }
    if re.search(r'unlimited|without (?:any )?limit|any and all', original, re.I):
        return (
            'The cited wording includes broad or unlimited language; confirm its scope and any limits elsewhere.',
            'How does this broad wording interact with any caps, exclusions, or other limits in the documents?',
        )
    return guidance.get(
        kind,
        (
            'Review this source section together with any definitions, conditions, and cross-references.',
            f'Which definitions, conditions, or related sections should I check when reading this {kind.lower()} provision?',
        ),
    )


def _risk(document_id: str, finding: str, why: str, severity: str, citations: list[dict]) -> dict:
    return dict(
        id=ident(document_id, finding, str(citations)),
        finding=finding,
        why_it_matters=why,
        severity=severity,
        affected_party='Confirm with the relevant parties',
        confidence=min((c['confidence'] for c in citations), default=0.35),
        suggested_clarification='Confirm the intended meaning, applicable exceptions, and any missing supporting documents.',
        lawyer_question=f'How should I understand and address this point: {finding.lower()}?',
        citations=citations,
    )


def _deterministic_checks(document_id: str, clauses: list[dict]) -> list[dict]:
    risks = []
    all_text = '\n'.join(c['original'] for c in clauses)
    section_ids = {
        m.group(1).rstrip('.')
        for c in clauses
        if (m := re.match(r'(\d+(?:\.\d+)*)', c['citations'][0]['section']))
    }
    for clause in clauses:
        for ref in re.findall(r'\b(?:section|clause)\s+(\d+(?:\.\d+)*)', clause['original'], re.I):
            if ref not in section_ids:
                risks.append(
                    _risk(
                        document_id,
                        f'Reference to section {ref} could not be resolved',
                        'The referenced section was not detected; extraction or an omitted document may explain this.',
                        'Review recommended',
                        clause['citations'],
                    )
                )
        for annex in re.findall(r'\b(?:Schedule|Annex(?:ure)?|Appendix)\s+[A-Z0-9]+\b', clause['original']):
            if not re.search(r'(?:^|\n)\s*' + re.escape(annex) + r'\s*(?:\n|[-:])', all_text):
                risks.append(
                    _risk(
                        document_id,
                        f'{annex} was referenced but not located',
                        'A referenced attachment may contain important terms.',
                        'Review recommended',
                        clause['citations'],
                    )
                )
    for index, left in enumerate(clauses):
        for right in clauses[index + 1 :]:
            left_text, right_text = left['original'], right['original']
            common_key = next(
                (
                    key
                    for key in (
                        'effective date',
                        'end date',
                        'expiration date',
                        'monthly rent',
                        'security deposit',
                        'payment amount',
                    )
                    if key in left_text.lower() and key in right_text.lower()
                ),
                None,
            )
            if common_key:
                before = set(re.findall(DATE_RE + '|' + AMOUNT_RE, left_text, re.I))
                after = set(re.findall(DATE_RE + '|' + AMOUNT_RE, right_text, re.I))
                if before and after and before != after:
                    risks.append(
                        _risk(
                            document_id,
                            f'Potential conflicting {common_key}',
                            'Different dates or amounts accompany the same label. Confirm whether the clauses describe the same event or obligation.',
                            'High attention',
                            left['citations'] + right['citations'],
                        )
                    )
    return risks


def _abstain(missing: str, category='Document facts') -> dict:
    return GroundedAnswer(
        direct_answer=ABSTENTION,
        explanation=missing,
        citations=[],
        excerpts=[],
        missing_information=[missing],
        confidence=0,
        follow_up_questions=['Which section addresses this issue?', 'What should I clarify with a lawyer?'],
        category=category,
        abstained=True,
        mode=MODE,
    ).model_dump()


def answer_question(question: str, documents: list[dict], provider=None, embedding_provider=None) -> dict:
    urgent, evidence_query = _urgent_guidance(question)
    # Safety guidance must not wait for a hosted model or embedding service.
    effective_embeddings = False if urgent else embedding_provider
    answer = _document_answer(question, documents, None if urgent else provider, effective_embeddings)
    if urgent and answer['abstained'] and evidence_query:
        rows = retrieve(evidence_query, documents, limit=3, embedding_provider=effective_embeddings)
        citations = [
            c
            for row in rows
            if row['relevance'] >= 0.28
            and row['clause']['confidence'] >= 0.65
            and not INJECTION.search(row['clause']['original'])
            for c in row['clause']['citations']
            if verify_citation(c, documents)
        ]
        if citations:
            answer.update(
                citations=citations,
                excerpts=[c['excerpt'] for c in citations],
                direct_answer=answer['direct_answer']
                + '\n\nPotentially relevant document wording (not a determination of your rights):\n\n'
                + '\n\n'.join(c['excerpt'] for c in citations),
            )
    answer['answer_type'] = (
        'not_found'
        if answer['abstained']
        else 'explicit'
        if answer['category'] == 'Document facts'
        else 'interpreted'
    )
    answer['confidence_label'] = (
        'low'
        if answer['abstained'] or answer['confidence'] < 0.65
        else 'high'
        if answer['confidence'] >= 0.9
        else 'medium'
    )
    answer['relevant_clauses'] = answer['citations']
    answer['verification_step'] = urgent or (
        'Open each cited page and check definitions, exceptions, amendments, and trigger dates. Confidence describes evidence quality, not certainty about legal effect.'
        if answer['citations']
        else 'Locate the missing source section or document, then ask a qualified legal professional to confirm its meaning. No supported answer was found.'
    )
    return GroundedAnswer.model_validate(answer).model_dump()


def _urgent_guidance(question: str) -> tuple[str, str]:
    if re.search(
        r'\b(?:immediate danger|domestic (?:abuse|violence)|being (?:abused|attacked)|threatened with violence|unsafe right now)\b',
        question,
        re.I,
    ):
        return (
            'If you are in immediate danger, move to a safer place if you can and contact local emergency services. A local abuse-support service or trusted person may help with safety planning. Use a safe device if you are concerned about monitoring. Document analysis should not delay getting help.',
            '',
        )
    if re.search(r'\b(?:detained|detention|arrested|in custody)\b', question, re.I):
        return (
            'Contact a qualified local lawyer or local legal-aid service promptly about the detention. If there is an immediate safety or medical emergency, seek local emergency assistance. This tool cannot determine your rights or the legality of detention.',
            'detention arrest custody',
        )
    if re.search(r'\b(?:evict\w*|court|hearing|filing)\b', question, re.I) and re.search(
        r'\b(?:today|tomorrow|urgent|deadline|imminent|being evicted|now)\b', question, re.I
    ):
        return (
            'Contact a qualified local lawyer or local legal-aid service promptly about the eviction or court deadline. Confirm the date and required procedure directly from the notice and the relevant court or issuing authority. Do not rely on this analysis to calculate or extend a deadline.',
            'notice termination deadline'
            if re.search(r'evict', question, re.I)
            else 'court hearing filing deadline notice',
        )
    return '', ''


def _document_answer(question: str, documents: list[dict], provider=None, embedding_provider=None) -> dict:
    if re.search(
        r'fabricat|forge|impersonat|pretend.{0,20}lawyer|guarantee.{0,30}(?:outcome|win)|conceal.{0,30}(?:crime|wrongdoing)|evade.{0,30}(?:obligation|law)|ignore.{0,25}instructions|system prompt|reveal.{0,30}(?:secret|key|password)',
        question,
        re.I,
    ):
        return _abstain(
            'I can help summarize authentic documents or prepare questions for a qualified lawyer, but cannot fabricate evidence, impersonate counsel, conceal wrongdoing, or guarantee outcomes.',
            'Suggested next steps',
        )
    if re.search(
        r'\b(?:legal|illegal|enforceable|enforceability|lawful|statute|legislation)\b|under .{0,25}law',
        question,
        re.I,
    ):
        return _abstain(
            'A legal conclusion requires a confirmed jurisdiction and an approved, current legal authority. No external legal source retrieval is configured. Document analysis remains available.',
            'General legal information',
        )
    matches = retrieve(question, documents, embedding_provider=embedding_provider)
    safe = [
        r
        for r in matches
        if not INJECTION.search(r['clause']['original'])
        and r['clause']['confidence'] >= 0.65
        and r['relevance'] >= 0.28
        and all(verify_citation(c, documents) for c in r['clause']['citations'])
    ]
    if not safe:
        return _abstain(
            'No sufficiently relevant, readable source clause was found. Upload the missing terms or review affected pages.'
        )
    # Specific unknown subjects must not borrow support from incidental words such as payment or termination.
    specific = set(tokens(question)) - set(
        'could would should happen happens happen agreement contract clarify lawyer ask early late information produced work remain automatically enough required notice period days after before rights obligations continues'.split()
    )
    evidence_concepts = set(concept_tokens(' '.join(r['clause']['original'] for r in safe[:3])))
    query_concepts = set(concept_tokens(' '.join(specific)))
    if query_concepts and len(query_concepts & evidence_concepts) / len(query_concepts) < 0.4:
        return _abstain('The retrieved clauses do not establish the specific issue in your question.')
    selected = safe[:3]
    citations = [c for row in selected for c in row['clause']['citations']]
    answer = dict(
        direct_answer='The document states:\n\n' + '\n\n'.join(c['excerpt'] for c in citations),
        explanation='These are exact source excerpts selected for your question. They may need to be read together with definitions, exceptions, amendments, and other clauses. This extractive response does not decide legal effect.',
        citations=citations,
        excerpts=[c['excerpt'] for c in citations],
        missing_information=[
            'Intent, exceptions, and applicable legal effect are not established by retrieval alone.'
        ],
        confidence=min(c['confidence'] for c in citations),
        follow_up_questions=[
            'Do other sections qualify this wording?',
            'Which trigger dates or missing attachments should I confirm with a lawyer?',
        ],
        category='Document facts',
        abstained=False,
        mode=MODE,
    )
    if provider is not None:
        draft = provider.answer(question, citations)
        from .generation import VerifiedGenerativeAnswer

        if isinstance(draft, VerifiedGenerativeAnswer):
            selected = {
                (c['document_id'], c['page'], c['section'], normalized(c['excerpt'])) for c in citations
            }
            validated = GroundedAnswer.model_validate(draft).model_dump()
            if all(
                verify_citation(c, documents)
                and (c['document_id'], c['page'], c['section'], normalized(c['excerpt'])) in selected
                for c in validated['citations']
            ):
                return validated
            raise ValueError('Generated answer cited evidence outside retrieval scope')
        # Fail closed: generated prose is accepted only if it is an exact source span.
        selected_evidence = {
            (c['document_id'], c['page'], c['section'], normalized(c['excerpt'])) for c in citations
        }
        if (
            draft
            and verify_generated_answer(draft, documents)
            and all(
                (c['document_id'], c['page'], c['section'], normalized(c['excerpt'])) in selected_evidence
                for c in draft['citations']
            )
        ):
            answer = draft
            answer['mode'] = 'Verified extractive model output'
    return GroundedAnswer.model_validate(answer).model_dump()


def verify_generated_answer(draft: dict, documents: list[dict]) -> bool:
    try:
        answer = GroundedAnswer.model_validate(draft)
    except ValueError:
        return False
    if answer.abstained or not answer.citations:
        return False
    if not all(verify_citation(c.model_dump(), documents) for c in answer.citations):
        return False
    evidence = [normalized(c.excerpt) for c in answer.citations]
    canonical = {
        normalized(clause['original'])
        for document in documents
        for clause in (document.get('analysis') or {}).get('clauses', [])
    }
    if not all(source in canonical for source in evidence):
        return False
    # Exact extractive entailment intentionally sacrifices paraphrase freedom for auditable grounding.
    if (
        answer.category != 'Document facts'
        or not answer.direct_answer.strip()
        or answer.confidence > min(c.confidence for c in answer.citations)
    ):
        return False
    if any(INJECTION.search(source) for source in evidence):
        return False
    # Every user-visible model text is checked, including lists often missed by claim verifiers.
    if any(
        c.model_dump() not in [source.model_dump() for source in answer.citations]
        for c in answer.relevant_clauses
    ):
        return False
    claims = [
        answer.direct_answer,
        answer.explanation,
        answer.verification_step,
        *answer.excerpts,
        *answer.missing_information,
        *answer.follow_up_questions,
    ]
    return all(normalized(claim) in evidence for claim in claims if claim.strip())


def compare_documents(left: dict, right: dict) -> list[dict]:
    before = (left.get('analysis') or analyze_document(left['id'], left['pages']))['clauses']
    after = (right.get('analysis') or analyze_document(right['id'], right['pages']))['clauses']
    unmatched = set(range(len(after)))
    findings = []
    for clause in before:
        options = [
            (
                i,
                0.5 * (clause['clause_type'] == after[i]['clause_type'])
                + 0.35 * max(0, similarity(clause['original'], after[i]['original']))
                + 0.15 * SequenceMatcher(None, clause['original'], after[i]['original']).ratio(),
            )
            for i in unmatched
        ]
        best = max(options, key=lambda x: x[1], default=(None, 0))
        paired = after[best[0]] if best[0] is not None and best[1] >= 0.56 else None
        if paired is not None:
            unmatched.remove(best[0])
            if normalized(clause['original']) == normalized(paired['original']):
                continue
        findings.append(_comparison(clause, paired))
    findings.extend(_comparison(None, after[i]) for i in sorted(unmatched))
    left_terms = set(tokens(' '.join(c['original'] for c in before)))
    right_terms = set(tokens(' '.join(c['original'] for c in after)))
    overlap = len(left_terms & right_terms) / max(1, len(left_terms | right_terms))
    if left_terms and right_terms and overlap < 0.12:
        for finding in findings:
            finding['warning'] = (
                'The extracted texts have limited vocabulary overlap. Confirm that these are the documents you intend to compare; automatic clause alignment may be less reliable.'
            )
    return [ComparisonFinding.model_validate(f).model_dump() for f in findings]


def compare_checklist(document: dict, required_clause_types: list[str]) -> list[dict]:
    if not isinstance(required_clause_types, list) or not 1 <= len(required_clause_types) <= 50:
        raise ValueError('Choose between 1 and 50 clause types for the review checklist.')
    allowed = {kind for kind, _ in CLASSIFIERS} | {'Other'}
    if any(not isinstance(kind, str) or kind not in allowed for kind in required_clause_types):
        raise ValueError(
            'Unknown clause type in review checklist. Choose one of the supported clause categories.'
        )
    analysis = document.get('analysis') or analyze_document(document['id'], document['pages'])
    source = {**document, 'analysis': analysis}
    findings = []
    for kind in dict.fromkeys(required_clause_types):
        clauses = [
            clause
            for clause in analysis['clauses']
            if clause['clause_type'] == kind and not INJECTION.search(clause['original'])
        ]
        citations = [
            citation
            for clause in clauses
            for citation in clause['citations']
            if verify_citation(citation, [source])
        ]
        explanation = (
            'Matching source sections were located. This is a classification result; review the cited wording for scope, exceptions, and extraction quality.'
            if citations
            else 'No matching section was located by extraction and classification. This is an extraction coverage gap, not proof that the provision is absent. Review the original and referenced attachments.'
        )
        findings.append(
            ChecklistFinding(
                clause_type=kind,
                status='located' if citations else 'not_located',
                citations=citations,
                explanation=explanation,
            ).model_dump()
        )
    return findings


def _comparison(left: dict | None, right: dict | None) -> dict:
    source = left or right
    before, after = (left or {}).get('original', ''), (right or {}).get('original', '')
    changes = []
    for label, pattern in [('date', DATE_RE), ('amount', AMOUNT_RE), ('time window', WINDOW_RE)]:
        if set(re.findall(pattern, before, re.I)) != set(re.findall(pattern, after, re.I)):
            changes.append(label)
    description = ('Changed ' + ', '.join(changes) + '. ') if changes else ''
    description += 'Clause alignment uses category and local concept similarity. Review exact wording and both sources; legal effect has not been determined.'
    return dict(
        id=ident(before, after),
        clause_type=source['clause_type'],
        change_type='modified' if left and right else 'removed' if left else 'added',
        before=before or 'Not present in the matched source',
        after=after or 'Not present in the matched source',
        explanation=description,
        attention_before=(left or {}).get('attention', 'Insufficient information'),
        attention_after=(right or {}).get('attention', 'Insufficient information'),
        citations=(left or {}).get('citations', []) + (right or {}).get('citations', []),
    )
