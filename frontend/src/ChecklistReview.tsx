import { useState } from 'react';
import { api, errorMessage, json, workspacePath } from './api';
import { Citations, ErrorNotice } from './components';
import type { Citation, DocumentRecord, Workspace } from './types';

const categories = [
  'Payment',
  'Termination',
  'Renewal',
  'Liability',
  'Indemnity',
  'Confidentiality',
  'Intellectual property',
  'Non-compete',
  'Non-solicitation',
  'Data protection',
  'Privacy',
  'Warranty',
  'Force majeure',
  'Dispute resolution',
  'Arbitration',
  'Governing law',
  'Penalties',
  'Notice periods',
  'Assignment',
  'Exclusivity',
];
interface Finding {
  clause_type: string;
  status: 'located' | 'not_located';
  explanation: string;
  citations: Citation[];
}

export function ChecklistReview({
  workspace,
  documents,
  onCitation,
}: {
  workspace: Workspace;
  documents: DocumentRecord[];
  onCitation: (c: Citation) => void;
}) {
  const ready = documents.filter((d) => d.status === 'ready' || d.status === 'partially_processed');
  const [documentId, setDocumentId] = useState(''),
    [selected, setSelected] = useState(['Payment', 'Termination', 'Liability', 'Governing law']);
  const [findings, setFindings] = useState<Finding[] | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const current = documentId || ready[0]?.id || '';
  async function review() {
    setBusy(true);
    setError('');
    setFindings(null);
    try {
      setFindings(
        await api<Finding[]>(`${workspacePath(workspace.id)}/review-checklist`, {
          method: 'POST',
          body: json({ document_id: current, required_clause_types: selected }),
        }),
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  if (!ready.length) return null;
  return (
    <section className="panel checklist-review">
      <div className="eyebrow">YOUR REVIEW CRITERIA</div>
      <h2>Check for the terms that matter to you.</h2>
      <p className="muted">
        Configure a clause checklist. A missing match is an extraction gap to investigate, not proof
        a term is absent.
      </p>
      <label>
        Document to check
        <select
          value={current}
          onChange={(e) => {
            setDocumentId(e.target.value);
            setFindings(null);
          }}
        >
          {ready.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </label>
      <fieldset>
        <legend>Clause categories</legend>
        <div className="checklist-categories">
          {categories.map((category) => (
            <label key={category}>
              <input
                type="checkbox"
                checked={selected.includes(category)}
                onChange={(e) => {
                  setSelected((items) =>
                    e.target.checked
                      ? [...items, category]
                      : items.filter((item) => item !== category),
                  );
                  setFindings(null);
                }}
              />
              {category}
            </label>
          ))}
        </div>
      </fieldset>
      <button className="secondary" onClick={review} disabled={busy || !selected.length}>
        {busy ? 'Checking coverage…' : 'Review checklist coverage'}
      </button>
      {error && <ErrorNotice message={error} />}
      <div aria-live="polite">
        {findings?.map((f) => (
          <article className="checklist-finding" key={f.clause_type}>
            <h3>
              {f.clause_type}{' '}
              <span className="badge neutral">
                {f.status === 'located' ? 'Source located' : 'Review coverage gap'}
              </span>
            </h3>
            <p>{f.explanation}</p>
            <Citations items={f.citations} onSelect={onCitation} />
          </article>
        ))}
      </div>
    </section>
  );
}
