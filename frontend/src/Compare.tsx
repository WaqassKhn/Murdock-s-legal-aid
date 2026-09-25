import { useState } from 'react';
import { ChecklistReview } from './ChecklistReview';
import { ArrowLeftRight, ArrowRight, GitCompareArrows } from 'lucide-react';
import { api, errorMessage, json, label, workspacePath } from './api';
import { AttentionBadge, Citations, Empty, ErrorNotice, Loading } from './components';
import type { Citation, Comparison, DocumentRecord, Workspace } from './types';

export function Compare({
  workspace,
  documents,
  onCitation,
}: {
  workspace: Workspace;
  documents: DocumentRecord[];
  onCitation: (c: Citation) => void;
}) {
  const ready = documents.filter((d) => ['ready', 'partially_processed'].includes(d.status));
  const [left, setLeft] = useState(ready[0]?.id || ''),
    [right, setRight] = useState(ready[1]?.id || ''),
    [result, setResult] = useState<Comparison | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function compare() {
    setBusy(true);
    setError('');
    setResult(null);
    try {
      setResult(
        await api<Comparison>(`${workspacePath(workspace.id)}/compare`, {
          method: 'POST',
          body: json({ left_id: left, right_id: right }),
        }),
      );
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
          <div className="eyebrow">SEE WHAT CHANGED. UNDERSTAND WHY.</div>
          <h1>The difference is in the details.</h1>
          <p>Compare clause meaning and exact wording across two documents.</p>
        </div>
        <GitCompareArrows size={33} className="heading-icon" />
      </div>
      {ready.length < 2 ? (
        <Empty title="A comparison needs two documents">
          Upload two versions, an agreement and an amendment, or competing agreements to the same
          workspace. Both must finish processing first.
        </Empty>
      ) : (
        <>
          <section className="panel comparison-picker">
            <label>
              Original / first document
              <select
                aria-label="Original document"
                value={left}
                onChange={(e) => {
                  setLeft(e.target.value);
                  setResult(null);
                }}
              >
                <option value="">Choose a document</option>
                {ready.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <ArrowLeftRight size={21} />
            <label>
              Revised / second document
              <select
                aria-label="Revised document"
                value={right}
                onChange={(e) => {
                  setRight(e.target.value);
                  setResult(null);
                }}
              >
                <option value="">Choose a document</option>
                {ready.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="primary"
              disabled={busy || !left || !right || left === right}
              onClick={compare}
            >
              {busy ? 'Comparing…' : 'Compare documents'}
              <ArrowRight size={16} />
            </button>
          </section>
          {left === right && <p className="field-hint">Choose two different documents.</p>}
          {error && <ErrorNotice message={error} />}{' '}
          {busy && <Loading text="Aligning clauses and checking changes…" />}
          {result && (
            <>
              <div className="section-heading">
                <h2>
                  {result.findings.length} {result.findings.length === 1 ? 'change' : 'changes'} to
                  review
                </h2>
                <span className="mode-badge">{result.mode}</span>
              </div>
              {result.findings.length === 0 ? (
                <Empty title="No clause-level changes detected">
                  Review both originals for differences the automated comparison may have missed.
                </Empty>
              ) : (
                <div className="comparison-results">
                  {result.findings.map((f) => (
                    <article className="panel comparison-finding" key={f.id}>
                      <div className="comparison-title">
                        <h3>{label(f.clause_type)}</h3>
                        <span className="badge neutral">{label(f.change_type)}</span>
                      </div>
                      <div className="diff-columns">
                        <div className="diff-before">
                          <span className="eyebrow">FIRST DOCUMENT</span>
                          <blockquote>{f.before || 'No matching clause found.'}</blockquote>
                          <Citations
                            items={f.citations.filter((c) => c.document_id === left)}
                            onSelect={onCitation}
                          />
                        </div>
                        <div className="diff-after">
                          <span className="eyebrow">SECOND DOCUMENT</span>
                          <blockquote>{f.after || 'No matching clause found.'}</blockquote>
                          <Citations
                            items={f.citations.filter((c) => c.document_id === right)}
                            onSelect={onCitation}
                          />
                        </div>
                      </div>
                      <div className="comparison-explanation">
                        <span className="eyebrow">SYSTEM INTERPRETATION</span>
                        <p>{f.explanation}</p>
                        {f.warning && <p className="quality-warning">{f.warning}</p>}
                        <div className="attention-movement">
                          <AttentionBadge value={f.attention_before} />
                          <ArrowRight size={14} />
                          <AttentionBadge value={f.attention_after} />
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
      <ChecklistReview workspace={workspace} documents={documents} onCitation={onCitation} />
      <div className="info-strip">
        <strong>Context makes a difference</strong>
        <span>
          An amendment may modify only selected terms. Review which original provisions remain in
          effect; an absent clause is not automatically removed.
        </span>
      </div>
    </>
  );
}
