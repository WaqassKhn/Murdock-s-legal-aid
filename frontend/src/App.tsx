import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  BriefcaseBusiness,
  FileStack,
  FileText,
  GitCompareArrows,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  MessageSquareText,
  Scale,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react';
import { api, ApiError, errorMessage, workspacePath } from './api';
import { Auth } from './Auth';
import { WorkspaceHome } from './WorkspaceHome';
import { Documents } from './Documents';
import { AnalysisView } from './Analysis';
import { Ask } from './Ask';
import { Compare } from './Compare';
import { Obligations } from './Obligations';
import { Reports } from './Reports';
import { CitationDialog } from './SourceViewer';
import { Disclaimer, Empty, ErrorNotice, Loading, Modal } from './components';
import type { Citation, DocumentRecord, User, View, Workspace } from './types';

const navigation = [
  { name: 'Workspaces', icon: LayoutDashboard },
  { name: 'Documents', icon: FileStack },
  { name: 'Analysis', icon: FileText },
  { name: 'Compare', icon: GitCompareArrows },
  { name: 'Obligations', icon: ListChecks },
  { name: 'Ask', icon: MessageSquareText },
  { name: 'Reports', icon: BriefcaseBusiness },
] as const;
export default function App() {
  const [user, setUser] = useState<User | null>(null),
    [initializing, setInitializing] = useState(true),
    [view, setView] = useState<View>('Workspaces'),
    [workspaces, setWorkspaces] = useState<Workspace[]>([]),
    [activeId, setActiveId] = useState(''),
    [documents, setDocuments] = useState<DocumentRecord[]>([]),
    [documentId, setDocumentId] = useState(''),
    [error, setError] = useState(''),
    [citation, setCitation] = useState<Citation | null>(null),
    [mobileOpen, setMobileOpen] = useState(false),
    [deleting, setDeleting] = useState<{
      type: 'workspace' | 'document';
      id: string;
      name: string;
    } | null>(null),
    [busy, setBusy] = useState(false),
    [privacy, setPrivacy] = useState(false);
  const active = workspaces.find((w) => w.id === activeId);
  const activeIdRef = useRef(activeId);
  useEffect(() => {
    activeIdRef.current = activeId;
  }, [activeId]);
  const refreshWorkspaces = useCallback(async () => {
    setWorkspaces(await api<Workspace[]>('/workspaces'));
  }, []);
  const refreshDocuments = useCallback(async () => {
    if (!activeId) return;
    const data = await api<DocumentRecord[]>(`${workspacePath(activeId)}/documents`);
    if (activeIdRef.current !== activeId) return;
    setDocuments(data);
    setDocumentId((current) => (data.some((d) => d.id === current) ? current : data[0]?.id || ''));
  }, [activeId]);
  useEffect(() => {
    api<User>('/auth/me')
      .then(setUser)
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 401)) setError(errorMessage(e));
      })
      .finally(() => setInitializing(false));
  }, []);
  useEffect(() => {
    if (user) void refreshWorkspaces().catch((e) => setError(errorMessage(e)));
  }, [user, refreshWorkspaces]);
  useEffect(() => {
    setDocuments([]);
    setDocumentId('');
    setCitation(null);
    if (activeId) void refreshDocuments().catch((e) => setError(errorMessage(e)));
  }, [activeId, refreshDocuments]);
  useEffect(() => {
    if (!activeId || !user) return;
    const timer = window.setInterval(() => {
      void refreshDocuments().catch((e) => setError(errorMessage(e)));
    }, 3000);
    return () => window.clearInterval(timer);
  }, [activeId, user, refreshDocuments]);
  function navigate(next: View) {
    setView(next);
    setMobileOpen(false);
    setError('');
  }
  function openWorkspace(w: Workspace) {
    setActiveId(w.id);
    navigate('Documents');
  }
  async function logout() {
    try {
      await api('/auth/logout', { method: 'POST' });
      setUser(null);
      setWorkspaces([]);
      setActiveId('');
      setDocuments([]);
      navigate('Workspaces');
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  async function confirmDelete() {
    if (!deleting) return;
    setBusy(true);
    setError('');
    try {
      if (deleting.type === 'workspace') {
        await api(workspacePath(deleting.id), { method: 'DELETE' });
        if (activeId === deleting.id) {
          setActiveId('');
          setDocuments([]);
          navigate('Workspaces');
        }
        await refreshWorkspaces();
      } else {
        await api(`${workspacePath(activeId)}/documents/${deleting.id}`, { method: 'DELETE' });
        await refreshDocuments();
        await refreshWorkspaces();
      }
      setDeleting(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  if (initializing)
    return (
      <div className="initial-loading">
        <Scale size={40} />
        <Loading text="Opening LegalLens…" />
      </div>
    );
  if (!user)
    return (
      <>
        {error && (
          <div className="connection-error">
            <ErrorNotice message={error} />
          </div>
        )}
        <Auth onAuthenticated={setUser} />
      </>
    );
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      {mobileOpen && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
        <button
          className="brand"
          onClick={() => navigate('Workspaces')}
          aria-label="LegalLens home"
        >
          <span className="brand-icon">
            <Scale size={24} />
          </span>
          LegalLens<span className="brand-dot">.</span>
        </button>
        <button
          className="icon-button mobile-close"
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
        >
          <X size={22} />
        </button>
        <div className="sidebar-caption">YOUR REVIEW DESK</div>
        <nav aria-label="Main navigation">
          {navigation.map(({ name, icon: Icon }) => (
            <button
              key={name}
              aria-current={view === name ? 'page' : undefined}
              className={view === name ? 'active' : ''}
              onClick={() => navigate(name)}
            >
              <Icon size={19} />
              <span>{name}</span>
              {name === 'Documents' && active && (
                <span className="nav-count">{documents.length}</span>
              )}
              {view === name && <span className="nav-active-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-divider" />
        <div className="sidebar-caption">CURRENT WORKSPACE</div>
        {active ? (
          <div className="current-workspace">
            <span className="workspace-letter">{active.name[0]}</span>
            <div>
              <strong>{active.name}</strong>
              <span>{active.is_demo ? 'Synthetic demo' : 'Private workspace'}</span>
            </div>
          </div>
        ) : (
          <p className="sidebar-empty">Choose a workspace to start reviewing your documents.</p>
        )}
        <div className="sidebar-bottom">
          <div className="sidebar-promise">
            <ShieldCheck size={20} />
            <strong>
              Confidence starts
              <br />
              with evidence.
            </strong>
            <p>
              Every insight has a path
              <br />
              back to the source.
            </p>
            <button onClick={() => setPrivacy(true)}>
              Privacy & retention
              <ArrowRight size={13} />
            </button>
          </div>
          <div className="profile">
            <span className="avatar">{user.email.slice(0, 2).toUpperCase()}</span>
            <div>
              <strong>{user.email.split('@')[0]}</strong>
              <span>Personal workspace</span>
            </div>
            <button className="icon-button" onClick={logout} aria-label="Sign out">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={22} />
            </button>
            <span>My review desk</span>
            <span className="breadcrumb-slash">/</span>
            <strong>{view}</strong>
            {active && view !== 'Workspaces' && (
              <>
                <span className="breadcrumb-slash">/</span>
                <span className="breadcrumb-workspace">{active.name}</span>
              </>
            )}
          </div>
          <div className="topbar-right">
            <span className="private-badge">
              <span className="status-dot" />
              Account protected
            </span>
            <button
              className="icon-button"
              aria-label="View privacy and retention information"
              onClick={() => setPrivacy(true)}
            >
              <ShieldCheck size={18} />
            </button>
            <span className="topbar-divider" />
            <span className="avatar small-avatar">{user.email.slice(0, 2).toUpperCase()}</span>
          </div>
        </header>
        <main
          id="main-content"
          className={`main-content ${view === 'Analysis' ? 'analysis-content' : ''}`}
        >
          {active && view !== 'Workspaces' && (
            <div className="workspace-context">
              <button className="text-button muted" onClick={() => navigate('Workspaces')}>
                <ArrowLeft size={14} />
                Workspaces
              </button>
              <label>
                <span className="sr-only">Current workspace</span>
                <select
                  aria-label="Current workspace"
                  value={activeId}
                  onChange={(e) => setActiveId(e.target.value)}
                >
                  {workspaces.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
              {active.is_demo && <span className="demo-label">SYNTHETIC DEMO</span>}
            </div>
          )}
          {error && <ErrorNotice message={error} onDismiss={() => setError('')} />}
          {view === 'Workspaces' ? (
            <WorkspaceHome
              workspaces={workspaces}
              onOpen={openWorkspace}
              onRefresh={refreshWorkspaces}
              onDelete={(w) => setDeleting({ type: 'workspace', id: w.id, name: w.name })}
            />
          ) : !active ? (
            <Empty
              title="Choose the workspace you want to review"
              action={
                <button className="primary" onClick={() => navigate('Workspaces')}>
                  Go to workspaces
                  <ArrowRight size={16} />
                </button>
              }
            >
              Your documents and analysis stay together in isolated workspaces. Create or open one
              to continue.
            </Empty>
          ) : (
            <div key={`${active.id}-${view}`}>
              {view === 'Documents' && (
                <Documents
                  workspace={active}
                  documents={documents}
                  onRefresh={async () => {
                    await refreshDocuments();
                    await refreshWorkspaces();
                  }}
                  onOpen={(d) => {
                    setDocumentId(d.id);
                    navigate('Analysis');
                  }}
                  onDelete={(d) => setDeleting({ type: 'document', id: d.id, name: d.name })}
                />
              )}
              {view === 'Analysis' && (
                <AnalysisView
                  workspace={active}
                  documents={documents}
                  selectedId={documentId}
                  onSelectDocument={setDocumentId}
                  onCitation={setCitation}
                  onGoDocuments={() => navigate('Documents')}
                />
              )}
              {view === 'Compare' && (
                <Compare workspace={active} documents={documents} onCitation={setCitation} />
              )}
              {view === 'Obligations' && (
                <Obligations workspace={active} onCitation={setCitation} />
              )}
              {view === 'Ask' && (
                <Ask
                  workspace={active}
                  documents={documents}
                  onCitation={setCitation}
                  onGoDocuments={() => navigate('Documents')}
                />
              )}
              {view === 'Reports' && <Reports workspace={active} />}
            </div>
          )}
        </main>
        <footer className="app-footer">
          <Disclaimer />
          <span>LegalLens · Evidence before answers.</span>
        </footer>
      </div>
      {citation && active && (
        <CitationDialog
          citation={citation}
          workspaceId={active.id}
          onClose={() => setCitation(null)}
        />
      )}
      {deleting && (
        <Modal title={`Delete ${deleting.type}?`} onClose={() => setDeleting(null)}>
          <div className="delete-icon">
            <Trash2 size={26} />
          </div>
          <p>
            <strong>{deleting.name}</strong> and its associated data will be permanently removed.{' '}
            {deleting.type === 'workspace'
              ? 'This includes all documents, analyses, messages, and generated reports.'
              : 'Related analysis artifacts and reports may also be removed.'}
          </p>
          <p className="muted">This action cannot be undone.</p>
          {error && <ErrorNotice message={error} />}
          <div className="modal-actions">
            <button className="secondary" onClick={() => setDeleting(null)} disabled={busy}>
              Keep {deleting.type}
            </button>
            <button className="danger" onClick={confirmDelete} disabled={busy}>
              {busy ? 'Deleting…' : `Delete ${deleting.type}`}
            </button>
          </div>
        </Modal>
      )}
      {privacy && (
        <Modal title="Your documents, handled with care" onClose={() => setPrivacy(false)}>
          <div className="privacy-copy">
            <ShieldCheck size={28} />
            <h3>Workspace isolation</h3>
            <p>
              Your account can access only its own workspaces. Documents are treated as untrusted
              source evidence, never as instructions.
            </p>
            <h3>Retention & deletion</h3>
            <p>
              Documents and generated artifacts are retained until you explicitly delete the
              document or workspace. Use the deletion controls to remove them from active storage.
              Deployment administrators must configure their own backup retention.
            </p>
            <h3>Model processing</h3>
            <p>
              With a configured AI provider, relevant source excerpts and your question can be sent
              to that provider. If external embeddings are configured, document chunks are sent
              during indexing and questions are sent during retrieval. Provider retention depends on
              your deployment and account settings. The local extraction mode does not send document
              text to a model provider.
            </p>
            <h3>What LegalLens does</h3>
            <Disclaimer />
          </div>
        </Modal>
      )}
    </div>
  );
}
