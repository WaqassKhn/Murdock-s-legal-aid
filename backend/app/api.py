import csv
import hashlib
import io
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from .database import (
    AnalysisRun,
    ChatSession,
    Comparison,
    Document,
    DocumentPage,
    DocumentVersion,
    DocumentChunk,
    GeneratedReport,
    Message,
    Obligation,
    SessionToken,
    User,
    Workspace,
    uid,
)
from .security import (
    authenticate,
    create_session,
    hash_password,
    sanitize_filename,
    token_hash,
    verify_password,
)
from .uploads import validate_upload


async def serialize_mutation(request: Request):
    workspace_id = request.path_params.get('w')
    if workspace_id and request.method in {'POST', 'PATCH', 'DELETE', 'PUT'}:
        async with request.app.state.workspace_locks.hold(workspace_id):
            yield
    else:
        yield


router = APIRouter(prefix='/api', dependencies=[Depends(serialize_mutation)])


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Credentials(Input):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if value.count('@') != 1 or '.' not in value.split('@')[-1] or any(c.isspace() for c in value):
            raise ValueError('Enter a valid email address.')
        return value


class WorkspaceInput(Input):
    name: str = Field(min_length=1, max_length=160)
    objective: str = Field(default='', max_length=4000)
    jurisdiction: str = Field(default='Unknown', max_length=160)

    @field_validator('name')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Workspace name cannot be blank.')
        return value.strip()


class QuestionInput(Input):
    question: str = Field(min_length=3, max_length=2000)
    document_ids: list[str] | None = Field(default=None, max_length=20)
    jurisdiction: str | None = Field(default=None, max_length=160)


class CompareInput(Input):
    left_id: str
    right_id: str


class ChecklistInput(Input):
    document_id: str
    required_clause_types: list[str] = Field(min_length=1, max_length=50)


class ReportInput(Input):
    objective: str = Field(default='', max_length=4000)
    notes: str = Field(default='', max_length=10000)
    format: Literal['pdf', 'docx'] = 'pdf'


class StatusInput(Input):
    status: Literal['open', 'complete']


class CitationInput(Input):
    document_id: str
    page: int = Field(ge=1)
    section: str = Field(max_length=1000)
    excerpt: str = Field(min_length=1, max_length=30000)
    confidence: float = Field(default=1, ge=0, le=1)
    bbox: list[float] | None = None


def session(request: Request):
    with request.app.state.sessions() as db:
        yield db


def user(request: Request, db=Depends(session)):
    return authenticate(request, db)


def owned_workspace(db, user_id: str, workspace_id: str):
    workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id, Workspace.user_id == user_id))
    if not workspace:
        raise HTTPException(404, 'Workspace not found.')
    return workspace


def owned_document(db, user_id: str, workspace_id: str, document_id: str):
    owned_workspace(db, user_id, workspace_id)
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.workspace_id == workspace_id))
    if not doc:
        raise HTTPException(404, 'Document not found in this workspace.')
    return doc


def expensive(request, current):
    request.app.state.limiter.check(
        f'work:{current.id}', request.app.state.settings.expensive_requests_per_minute
    )


def workspace_json(db, workspace):
    return {
        'id': workspace.id,
        'name': workspace.name,
        'objective': workspace.objective,
        'jurisdiction': workspace.jurisdiction,
        'created_at': workspace.created_at,
        'is_demo': workspace.is_demo,
        'document_count': db.scalar(
            select(func.count()).select_from(Document).where(Document.workspace_id == workspace.id)
        ),
    }


def document_json(db, doc, full=False):
    job = db.scalar(
        select(AnalysisRun).where(AnalysisRun.document_id == doc.id).order_by(AnalysisRun.created_at.desc())
    )
    result = {
        key: getattr(doc, key)
        for key in (
            'id',
            'workspace_id',
            'name',
            'status',
            'media_type',
            'page_count',
            'warnings',
            'created_at',
            'version',
        )
    }
    result['job_id'] = job.id if job else None
    if full:
        result['pages'] = [
            page.payload
            for page in db.scalars(
                select(DocumentPage).where(DocumentPage.document_id == doc.id).order_by(DocumentPage.number)
            )
        ]
        result['analysis'] = doc.analysis
    return result


def job_json(job):
    return {
        **{k: getattr(job, k) for k in ('id', 'status', 'error', 'document_id')},
        'error_code': 'DOCUMENT_PROCESSING_FAILED' if job.error else None,
    }


def report_json(report):
    return {k: getattr(report, k) for k in ('id', 'title', 'created_at', 'format')}


