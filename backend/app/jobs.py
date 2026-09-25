import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import delete, select
from .database import (
    AnalysisRun,
    Citation,
    Clause,
    Document,
    DocumentPage,
    DocumentSection,
    DocumentVersion,
    DocumentChunk,
    Entity,
    Obligation,
    RiskFinding,
    now,
)
from .providers import configured_embedding_provider, configured_provider
from .generation import generation_signature
from .retrieval import build_index, analysis_signature

logger = logging.getLogger('legallens.jobs')
TERMINAL = {'ready', 'partially_processed', 'failed'}


class Processor:
    """Durable SQL jobs with bounded local execution. Deploy one API worker."""

    def __init__(self, sessions, settings):
        self.sessions = sessions
        self.settings = settings
        self.pool = (
            None if settings.serverless else ThreadPoolExecutor(max_workers=2, thread_name_prefix='document')
        )
        self.lock = threading.Lock()
        self.pending: set[str] = set()

    def submit(self, job_id: str):
        if self.pool is None:
            return  # The authenticated processing request owns execution on serverless hosts.
        with self.lock:
            if job_id in self.pending:
                return
            self.pending.add(job_id)
        self.pool.submit(self._run, job_id)

    def recover(self):
        if self.settings.serverless:
            return
        with self.sessions() as db:
            for job in db.scalars(select(AnalysisRun).where(AnalysisRun.status.not_in(TERMINAL))):
                self.submit(job.id)

    def close(self):
        if self.pool:
            self.pool.shutdown(wait=True)

    def _run(self, job_id: str):
        try:
            self.process(job_id)
        except Exception as error:
            # Do not log exceptions from parsers/providers: they may contain source text.
            logger.error('document_job_failed job_id=%s', job_id)
            with self.sessions() as db:
                job = db.get(AnalysisRun, job_id)
                if job:
                    job.status = 'failed'
                    job.error = 'Processing could not complete. Check that the document is readable and unencrypted, then retry analysis or upload a clearer copy.'
                    from .extraction import EncryptedDocumentError

                    if isinstance(error, EncryptedDocumentError):
                        job.error = 'This PDF is password-protected. Export an unlocked copy from your PDF application, then upload it again.'
                    job.completed_at = now()
                    doc = db.get(Document, job.document_id)
                    if doc:
                        doc.status = 'partially_processed' if doc.analysis else 'failed'
                        doc.warnings = list(doc.warnings) + [job.error]
                    db.commit()
        finally:
            with self.lock:
                self.pending.discard(job_id)

    def process(self, job_id: str):
        from .extraction import extract_document
        from .intelligence import analyze_document, verify_citation

        with self.sessions() as db:
            job = db.get(AnalysisRun, job_id)
            if not job or job.status in TERMINAL:
                return
            doc = db.get(Document, job.document_id)
            if not doc:
                return
            job.status = doc.status = 'extracting'
            db.commit()
            doc_id, name, mime, key = doc.id, doc.name, doc.media_type, doc.storage_key
        from .storage import storage

        data = storage(self.settings).read(key)
        pages = extract_document(
            data,
            name,
            mime,
            allow_ocr=not self.settings.serverless,
            max_pages=self.settings.max_pages,
            max_text=30000 if self.settings.serverless else 2_000_000,
        )
        if len(pages) > self.settings.max_pages:
            raise ValueError('Page budget exceeded')
        with self.sessions() as db:
            job, doc = db.get(AnalysisRun, job_id), db.get(Document, doc_id)
            if not job or not doc:
                return
            job.status = doc.status = 'indexing'
            db.commit()
        analysis = analyze_document(doc_id, pages)
        generation_warning = None
        generator = configured_provider(self.settings)
        if generator:
            with self.sessions() as db:
                current_job, current_doc = db.get(AnalysisRun, job_id), db.get(Document, doc_id)
                if not current_job or not current_doc:
                    return
                current_job.status = current_doc.status = 'analyzing'
                db.commit()
            try:
                analysis = generator.analyze(analysis)
            except (RuntimeError, ValueError):
                generation_warning = 'Gemini analysis was unavailable or failed grounding checks. Showing local extraction; retry analysis for generated explanations.'
                analysis['mode'] = 'Local extraction fallback · AI analysis unavailable'
        evidence_doc = [{'id': doc_id, 'pages': pages, 'analysis': analysis}]
        citations = []

        def gather(value):
            if isinstance(value, dict):
                for c in value.get('citations', []):
                    if not verify_citation(c, evidence_doc):
                        raise ValueError('Generated citation does not map to the source')
                    citations.append(c)
                for key, child in value.items():
                    if key != 'citations':
                        gather(child)
            elif isinstance(value, list):
                for child in value:
                    gather(child)

        gather(analysis)
        provider = configured_embedding_provider(self.settings)
        index_warning = None
        try:
            chunks = build_index({'id': doc_id, 'name': name, 'analysis': analysis}, provider)
        except (RuntimeError, ValueError):
            if not provider:
                raise
            chunks = build_index({'id': doc_id, 'name': name, 'analysis': analysis})
            index_warning = 'Hosted embedding indexing was unavailable. Local concept and keyword retrieval remains available. Retry analysis to rebuild hosted embeddings.'
            provider = None
        with self.sessions() as db:
            job, doc = db.get(AnalysisRun, job_id), db.get(Document, doc_id)
            if not job or not doc:
                return  # deletion during extraction must never recreate a document
            version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc_id))
            for table in (
                DocumentPage,
                DocumentSection,
                DocumentChunk,
                Clause,
                Entity,
                RiskFinding,
                Citation,
            ):
                db.execute(delete(table).where(table.document_id == doc_id))
            for chunk in chunks:
                chunk['analysis_signature'] = analysis_signature(provider)
                chunk['generation_signature'] = (
                    generation_signature(self.settings)
                    if not generation_warning and not analysis.get('generation_warnings')
                    else 'retry-required'
                )
                chunk['content_sha256'] = version.sha256
                db.add(DocumentChunk(document_id=doc_id, version_id=version.id, payload=chunk))
            for page in pages:
                db.add(DocumentPage(document_id=doc_id, number=page['number'], payload=page))
            for clause in analysis['clauses']:
                db.add(Clause(id=clause['id'], document_id=doc_id, version_id=version.id, payload=clause))
                db.add(
                    DocumentSection(
                        document_id=doc_id,
                        version_id=version.id,
                        payload={
                            'section': clause['citations'][0]['section'] if clause['citations'] else '',
                            'clause_id': clause['id'],
                        },
                    )
                )
                for term in clause.get('defined_terms', []):
                    db.add(
                        Entity(
                            document_id=doc_id,
                            version_id=version.id,
                            payload={'kind': 'defined_term', **term},
                        )
                    )
            for obligation in analysis['obligations']:
                existing = db.get(Obligation, obligation['id'])
                if existing:
                    # Only source payload changes. Concurrent personal edits use separate columns.
                    existing.payload = obligation
                else:
                    db.add(
                        Obligation(
                            id=obligation['id'],
                            document_id=doc_id,
                            workspace_id=doc.workspace_id,
                            version_id=version.id,
                            payload=obligation,
                            status='open',
                        )
                    )
            current_ids = [item['id'] for item in analysis['obligations']]
            db.execute(
                delete(Obligation).where(Obligation.document_id == doc_id, Obligation.id.not_in(current_ids))
            )
            for risk in analysis['risks']:
                db.add(RiskFinding(id=risk['id'], document_id=doc_id, version_id=version.id, payload=risk))
            for kind, field in analysis['metadata'].items():
                if field['value'] != 'Not found':
                    db.add(Entity(document_id=doc_id, version_id=version.id, payload={'kind': kind, **field}))
            unique = {(c['page'], c['section'], c['excerpt']): c for c in citations}
            for citation in unique.values():
                db.add(Citation(document_id=doc_id, version_id=version.id, payload=citation))
            warnings = [f'Page {p["number"]}: {p["warning"]}' for p in pages if p.get('warning')]
            warnings.extend(analysis.get('generation_warnings', []))
            if index_warning:
                warnings.append(index_warning)
            if generation_warning:
                warnings.append(generation_warning)
            doc.analysis = analysis
            doc.page_count = len(pages)
            doc.warnings = warnings
            # Pagination notices are informational; only extraction uncertainty makes a job partial.
            job.status = doc.status = (
                'partially_processed' if any(p.get('quality', 0) < 0.75 for p in pages) else 'ready'
            )
            job.completed_at = now()
            db.commit()
            logger.info('document_job_complete job_id=%s pages=%d status=%s', job_id, len(pages), job.status)
