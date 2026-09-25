import { useState } from 'react';
import type { FormEvent } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  BriefcaseBusiness,
  FileText,
  FolderPlus,
  Layers3,
  Plus,
  ShieldCheck,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { api, errorMessage, formatDate, json } from './api';
import { Empty, ErrorNotice, Modal } from './components';
import type { Workspace } from './types';

export function WorkspaceHome({
  workspaces,
  onOpen,
  onRefresh,
  onDelete,
}: {
  workspaces: Workspace[];
  onOpen: (workspace: Workspace) => void;
  onRefresh: () => Promise<void>;
  onDelete: (workspace: Workspace) => void;
}) {
  const [creating, setCreating] = useState(false),
    [name, setName] = useState(''),
    [objective, setObjective] = useState(''),
    [jurisdiction, setJurisdiction] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [demoConfirm, setDemoConfirm] = useState(false);
  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const workspace = await api<Workspace>('/workspaces', {
        method: 'POST',
        body: json({ name, objective, jurisdiction }),
      });
      await onRefresh();
      setCreating(false);
      onOpen(workspace);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function demo() {
    setBusy(true);
    setError('');
    try {
      await api('/demo', { method: 'POST' });
      await onRefresh();
      setDemoConfirm(false);
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
          <div className="eyebrow">YOUR DOCUMENT REVIEW DESK</div>
          <h1>A clearer picture starts here.</h1>
          <p>Bring your documents together. Understand what matters.</p>
        </div>
        <button className="primary" onClick={() => setCreating(true)}>
          <Plus size={17} />
          New workspace
        </button>
      </div>
      <section className="welcome-banner">
        <div className="welcome-copy">
          <span className="eyebrow">THE LEGALLENS APPROACH</span>
          <h2>
            More understanding.
            <br />
            <em>Less uncertainty.</em>
          </h2>
          <p>
            Explore the terms, track your obligations, and turn your questions into an informed
            conversation.
          </p>
          <button className="text-button" onClick={() => setDemoConfirm(true)}>
            Explore synthetic demo documents <ArrowRight size={16} />
          </button>
        </div>
        <div
          className="evidence-illustration"
          aria-label="Every insight connects to source evidence"
        >
          <div className="illustration-grid" />
          <div className="mini-node insight">
            <span className="node-icon">
              <Sparkles size={18} />
            </span>
            <div>
              <small>SYSTEM INTERPRETATION</small>
              <strong>What does this mean?</strong>
            </div>
          </div>
          <div className="connector-line" />
          <div className="mini-node clause">
            <span className="node-icon">
              <Layers3 size={18} />
            </span>
            <div>
              <small>DOCUMENT FACT</small>
              <strong>The relevant clause</strong>
            </div>
            <span className="mini-verified">
              <ShieldCheck size={15} />
            </span>
          </div>
          <div className="connector-line second" />
          <div className="mini-node source">
            <span className="node-icon">
              <FileText size={18} />
            </span>
            <div>
              <small>SUPPORTING EVIDENCE</small>
              <strong>The exact source page</strong>
            </div>
          </div>
          <div className="illustration-caption">
            <span className="status-dot" />
            Traceable by design.
          </div>
        </div>
      </section>
      <div className="stat-grid">
        <div>
          <span className="stat-icon">
            <BriefcaseBusiness size={21} />
          </span>
          <div>
            <strong>{workspaces.length.toString().padStart(2, '0')}</strong>
            <span>Workspaces</span>
          </div>
        </div>
        <div>
          <span className="stat-icon">
            <FileText size={21} />
          </span>
          <div>
            <strong>
              {workspaces
                .reduce((sum, w) => sum + w.document_count, 0)
                .toString()
                .padStart(2, '0')}
            </strong>
            <span>Documents in your care</span>
          </div>
        </div>
        <div>
          <span className="stat-icon">
            <ShieldCheck size={21} />
          </span>
          <div>
            <strong className="stat-word">Evidence first</strong>
            <span>Source-linked analysis</span>
          </div>
        </div>
      </div>
      {error && !creating && !demoConfirm && (
        <ErrorNotice message={error} onDismiss={() => setError('')} />
      )}
      <div className="section-heading">
        <h2>
          Your workspaces <span className="count">{workspaces.length}</span>
        </h2>
        <span className="muted small">Private to your account</span>
      </div>
      {workspaces.length === 0 ? (
        <Empty
          title="Give your documents a home"
          action={
            <button className="secondary" onClick={() => setCreating(true)}>
              <FolderPlus size={17} />
              Create a workspace
            </button>
          }
        >
          Organize a contract, its amendments, and supporting documents in one private space.
        </Empty>
      ) : (
        <div className="workspace-grid">
          {workspaces.map((w, index) => (
            <article className="workspace-card" key={w.id}>
              <div className="workspace-card-top">
                <span className={`workspace-icon tone-${index % 3}`}>
                  <BriefcaseBusiness size={22} />
                </span>
                <button
                  className="icon-button subtle"
                  aria-label={`Delete workspace ${w.name}`}
                  onClick={() => onDelete(w)}
                >
                  <Trash2 size={16} />
                </button>
              </div>
              {w.is_demo && <span className="demo-label">SYNTHETIC DEMO</span>}
              <h3>
                <button onClick={() => onOpen(w)}>
                  {w.name}
                  <ArrowUpRight size={18} />
                </button>
              </h3>
              <p>
                {w.objective ||
                  'A private space to understand your documents and prepare your questions.'}
              </p>
              <div className="workspace-card-footer">
                <span>
                  <FileText size={14} />
                  {w.document_count} {w.document_count === 1 ? 'document' : 'documents'}
                </span>
                <span>{formatDate(w.created_at)}</span>
              </div>
            </article>
          ))}
          <button className="workspace-card add-card" onClick={() => setCreating(true)}>
            <span className="add-circle">
              <Plus size={24} />
            </span>
            <strong>Start something new</strong>
            <span>One workspace. The complete picture.</span>
          </button>
        </div>
      )}
      <div className="quiet-note">
        <ShieldCheck size={18} />
        <p>
          <strong>A starting point for better questions.</strong> LegalLens helps you understand
          document evidence. It does not replace a qualified legal professional.
        </p>
      </div>
      {creating && (
        <Modal title="Create a workspace" onClose={() => setCreating(false)}>
          <p className="muted">Keep related documents together for a more complete review.</p>
          <form onSubmit={create}>
            {error && <ErrorNotice message={error} />}
            <label>
              Workspace name
              <input
                autoFocus
                required
                maxLength={120}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. My employment agreement"
              />
            </label>
            <label>
              Your objective
              <textarea
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="What would you like to understand?"
                rows={3}
                maxLength={2000}
              />
            </label>
            <label>
              Jurisdiction, if known <span className="optional">Optional</span>
              <input
                value={jurisdiction}
                onChange={(e) => setJurisdiction(e.target.value)}
                placeholder="e.g. England and Wales"
                maxLength={100}
              />
            </label>
            <p className="field-hint">
              Use the governing law stated in the document. Analysis can continue when jurisdiction
              is unknown.
            </p>
            <button className="primary full" disabled={busy}>
              {busy ? 'Creating…' : 'Create workspace'}
              <ArrowRight size={16} />
            </button>
          </form>
        </Modal>
      )}
      {demoConfirm && (
        <Modal title="Explore with synthetic documents" onClose={() => setDemoConfirm(false)}>
          <p>
            We will add three clearly labeled example workspaces: an employment agreement, a rental
            agreement, and an NDA version comparison.
          </p>
          <p className="muted">
            These fictional documents are for demonstrating the product. They are not templates or
            legal advice. When AI is configured, these samples also use the configured provider for
            explanations and answers. Each result identifies whether AI or a local fallback was
            used.
          </p>
          {error && <ErrorNotice message={error} />}
          <button className="primary full" onClick={demo} disabled={busy}>
            {busy ? 'Preparing workspaces…' : 'Add synthetic demo workspaces'}
            <ArrowRight size={16} />
          </button>
        </Modal>
      )}
    </>
  );
}
