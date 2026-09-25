import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import {
  ArrowRight,
  BookOpen,
  Check,
  Download,
  ListChecks,
  PencilLine,
  RefreshCw,
} from 'lucide-react';
import { api, errorMessage, json, workspacePath } from './api';
import { QuestionList, Timeline } from './ActionSections';
import { AttentionBadge, Citations, Empty, ErrorNotice, Loading } from './components';
import type { ActionPlan, Citation, Obligation, Workspace } from './types';

type ActionTab = 'Checklist' | 'Timeline' | 'Open questions' | 'Review & prepare';

export function Obligations({
  workspace,
  onCitation,
}: {
  workspace: Workspace;
  onCitation: (citation: Citation) => void;
}) {
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const [tab, setTab] = useState<ActionTab>('Checklist');
  const [saving, setSaving] = useState('');
  const [editing, setEditing] = useState<Obligation | null>(null);
  const [userAction, setUserAction] = useState('');
  const [userNotes, setUserNotes] = useState('');
  const [revision, setRevision] = useState(0);
  const [savedNotice, setSavedNotice] = useState('');
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    api<ActionPlan>(`${workspacePath(workspace.id)}/action-plan`)
      .then((data) => {
        if (!cancelled) setPlan(data);
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
  }, [workspace.id, revision]);
  function applyItem(item: Obligation) {
    setPlan((current) =>
      current
        ? {
            ...current,
            responsibilities: current.responsibilities.map((o) => (o.id === item.id ? item : o)),
            timeline: current.timeline.map((event) =>
              event.id === item.id ? { ...event, status: item.status } : event,
            ),
          }
        : current,
    );
  }
  async function toggle(item: Obligation) {
    const status = item.status === 'open' ? 'complete' : 'open';
    setSaving(item.id);
    setError('');
    applyItem({ ...item, status });
    try {
      const saved = await api<Obligation>(
        `${workspacePath(workspace.id)}/action-plan/obligations/${item.id}`,
        { method: 'PATCH', body: json({ status }) },
      );
      applyItem(saved);
    } catch (e) {
      applyItem(item);
      setError(errorMessage(e));
    } finally {
      setSaving('');
    }
  }
  function beginEdit(item: Obligation) {
    setEditing(item);
    setUserAction(item.user_action || '');
    setUserNotes(item.user_notes || '');
    setError('');
    setSavedNotice('');
  }
  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editing) return;
    setSaving(editing.id);
    setError('');
    try {
      const saved = await api<Obligation>(
        `${workspacePath(workspace.id)}/action-plan/obligations/${editing.id}`,
        { method: 'PATCH', body: json({ user_action: userAction, user_notes: userNotes }) },
      );
      applyItem(saved);
      setEditing(null);
      setSavedNotice('Your personal task and notes were saved. Source evidence is unchanged.');
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving('');
    }
  }
  const items = plan?.responsibilities || [];
  const displayed = items.filter((item) => filter === 'all' || item.status === filter);
  const complete = items.filter((item) => item.status === 'complete').length;
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Your next steps, in focus.</h1>
        </div>
        <div className="action-exports">
          <a className="secondary" href={`/api${workspacePath(workspace.id)}/checklist`} download>
            <Download size={16} />
            Export checklist
          </a>
          <a
            className="primary"
            href={`/api${workspacePath(workspace.id)}/action-plan/export`}
            download
          >
            <Download size={16} />
            Download action plan
          </a>
        </div>
      </div>
      <div className="action-principle">
        <BookOpen size={19} />
        <p>
          <strong>Your planning. The document’s words.</strong> Edit your next steps and notes
          freely. Original obligations and citations remain separate and unchanged.
        </p>
      </div>
      {error && <ErrorNotice message={error} />}{' '}
      {savedNotice && (
        <p className="action-saved" role="status">
          <Check size={16} />
          {savedNotice}
        </p>
      )}
      {loading ? (
        <Loading text="Gathering your action plan and supporting evidence…" />
      ) : !plan ? (
        <Empty
          title="Your action plan could not be loaded"
          action={
            <button className="secondary" onClick={() => setRevision((r) => r + 1)}>
              <RefreshCw size={16} />
              Try again
            </button>
          }
        >
          Check the connection and try again. Your saved tasks are unchanged.
        </Empty>
      ) : (
        <>
          <div className="obligation-summary">
            <div>
              <ListChecks size={22} />
              <strong>{items.length - complete}</strong>
              <span>Open obligations</span>
            </div>
            <div>
              <Check size={22} />
              <strong>{complete}</strong>
              <span>Marked complete</span>
            </div>
            <p>
              Relative deadlines stay relative.
              <br />
              <span>We do not assume an unknown trigger date.</span>
            </p>
          </div>
          <div className="tabs action-tabs" role="tablist" aria-label="Action Center sections">
            {(['Checklist', 'Timeline', 'Open questions', 'Review & prepare'] as ActionTab[]).map(
              (name) => (
                <button
                  key={name}
                  role="tab"
                  aria-selected={tab === name}
                  onClick={() => setTab(name)}
                >
                  {name}
                </button>
              ),
            )}
          </div>
          {tab === 'Checklist' && (
            <>
              <div className="section-heading">
                <div>
                  <h2>Your obligation tracker</h2>
                  <p className="field-hint">
                    Use personal tasks to turn the source wording into your own preparation
                    checklist.
                  </p>
                </div>
                <div className="segmented" aria-label="Filter obligations">
                  {['all', 'open', 'complete'].map((value) => (
                    <button
                      key={value}
                      aria-pressed={filter === value}
                      onClick={() => setFilter(value)}
                    >
                      {value === 'all' ? 'All tasks' : value === 'open' ? 'Open' : 'Complete'}
                    </button>
                  ))}
                </div>
              </div>
              {editing && (
                <section className="panel action-editor" aria-label="Edit personal task">
                  <div className="eyebrow">USER-AUTHORED PLANNING · NOT DOCUMENT EVIDENCE</div>
                  <h3>Make this next step your own.</h3>
                  <div className="action-original">
                    <span>Original document obligation</span>
                    <p>{editing.action}</p>
                    <Citations items={editing.citations} onSelect={onCitation} />
                  </div>
                  <form onSubmit={saveEdit}>
                    <label>
                      Your action
                      <textarea
                        autoFocus
                        rows={2}
                        maxLength={2000}
                        value={userAction}
                        onChange={(event) => setUserAction(event.target.value)}
                        placeholder="e.g. Gather the notice email and confirm the delivery method."
                      />
                    </label>
                    <label>
                      Your notes
                      <textarea
                        rows={3}
                        maxLength={4000}
                        value={userNotes}
                        onChange={(event) => setUserNotes(event.target.value)}
                        placeholder="Add context or a question for your lawyer. These notes are saved in this workspace."
                      />
                    </label>
                    <p className="field-hint">
                      Personal edits are not verified facts and cannot change the document wording
                      or a legal obligation. Clear a field to remove your note.
                    </p>
                    <div className="modal-actions">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => setEditing(null)}
                        disabled={!!saving}
                      >
                        Cancel edit
                      </button>
                      <button className="primary" disabled={!!saving}>
                        {saving ? 'Saving…' : 'Save personal task'}
                        <Check size={16} />
                      </button>
                    </div>
                  </form>
                </section>
              )}
              {!displayed.length ? (
                <Empty
                  title={items.length ? 'No tasks in this view' : 'No obligations extracted yet'}
                >
                  {items.length
                    ? 'Choose another filter to see your checklist.'
                    : 'Once a document is processed, identified responsibilities and deadlines will appear here.'}
                </Empty>
              ) : (
                <div className="table-wrap">
                  <table className="obligation-table action-table">
                    <thead>
                      <tr>
                        <th>Status</th>
                        <th>Document obligation & your plan</th>
                        <th>Trigger & time window</th>
                        <th>Consequence</th>
                        <th>Evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {displayed.map((item) => (
                        <tr key={item.id} className={item.status === 'complete' ? 'completed' : ''}>
                          <td>
                            <label className="task-checkbox">
                              <input
                                type="checkbox"
                                checked={item.status === 'complete'}
                                onChange={() => void toggle(item)}
                                disabled={!!saving}
                                aria-label={`Mark ${item.action} ${item.status === 'open' ? 'complete' : 'open'}`}
                              />
                              <span>{item.status === 'complete' ? 'Complete' : 'Open'}</span>
                            </label>
                          </td>
                          <td>
                            <span className="action-source-label">Document obligation</span>
                            <strong>{item.action}</strong>
                            <span className="cell-sub">
                              Responsible party: {item.responsible_party || 'Not specified'}
                            </span>
                            {item.user_action && (
                              <div className="personal-action">
                                <span>Your action · not source evidence</span>
                                <p>{item.user_action}</p>
                              </div>
                            )}
                            {item.user_notes && (
                              <div className="personal-note">
                                <span>Your notes</span>
                                <p>{item.user_notes}</p>
                              </div>
                            )}
                            <button
                              className="text-button action-edit-button"
                              onClick={() => beginEdit(item)}
                              disabled={!!saving}
                            >
                              <PencilLine size={13} />
                              Edit personal task
                            </button>
                          </td>
                          <td>
                            <strong>{item.time_window || 'Not specified'}</strong>
                            <span className="cell-sub">
                              Trigger: {item.trigger || 'Not specified'}
                            </span>
                            {item.recurrence && (
                              <span className="cell-sub">Recurrence: {item.recurrence}</span>
                            )}
                          </td>
                          <td>{item.consequence || 'Not specified'}</td>
                          <td>
                            <Citations items={item.citations} onSelect={onCitation} />
                            {item.document_name && (
                              <span className="cell-sub">{item.document_name}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="field-hint">
                Completion is your own tracking status; it does not certify that an obligation has
                been legally satisfied.
              </p>
            </>
          )}
          {tab === 'Timeline' && <Timeline events={plan.timeline} onCitation={onCitation} />}
          {tab === 'Open questions' && (
            <div className="action-questions">
              <QuestionList
                title="Points to clarify"
                introduction="Resolve missing context before treating an interpretation as a settled fact."
                items={plan.open_questions}
                onCitation={onCitation}
              />
              <QuestionList
                title="Questions for your lawyer"
                introduction="Bring these evidence-linked questions to an independent professional review."
                items={plan.lawyer_questions}
                onCitation={onCitation}
              />
              <QuestionList
                title="Conversation starters for the parties"
                introduction="Suggested discussion prompts, not instructions to accept, reject, or renegotiate a term."
                items={plan.negotiation_prompts}
                onCitation={onCitation}
              />
            </div>
          )}
          {tab === 'Review & prepare' && (
            <>
              <div className="section-heading">
                <h2>What deserves a closer look</h2>
                <span className="small muted">System interpretation</span>
              </div>
              {plan.risks.length ? (
                <div className="risk-grid">
                  {plan.risks.map((risk) => (
                    <article
                      key={`${risk.document_id}-${risk.id}`}
                      className="panel risk-card action-risk"
                    >
                      <AttentionBadge value={risk.severity} />
                      <h3>{risk.finding}</h3>
                      <p>{risk.why_it_matters}</p>
                      <div className="next-step">
                        <span className="eyebrow">SUGGESTED NEXT STEP</span>
                        <p>{risk.suggested_clarification}</p>
                      </div>
                      <Citations items={risk.citations} onSelect={onCitation} />
                      {risk.citations.length > 0 && (
                        <button
                          className="text-button"
                          onClick={() => onCitation(risk.citations[0])}
                        >
                          Inspect supporting evidence
                          <ArrowRight size={15} />
                        </button>
                      )}
                      <span className="cell-sub">{risk.document_name}</span>
                    </article>
                  ))}
                </div>
              ) : (
                <Empty title="No review findings identified">
                  This does not establish that the document is complete or risk-free. Review the
                  clauses and any missing context with a qualified professional.
                </Empty>
              )}
              <section className="panel preparation-evidence">
                <div className="section-heading">
                  <div>
                    <h2>Evidence to prepare</h2>
                  </div>
                  <BookOpen size={22} />
                </div>
                <p>
                  Collect the relevant originals and any correspondence that establishes a trigger
                  date. The excerpts below are from this workspace’s documents.
                </p>
                {plan.preparation_evidence.length ? (
                  plan.preparation_evidence.map((citation, index) => (
                    <details
                      className="preparation-excerpt"
                      key={`${citation.document_id}-${index}`}
                    >
                      <summary>
                        Page {citation.page} · {citation.section || 'Source passage'}
                      </summary>
                      <blockquote>{citation.excerpt}</blockquote>
                      <Citations items={[citation]} onSelect={onCitation} />
                    </details>
                  ))
                ) : (
                  <p className="muted">No supporting excerpts have been extracted yet.</p>
                )}
              </section>
            </>
          )}
        </>
      )}
    </>
  );
}
