import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowRight, Check, Download, FileDown, FileText } from 'lucide-react';
import { api, errorMessage, formatDate, json, workspacePath } from './api';
import { Disclaimer, Empty, ErrorNotice, Loading } from './components';
import type { Report, Workspace } from './types';

export function Reports({ workspace }: { workspace: Workspace }) {
  const [reports, setReports] = useState<Report[]>([]),
    [objective, setObjective] = useState(workspace.objective || ''),
    [notes, setNotes] = useState(''),
    [format, setFormat] = useState('pdf'),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    api<Report[]>(`${workspacePath(workspace.id)}/reports`)
      .then((data) => {
        if (!cancelled) setReports(data);
      })
      .catch((e) => {
        if (!cancelled) setError(errorMessage(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspace.id]);
  async function generate(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const report = await api<Report>(`${workspacePath(workspace.id)}/reports`, {
        method: 'POST',
        body: json({ objective, notes, format }),
      });
      setReports((r) => [report, ...r]);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">PREPARE FOR A BETTER CONVERSATION</div>
          <h1>Bring clarity to your consultation.</h1>
          <p>A structured handoff, grounded in your documents and shaped around your questions.</p>
        </div>
        <FileDown size={34} className="heading-icon" />
      </div>
      <div className="reports-layout">
        <section className="panel report-form">
          <div className="section-heading">
            <h2>Your lawyer preparation pack</h2>
            <FileText size={23} />
          </div>
          <form onSubmit={generate}>
            <label>
              Your objective
              <textarea
                rows={3}
                required
                maxLength={2000}
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="What would you like your lawyer to help you understand or achieve?"
              />
            </label>
            <label>
              Your notes <span className="optional">Optional</span>
              <textarea
                rows={5}
                maxLength={10000}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Add context, concerns, questions, or any known trigger dates. Your notes will be labeled separately from document facts."
              />
            </label>
            <label>
              Report format
              <select value={format} onChange={(e) => setFormat(e.target.value)}>
                <option value="pdf">PDF · Ready to share</option>
                <option value="docx">DOCX · Editable document</option>
              </select>
            </label>
            {error && <ErrorNotice message={error} />}
            <button className="primary full" disabled={busy}>
              {busy ? 'Preparing your report…' : 'Generate consultation pack'}
              <ArrowRight size={16} />
            </button>
          </form>
          <Disclaimer />
        </section>
        <aside>
          <section className="report-contents">
            <span className="eyebrow">WHAT GOES IN</span>
            <h3>
              The important things,
              <br />
              in one place.
            </h3>
            {[
              'Your objective and user notes',
              'Overview and important document facts',
              'High-attention clauses and ambiguities',
              'Obligations and deadlines',
              'Questions to ask your lawyer',
              'Relevant excerpts and source citations',
            ].map((t) => (
              <p key={t}>
                <Check size={16} />
                {t}
              </p>
            ))}
            <span className="field-hint">
              AI-generated informational material for independent professional review.
            </span>
          </section>
        </aside>
      </div>
      <div className="section-heading">
        <h2>
          Generated reports <span className="count">{reports.length}</span>
        </h2>
        <span className="small muted">Saved in this workspace</span>
      </div>
      {loading ? (
        <Loading text="Loading reports…" />
      ) : reports.length === 0 ? (
        <Empty title="Your preparation packs will appear here">
          Generate a report when you are ready to bring your findings to a qualified professional.
        </Empty>
      ) : (
        <div className="report-list">
          {reports.map((r) => (
            <article className="report-row" key={r.id}>
              <span className="document-icon">
                <FileText size={23} />
              </span>
              <div>
                <h3>{r.title}</h3>
                <p>
                  {formatDate(r.created_at)} · {r.format.toUpperCase()} · AI-generated
                </p>
              </div>
              <a
                className="secondary"
                href={`/api${workspacePath(workspace.id)}/reports/${r.id}/download`}
                download
              >
                <Download size={16} />
                Download
              </a>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
