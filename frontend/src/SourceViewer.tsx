import { useEffect, useState } from 'react';
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  ShieldCheck,
} from 'lucide-react';
import { api, errorMessage, workspacePath } from './api';
import { ErrorNotice, HighlightedText, Loading, Modal } from './components';
import type { Citation, DocumentDetail, Page } from './types';

export function PageViewer({
  pages,
  pageNumber,
  onPageChange,
  excerpt,
}: {
  pages: Page[];
  pageNumber: number;
  onPageChange: (page: number) => void;
  excerpt?: string;
}) {
  const page = pages.find((p) => p.number === pageNumber);
  return (
    <div className="page-viewer">
      <div className="viewer-toolbar">
        <span>
          <FileText size={15} />
          Source text
        </span>
        <div className="page-controls">
          <button
            className="icon-button"
            disabled={pageNumber <= 1}
            onClick={() => onPageChange(pageNumber - 1)}
            aria-label="Previous page"
          >
            <ChevronLeft size={15} />
          </button>
          <label className="page-select">
            <span className="sr-only">Source page</span>
            <select
              aria-label="Source page"
              value={pageNumber}
              onChange={(e) => onPageChange(Number(e.target.value))}
            >
              {pages.map((p) => (
                <option key={p.number} value={p.number}>
                  Page {p.number}
                </option>
              ))}
            </select>
          </label>
          <span>of {pages.length}</span>
          <button
            className="icon-button"
            disabled={pageNumber >= pages.length}
            onClick={() => onPageChange(pageNumber + 1)}
            aria-label="Next page"
          >
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
      {page?.warning && (
        <div className="quality-warning">
          Page {page.number}: {page.warning}
        </div>
      )}
      {page?.ocr && <div className="ocr-label">OCR-extracted page · Verify against original</div>}
      <div className="paper-scroll">
        <div className="source-paper">
          <div className="paper-label">DOCUMENT EVIDENCE · PAGE {pageNumber}</div>
          <div className="source-text">
            <HighlightedText
              text={page?.text || 'No extractable text on this page.'}
              excerpt={excerpt}
            />
          </div>
          <span className="paper-page">{pageNumber}</span>
        </div>
      </div>
    </div>
  );
}
export function CitationDialog({
  citation,
  workspaceId,
  onClose,
}: {
  citation: Citation;
  workspaceId: string;
  onClose: () => void;
}) {
  const [document, setDocument] = useState<DocumentDetail | null>(null),
    [error, setError] = useState(''),
    [verified, setVerified] = useState(false),
    [page, setPage] = useState(citation.page),
    [original, setOriginal] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setDocument(null);
    setError('');
    setPage(citation.page);
    Promise.all([
      api<DocumentDetail>(`${workspacePath(workspaceId)}/documents/${citation.document_id}`),
      api<{ verified: boolean }>(`${workspacePath(workspaceId)}/citations/resolve`, {
        method: 'POST',
        body: JSON.stringify(citation),
      }),
    ])
      .then(([doc, resolution]) => {
        if (!cancelled) {
          setDocument(doc);
          setVerified(resolution.verified);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(errorMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [citation, workspaceId]);
  return (
    <Modal title="Follow the evidence" onClose={onClose} wide>
      {error ? (
        <ErrorNotice message={error} />
      ) : !document ? (
        <Loading text="Resolving the source citation…" />
      ) : (
        <>
          <div className="source-summary">
            <div>
              <strong>{document.name}</strong>
              <span>
                Version {document.version} · Page {citation.page} · {citation.section}
              </span>
            </div>
            <span className={`badge ${verified ? 'low' : 'high'}`}>
              <ShieldCheck size={13} />
              {verified ? 'Excerpt verified' : 'Unverified citation'}
            </span>
          </div>
          <blockquote className="selected-excerpt">{citation.excerpt}</blockquote>
          <div className="source-actions">
            <button
              className={`secondary ${!original ? 'selected' : ''}`}
              onClick={() => setOriginal(false)}
            >
              <BookOpen size={15} />
              Extracted text
            </button>
            {document.media_type === 'application/pdf' && (
              <button
                className={`secondary ${original ? 'selected' : ''}`}
                onClick={() => setOriginal(true)}
              >
                <FileText size={15} />
                Original PDF
              </button>
            )}
            <a
              className="text-button"
              href={`/api${workspacePath(workspaceId)}/documents/${document.id}/file#page=${citation.page}`}
              target="_blank"
              rel="noreferrer"
            >
              Open original
              <ExternalLink size={14} />
            </a>
          </div>
          {original ? (
            <OriginalPreview citation={citation} workspaceId={workspaceId} />
          ) : (
            <PageViewer
              pages={document.pages}
              pageNumber={page}
              onPageChange={setPage}
              excerpt={page === citation.page ? citation.excerpt : undefined}
            />
          )}
          <p className="field-hint">
            Highlights identify supporting text or its containing block when coordinates are
            available. Source verification confirms the excerpt, not a legal conclusion.
          </p>
        </>
      )}
    </Modal>
  );
}

function OriginalPreview({ citation, workspaceId }: { citation: Citation; workspaceId: string }) {
  const [url, setUrl] = useState(''),
    [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = '';
    fetch(`/api${workspacePath(workspaceId)}/citations/preview`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(citation),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error((await response.json()).detail || 'Page preview unavailable');
        return response.blob();
      })
      .then((blob) => {
        if (!controller.signal.aborted) {
          objectUrl = URL.createObjectURL(blob);
          setUrl(objectUrl);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [citation, workspaceId]);
  return error ? (
    <ErrorNotice message={error} />
  ) : url ? (
    <div className="original-preview">
      <img
        src={url}
        alt={`Original source page ${citation.page}${citation.bbox ? ', supporting block highlighted' : ''}`}
      />
      {!citation.bbox && (
        <p className="field-hint">
          This citation has no source coordinates; use the extracted-text view to locate its
          excerpt.
        </p>
      )}
    </div>
  ) : (
    <Loading text="Rendering original page…" />
  );
}