def obligations_json(db, workspace_id):
    return [
        {**o.payload, 'status': o.status}
        for o in db.scalars(
            select(Obligation).where(Obligation.workspace_id == workspace_id).order_by(Obligation.created_at)
        )
    ]


def add_document(db, settings, workspace_id: str, name: str, data: bytes, mime: str):
    identifier = uid()
    key = identifier + Path(name).suffix.lower()
    (settings.storage_dir / key).write_bytes(data)
    try:
        doc = Document(id=identifier, workspace_id=workspace_id, name=name, media_type=mime, storage_key=key)
        db.add(doc)
        db.flush()
        db.add(DocumentVersion(document_id=doc.id, sha256=hashlib.sha256(data).hexdigest()))
        job = AnalysisRun(workspace_id=workspace_id, document_id=doc.id)
        db.add(job)
        db.commit()
        return doc, job
    except Exception:
        db.rollback()
        (settings.storage_dir / key).unlink(missing_ok=True)
        raise


@router.post('/auth/register', status_code=201)
def register(payload: Credentials, request: Request, response: Response, db=Depends(session)):
    request.app.state.limiter.check(f'auth:{request.client.host}', 10)
    account = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'An account with that email already exists. Sign in instead.') from None
    create_session(db, account, response, request.app.state.settings)
    return {'id': account.id, 'email': account.email}


@router.post('/auth/login')
def login(payload: Credentials, request: Request, response: Response, db=Depends(session)):
    request.app.state.limiter.check(f'auth:{request.client.host}', 10)
    account = db.scalar(select(User).where(User.email == payload.email))
    stored = account.password_hash if account else request.app.state.dummy_password
    valid = verify_password(payload.password, stored)
    if not account or not valid:
        raise HTTPException(401, 'Email or password is incorrect.')
    create_session(db, account, response, request.app.state.settings)
    return {'id': account.id, 'email': account.email}


@router.get('/auth/me')
def me(current=Depends(user)):
    return {'id': current.id, 'email': current.email}


@router.post('/auth/logout', status_code=204)
def logout(request: Request, response: Response, db=Depends(session)):
    db.execute(
        delete(SessionToken).where(
            SessionToken.token_hash == token_hash(request.cookies.get('legallens_session', ''))
        )
    )
    db.commit()
    response.delete_cookie('legallens_session', path='/')


@router.get('/workspaces')
def workspaces(current=Depends(user), db=Depends(session)):
    return [
        workspace_json(db, item)
        for item in db.scalars(
            select(Workspace).where(Workspace.user_id == current.id).order_by(Workspace.created_at.desc())
        )
    ]


@router.post('/workspaces', status_code=201)
def create_workspace(payload: WorkspaceInput, current=Depends(user), db=Depends(session)):
    workspace = Workspace(user_id=current.id, **payload.model_dump())
    db.add(workspace)
    db.commit()
    return workspace_json(db, workspace)


@router.delete('/workspaces/{w}', status_code=204)
def delete_workspace(w: str, request: Request, current=Depends(user), db=Depends(session)):
    workspace = owned_workspace(db, current.id, w)
    keys = list(db.scalars(select(Document.storage_key).where(Document.workspace_id == w)))
    keys.extend(db.scalars(select(GeneratedReport.storage_key).where(GeneratedReport.workspace_id == w)))
    db.delete(workspace)
    db.commit()
    for key in keys:
        (request.app.state.settings.storage_dir / key).unlink(missing_ok=True)


@router.get('/workspaces/{w}/documents')
def documents(w: str, current=Depends(user), db=Depends(session)):
    owned_workspace(db, current.id, w)
    return [
        document_json(db, doc)
        for doc in db.scalars(
            select(Document).where(Document.workspace_id == w).order_by(Document.created_at)
        )
    ]


@router.post('/workspaces/{w}/documents', status_code=202)
async def upload(
    w: str, request: Request, file: UploadFile = File(...), current=Depends(user), db=Depends(session)
):
    owned_workspace(db, current.id, w)
    expensive(request, current)
    settings = request.app.state.settings
    count = db.scalar(select(func.count()).select_from(Document).where(Document.workspace_id == w))
    if count >= settings.max_workspace_documents:
        raise HTTPException(
            409, 'Workspace document limit reached. Create another workspace or delete unused documents.'
        )
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    await file.close()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f'File exceeds the {settings.max_upload_mb} MB upload limit.')
    name = sanitize_filename(file.filename or '')
    mime = validate_upload(data, name, file.content_type or '')
    doc, job = add_document(db, settings, w, name, data, mime)
    request.app.state.processor.submit(job.id)
    return document_json(db, doc)


