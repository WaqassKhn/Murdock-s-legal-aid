import { useRef, useState } from 'react';
import {
  ArrowUpRight,
  CheckCircle2,
  FileText,
  LoaderCircle,
  Trash2,
  UploadCloud,
} from 'lucide-react';
import { api, errorMessage, formatDate, label, workspacePath } from './api';
import { Empty, ErrorNotice } from './components';
import type { Capabilities, DocumentRecord, Workspace } from './types';

export function Documents({
  workspace,
  documents,
  capabilities,
  onRefresh,
  onOpen,
  onDelete,
}: {
  workspace: Workspace;
  capabilities: Capabilities | null;
  documents: DocumentRecord[];
  onRefresh: () => Promise<void>;
  onOpen: (document: DocumentRecord) => void;
  onDelete: (document: DocumentRecord) => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  async function upload(files: FileList | null) {
    if (!files?.length || busy || !capabilities) return;
    setBusy(true);
    setError('');
    const failures: string[] = [];
    for (const file of Array.from(files)) {
      if (!/\.(pdf|docx|txt)$/i.test(file.name)) {
        failures.push(`${file.name}: unsupported format. Use PDF, DOCX, or TXT.`);
        continue;
      }
      if (file.size > capabilities.max_upload_mb * 1024 * 1024) {
        failures.push(`${file.name}: exceeds the ${capabilities.max_upload_mb} MB limit.`);
        continue;
      }
      try {
        const form = new FormData();
        form.append('file', file);
        await api(`${workspacePath(workspace.id)}/documents`, { method: 'POST', body: form });
      } catch (e) {
        failures.push(`${file.name}: ${errorMessage(e)}`);
      }
    }
    try {
      await onRefresh();
    } catch (e) {
      failures.push(errorMessage(e));
    }
    setError(failures.join(' '));
    setBusy(false);
    if (input.current) input.current.value = '';
  }
  return (
    <>
      <div className="page-heading">
        <div>
          {workspace.is_demo && <div className="eyebrow">SYNTHETIC DEMO</div>}
          <h1>Documents</h1>
        </div>
        <button
          className="primary"
          onClick={() => input.current?.click()}
          disabled={busy || !capabilities}
        >
          <UploadCloud size={17} />
          {busy ? 'Uploading…' : 'Upload documents'}
        </button>
      </div>
      <input
        ref={input}
        aria-label="Upload documents"
        disabled={busy || !capabilities}
        type="file"
        multiple
        accept=".pdf,.docx,.txt"
        className="sr-only"
        onChange={(e) => void upload(e.target.files)}
      />
      {error && <ErrorNotice message={error} onDismiss={() => setError('')} />}
      <button
        className={`upload-zone ${drag ? 'drag' : ''}`}
        disabled={busy || !capabilities}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          void upload(e.dataTransfer.files);
        }}
      >
        <span className="upload-symbol">
          {busy ? <LoaderCircle size={27} className="spin" /> : <UploadCloud size={27} />}
        </span>
        <strong>
          {busy ? 'Adding your documents…' : 'Drop your documents here, or browse files'}
        </strong>
        <span>
          {capabilities
            ? `${capabilities.ocr_available ? 'PDF, scanned PDF' : 'Text-based PDF'}, DOCX, or TXT · Up to ${capabilities.max_upload_mb} MB each`
            : 'Loading upload limits…'}
        </span>
      </button>
      {capabilities && !capabilities.ocr_available && (
        <p className="field-hint">Scanned PDFs need OCR before upload on this deployment.</p>
      )}
      {capabilities?.request_processing && documents.some((d) => d.processing_required) && (
        <p role="status" className="field-hint">
          Keep this workspace open while documents process. Pending work resumes when you reopen it.
        </p>
      )}
      <div className="section-heading">
        <h2>
          Document library <span className="count">{documents.length}</span>
        </h2>
      </div>
      <p className="field-hint">
        Uploads stay until deleted. Configured AI providers receive document text. See Privacy &
        retention.
      </p>
      {documents.length === 0 ? (
        <Empty title="Your evidence starts with a document">
          Upload a contract or related documents. We will preserve source pages so you can check
          every insight.
        </Empty>
      ) : (
        <div className="document-list">
          {documents.map((d) => (
            <article className="document-row" key={d.id}>
              <span className="document-icon">
                <FileText size={25} />
                <small>{d.name.split('.').pop()?.toUpperCase()}</small>
              </span>
              <div className="document-row-main">
                <button className="document-title" onClick={() => onOpen(d)}>
                  {d.name}
                  <ArrowUpRight size={15} />
                </button>
                <p>
                  {d.page_count} {d.page_count === 1 ? 'page' : 'pages'} <span>·</span> Version{' '}
                  {d.version} <span>·</span> Added {formatDate(d.created_at)}
                </p>
                {d.warnings?.length > 0 && (
                  <div className="quality-warning">{d.warnings.join(' ')}</div>
                )}
              </div>
              <div className={`status-badge status-${d.status}`}>
                {d.status === 'ready' ? (
                  <CheckCircle2 size={14} />
                ) : ['uploaded', 'extracting', 'indexing', 'analyzing'].includes(d.status) ? (
                  <LoaderCircle size={14} className="spin" />
                ) : null}
                {label(d.status)}
              </div>
              <button
                className="icon-button"
                aria-label={`Delete document ${d.name}`}
                onClick={() => onDelete(d)}
              >
                <Trash2 size={17} />
              </button>
            </article>
          ))}
        </div>
      )}
      <div className="info-strip">
        <strong>A note on page accuracy</strong>
        <span>PDF: original pages. DOCX and TXT: extracted logical pages.</span>
      </div>
    </>
  );
}