@router.get('/workspaces/{w}/documents/{d}')
def document(w: str, d: str, current=Depends(user), db=Depends(session)):
    return document_json(db, owned_document(db, current.id, w, d), full=True)


@router.get('/workspaces/{w}/documents/{d}/file')
def document_file(w: str, d: str, request: Request, current=Depends(user), db=Depends(session)):
    doc = owned_document(db, current.id, w, d)
    return FileResponse(
        request.app.state.settings.storage_dir / doc.storage_key,
        media_type=doc.media_type,
        filename=doc.name,
        content_disposition_type='inline' if doc.media_type == 'application/pdf' else 'attachment',
    )


@router.delete('/workspaces/{w}/documents/{d}', status_code=204)
def delete_document(w: str, d: str, request: Request, current=Depends(user), db=Depends(session)):
    doc = owned_document(db, current.id, w, d)
    # Reports and answers may quote deleted sources. Purge workspace derived snapshots.
    reports = list(db.scalars(select(GeneratedReport).where(GeneratedReport.workspace_id == w)))
    keys = [doc.storage_key] + [report.storage_key for report in reports]
    db.execute(delete(GeneratedReport).where(GeneratedReport.workspace_id == w))
    db.execute(delete(ChatSession).where(ChatSession.workspace_id == w))
    db.delete(doc)
    db.commit()
    for key in keys:
        (request.app.state.settings.storage_dir / key).unlink(missing_ok=True)


@router.get('/workspaces/{w}/jobs/{j}')
def job_status(w: str, j: str, current=Depends(user), db=Depends(session)):
    owned_workspace(db, current.id, w)
    job = db.scalar(select(AnalysisRun).where(AnalysisRun.id == j, AnalysisRun.workspace_id == w))
    if not job:
        raise HTTPException(404, 'Processing job not found.')
    return job_json(job)


@router.post('/workspaces/{w}/documents/{d}/analyze', status_code=202)
def analyze(w: str, d: str, request: Request, current=Depends(user), db=Depends(session)):
    doc = owned_document(db, current.id, w, d)
    expensive(request, current)
    active = db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.document_id == d,
            AnalysisRun.status.not_in(['ready', 'partially_processed', 'failed']),
        )
    )
    if active:
        return job_json(active)
    from .providers import configured_embedding_provider
    from .retrieval import analysis_signature

    owned_workspace(db, current.id, w)
    provider = configured_embedding_provider(request.app.state.settings)
    from .generation import generation_signature

    chunk = db.scalar(select(DocumentChunk).where(DocumentChunk.document_id == d))
    version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == d))
    if (
        doc.status == 'ready'
        and chunk
        and version
        and chunk.payload.get('analysis_signature') == analysis_signature(provider)
        and chunk.payload.get('generation_signature', 'local')
        == generation_signature(request.app.state.settings)
        and chunk.payload.get('content_sha256') == version.sha256
    ):
        previous = db.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.document_id == d, AnalysisRun.status == 'ready')
            .order_by(AnalysisRun.created_at.desc())
        )
        if previous:
            return job_json(previous)
    job = AnalysisRun(workspace_id=w, document_id=d, kind='analysis')
    doc.status = 'uploaded'
    db.add(job)
    db.commit()
    request.app.state.processor.submit(job.id)
    return job_json(job)


@router.get('/workspaces/{w}/obligations')
def obligations(w: str, current=Depends(user), db=Depends(session)):
    owned_workspace(db, current.id, w)
    return obligations_json(db, w)


@router.patch('/workspaces/{w}/obligations/{o}')
def update_obligation(w: str, o: str, payload: StatusInput, current=Depends(user), db=Depends(session)):
    owned_workspace(db, current.id, w)
    obligation = db.scalar(select(Obligation).where(Obligation.id == o, Obligation.workspace_id == w))
    if not obligation:
        raise HTTPException(404, 'Obligation not found.')
    obligation.status = payload.status
    db.commit()
    return {**obligation.payload, 'status': obligation.status}


@router.get('/workspaces/{w}/checklist')
def checklist(w: str, current=Depends(user), db=Depends(session)):
    owned_workspace(db, current.id, w)
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    columns = ['status', 'responsible_party', 'action', 'trigger', 'time_window', 'recurrence', 'consequence']
    writer.writerow(columns + ['citations'])
    for item in obligations_json(db, w):
        values = [str(item.get(k, '')) for k in columns] + [
            '; '.join(
                f'{c["document_id"]} p.{c["page"]} {c["section"]}: {c["excerpt"]}' for c in item['citations']
            )
        ]
        writer.writerow(
            ["'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value for value in values]
        )
    return Response(
        output.getvalue(),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="legallens-checklist.csv"'},
    )


@router.post('/workspaces/{w}/ask')
def ask(w: str, payload: QuestionInput, request: Request, current=Depends(user), db=Depends(session)):
    from .intelligence import answer_question, verify_citation

    owned_workspace(db, current.id, w)
    expensive(request, current)
    selected = (
        list(db.scalars(select(Document).where(Document.workspace_id == w)))
        if payload.document_ids is None
        else [owned_document(db, current.id, w, d) for d in payload.document_ids]
    )
    docs = [
        document_json(db, d, True)
        for d in selected
        if d.analysis and d.status in ('ready', 'partially_processed')
    ]
    for doc in docs:
        chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == doc['id'])
                .order_by(DocumentChunk.created_at, DocumentChunk.id)
            )
        )
        if chunks:
            doc['index'] = [chunk.payload for chunk in chunks]
    try:
        from .providers import configured_embedding_provider

        embedding_provider = configured_embedding_provider(request.app.state.settings) or False
        answer = answer_question(
            payload.question,
            docs,
            provider=request.app.state.answer_provider,
            embedding_provider=embedding_provider,
        )
    except (RuntimeError, ValueError):
        raise HTTPException(
            502,
            'The configured AI provider could not produce a verified response. Retry or switch the server to local extractive mode.',
        ) from None
    if any(not verify_citation(c, docs) for c in answer['citations']):
        raise HTTPException(
            502, 'An answer failed source verification. Please try a more specific document question.'
        )
    chat = db.scalar(select(ChatSession).where(ChatSession.workspace_id == w))
    if not chat:
        chat = ChatSession(workspace_id=w)
        db.add(chat)
        db.flush()
    db.add(
        Message(
            session_id=chat.id,
            payload={'question': payload.question, 'answer': answer, 'document_ids': [d['id'] for d in docs]},
        )
    )
    db.commit()
    return answer


@router.post('/workspaces/{w}/compare')
def compare(w: str, payload: CompareInput, request: Request, current=Depends(user), db=Depends(session)):
    from .intelligence import compare_documents

    expensive(request, current)
    if payload.left_id == payload.right_id:
        raise HTTPException(422, 'Select two different documents to compare.')
    left = owned_document(db, current.id, w, payload.left_id)
    right = owned_document(db, current.id, w, payload.right_id)
    if not left.analysis or not right.analysis:
        raise HTTPException(409, 'Both documents must finish analysis before comparison.')
    findings = compare_documents(document_json(db, left, True), document_json(db, right, True))
    mode = 'clause-aligned semantic and exact-text comparison'
    generator = request.app.state.answer_provider
    if generator and hasattr(generator, 'compare'):
        try:
            findings = generator.compare(findings)
            mode = 'AI-generated comparison · evidence checked'
            if any('AI explanation omitted' in f.get('warning', '') for f in findings):
                mode += ' · mixed with local differences'
        except (RuntimeError, ValueError):
            raise HTTPException(
                502, 'AI comparison was unavailable or failed evidence checks. Retry comparison.'
            ) from None
    comparison = Comparison(
        workspace_id=w,
        left_id=left.id,
        right_id=right.id,
        payload={'findings': findings, 'mode': mode},
    )
    db.add(comparison)
    db.commit()
    return {'id': comparison.id, 'left_id': left.id, 'right_id': right.id, **comparison.payload}


@router.post('/workspaces/{w}/review-checklist')
def review_checklist(
    w: str, payload: ChecklistInput, request: Request, current=Depends(user), db=Depends(session)
):
    from .intelligence import compare_checklist

    expensive(request, current)
    doc = owned_document(db, current.id, w, payload.document_id)
    if not doc.analysis:
        raise HTTPException(409, 'Wait for analysis before reviewing checklist coverage.')
    try:
        return compare_checklist(document_json(db, doc, True), payload.required_clause_types)
    except ValueError:
        raise HTTPException(422, 'Choose supported clause categories for the review checklist.') from None


@router.post('/workspaces/{w}/citations/resolve')
def resolve(w: str, payload: CitationInput, current=Depends(user), db=Depends(session)):
    from .intelligence import verify_citation

    doc = owned_document(db, current.id, w, payload.document_id)
    citation = payload.model_dump()
    full = document_json(db, doc, True)
    if not verify_citation(citation, [full]):
        raise HTTPException(422, 'This excerpt could not be verified on the cited source page.')
    page = next(p for p in full['pages'] if p['number'] == payload.page)
    return {'citation': citation, 'page': page, 'verified': True}


@router.post('/workspaces/{w}/citations/preview')
def citation_preview(
    w: str, payload: CitationInput, request: Request, current=Depends(user), db=Depends(session)
):
    import fitz
    from .intelligence import verify_citation

    doc = owned_document(db, current.id, w, payload.document_id)
    expensive(request, current)
    if doc.media_type != 'application/pdf':
        raise HTTPException(415, 'Original page previews are available for PDF documents.')
    if not verify_citation(payload.model_dump(), [document_json(db, doc, True)]):
        raise HTTPException(422, 'The requested highlight could not be verified against the source.')
    with fitz.open(request.app.state.settings.storage_dir / doc.storage_key) as pdf:
        if payload.page > len(pdf):
            raise HTTPException(422, 'The cited PDF page does not exist.')
        page = pdf[payload.page - 1]
        scale = min(1.5, 1800 / max(page.rect.width, page.rect.height))
        if payload.bbox:
            page.draw_rect(
                fitz.Rect(payload.bbox),
                color=(0.1, 0.45, 0.4),
                fill=(0.9, 0.75, 0.2),
                fill_opacity=0.24,
                width=1.5,
            )
        image = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return Response(image.tobytes('png'), media_type='image/png')


@router.get('/workspaces/{w}/reports')
def reports(w: str, current=Depends(user), db=Depends(session)):
    owned_workspace(db, current.id, w)
    return [
        report_json(r)
        for r in db.scalars(
            select(GeneratedReport)
            .where(GeneratedReport.workspace_id == w)
            .order_by(GeneratedReport.created_at.desc())
        )
    ]


@router.post('/workspaces/{w}/reports', status_code=201)
def report(w: str, payload: ReportInput, request: Request, current=Depends(user), db=Depends(session)):
    from .reports import generate_report, report_sections

    workspace = owned_workspace(db, current.id, w)
    expensive(request, current)
    docs = [
        document_json(db, d, True) for d in db.scalars(select(Document).where(Document.workspace_id == w))
    ]
    if not any(d['analysis'] for d in docs):
        raise HTTPException(409, 'Analyze at least one document before preparing a consultation pack.')
    identifier = uid()
    key = identifier + '.' + payload.format
    sections = report_sections(
        workspace_json(db, workspace), docs, payload.objective, payload.notes, obligations_json(db, w)
    )
    content = generate_report(sections, payload.format)
    path = request.app.state.settings.storage_dir / key
    try:
        path.write_bytes(content)
        report = GeneratedReport(
            id=identifier,
            workspace_id=w,
            title=f'{workspace.name} — Consultation pack',
            format=payload.format,
            storage_key=key,
            document_ids=[d['id'] for d in docs],
        )
        db.add(report)
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return report_json(report)


@router.get('/workspaces/{w}/reports/{r}/download')
def download_report(w: str, r: str, request: Request, current=Depends(user), db=Depends(session)):
    owned_workspace(db, current.id, w)
    report = db.scalar(
        select(GeneratedReport).where(GeneratedReport.id == r, GeneratedReport.workspace_id == w)
    )
    if not report:
        raise HTTPException(404, 'Report not found.')
    mime = (
        'application/pdf'
        if report.format == 'pdf'
        else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    return FileResponse(
        request.app.state.settings.storage_dir / report.storage_key,
        media_type=mime,
        filename=f'legallens-consultation.{report.format}',
    )


@router.post('/demo', status_code=201)
def seed_demo(request: Request, current=Depends(user), db=Depends(session)):
    expensive(request, current)
    existing = list(
        db.scalars(select(Workspace).where(Workspace.user_id == current.id, Workspace.is_demo.is_(True)))
    )
    if existing:
        return [workspace_json(db, w) for w in existing]
    directory = Path(__file__).resolve().parents[2] / 'demo'
    created = []
    for prefix, title, objective in [
        ('employment', 'Employment agreement', 'Understand notice, confidentiality, and work ownership.'),
        ('rental', 'Rental agreement', 'Clarify renewal, deposit, and conflicting dates.'),
        ('nda', 'NDA version comparison', 'Review how confidentiality and liability changed.'),
    ]:
        files = sorted((directory / prefix).glob('*.txt'))
        if not files:
            raise HTTPException(503, 'Synthetic demo documents are unavailable in this installation.')
        workspace = Workspace(user_id=current.id, name=title, objective=objective, is_demo=True)
        db.add(workspace)
        db.commit()
        for file in files:
            doc, job = add_document(
                db,
                request.app.state.settings,
                workspace.id,
                f'SYNTHETIC — {file.name}',
                file.read_bytes(),
                'text/plain',
            )
            request.app.state.processor.submit(job.id)
        created.append(workspace_json(db, workspace))
    return created
