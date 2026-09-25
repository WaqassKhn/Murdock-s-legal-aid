import { useEffect, useState } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  CircleDot,
  FileText,
  GitBranch,
  Layers3,
  ListChecks,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';
import { api, errorMessage, label, workspacePath } from './api';
import { AttentionBadge, Citations, Confidence, Empty, ErrorNotice, Loading } from './components';
import { PageViewer } from './SourceViewer';
import type { Citation, Clause, DocumentDetail, DocumentRecord, Risk, Workspace } from './types';

type Tab = 'Overview' | 'Clauses' | 'Review findings' | 'Evidence Map';
export function AnalysisView({
  workspace,
  documents,
  selectedId,
  onSelectDocument,
  onCitation,
  onGoDocuments,
}: {
  workspace: Workspace;
  documents: DocumentRecord[];
  selectedId: string;
  onSelectDocument: (id: string) => void;
  onCitation: (citation: Citation) => void;
  onGoDocuments: () => void;
}) {
  const [detail, setDetail] = useState<DocumentDetail | null>(null),
    [tab, setTab] = useState<Tab>('Overview'),
    [clauseId, setClauseId] = useState(''),
    [page, setPage] = useState(1),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const status = documents.find((d) => d.id === selectedId)?.status;
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    setDetail(null);
    setError('');
    api<DocumentDetail>(`${workspacePath(workspace.id)}/documents/${selectedId}`)
      .then((d) => {
        if (!cancelled) {
          setDetail(d);
          setPage(1);
          setClauseId(d.analysis?.clauses[0]?.id || '');
        }
      })
      .catch((e) => {
        if (!cancelled) setError(errorMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, workspace.id, status]);
  const clause =
    detail?.analysis?.clauses.find((c) => c.id === clauseId) || detail?.analysis?.clauses[0];
  function selectClause(c: Clause) {
    setClauseId(c.id);
    if (c.citations[0]) setPage(c.citations[0].page);
  }
  async function reanalyze() {
    if (!detail) return;
    setBusy(true);
    setError('');
    try {
      await api(`${workspacePath(workspace.id)}/documents/${detail.id}/analyze`, {
        method: 'POST',
      });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  if (!documents.length)
    return (
      <Empty
        title="There is nothing to analyze yet"
        action={
          <button className="primary" onClick={onGoDocuments}>
            Add your first document
            <ArrowRight size={16} />
          </button>
        }
      >
        Upload a document to see its structure, clauses, obligations, and source evidence.
      </Empty>
    );
  return (
    <>
      <div className="page-heading compact">
        <div>
          <div className="eyebrow">READ WITH UNDERSTANDING</div>
          <h1>Document analysis</h1>
          <p>Source facts, plain-language interpretation, and a path back to the page.</p>
        </div>
        <label className="inline-label">
          Document
          <select value={selectedId} onChange={(e) => onSelectDocument(e.target.value)}>
            {documents.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <ErrorNotice message={error} />}{' '}
      {!detail && !error ? (
        <Loading text="Loading source pages and analysis…" />
      ) : (
        detail && (
          <>
            {detail.warnings.length > 0 && (
              <div className="notice warning">
                <ShieldAlert size={18} />
                <div>
                  <strong>Processing needs attention</strong>
                  <p>{detail.warnings.join(' ')}</p>
                </div>
              </div>
            )}
            {!detail.analysis ? (
              <Empty
                title={
                  detail.status === 'failed'
                    ? 'This document could not be processed'
                    : 'Your analysis is being prepared'
                }
                action={
                  <button className="secondary" onClick={reanalyze} disabled={busy}>
                    <RefreshCw size={16} />
                    Retry analysis
                  </button>
                }
              >
                Current status: {label(detail.status)}. Documents with poor extraction may need a
                clearer source file.
              </Empty>
            ) : (
              <>
                <div className="analysis-meta">
                  <span>
                    <FileText size={15} />
                    {detail.name}
                  </span>
                  <span>{detail.page_count} pages</span>
                  <span>Version {detail.version}</span>
                  <span className="mode-badge">{detail.analysis.mode}</span>
                  <button
                    className="secondary"
                    onClick={reanalyze}
                    disabled={
                      busy || !['ready', 'partially_processed', 'failed'].includes(detail.status)
                    }
                  >
                    <RefreshCw size={16} />
                    {['uploaded', 'extracting', 'indexing', 'analyzing'].includes(detail.status)
                      ? 'Analysis in progress…'
                      : 'Reanalyze document'}
                  </button>
                </div>
                <div className="tabs" role="tablist" aria-label="Analysis sections">
                  {(['Overview', 'Clauses', 'Review findings', 'Evidence Map'] as Tab[]).map(
                    (t) => (
                      <button
                        key={t}
                        role="tab"
                        aria-selected={tab === t}
                        onClick={() => setTab(t)}
                      >
                        {t}
                        {t === 'Review findings' && (
                          <span className="count">{detail.analysis!.risks.length}</span>
                        )}
                        {t === 'Evidence Map' && <GitBranch size={14} />}
                      </button>
                    ),
                  )}
                </div>
                {tab === 'Overview' && (
                  <div className="overview-grid">
                    <div>
                      <section className="panel summary-panel">
                        <div className="eyebrow">
                          <CircleDot size={14} /> SYSTEM INTERPRETATION
                        </div>
                        <h2>The document, in plain language.</h2>
                        <p>{detail.analysis.summary}</p>
                        {!!detail.analysis.summary_citations?.length && (
                          <Citations
                            items={detail.analysis.summary_citations}
                            onSelect={onCitation}
                          />
                        )}
                        <div className="meaning">
                          <strong>What this means for you</strong>
                          <p>{detail.analysis.meaning}</p>
                          {!!detail.analysis.meaning_citations?.length && (
                            <Citations
                              items={detail.analysis.meaning_citations}
                              onSelect={onCitation}
                            />
                          )}
                        </div>
                        <p className="field-hint">
                          Interpretations explain the cited document evidence. Review the exact
                          wording before relying on them.
                        </p>
                      </section>
                      <section className="panel metadata-panel">
                        <div className="section-heading">
                          <h2>What the document says</h2>
                          <span className="eyebrow">DOCUMENT FACTS</span>
                        </div>
                        <div className="metadata-grid">
                          {Object.entries(detail.analysis.metadata).map(([key, field]) => (
                            <div className="metadata-field" key={key}>
                              <span>{label(key)}</span>
                              <p className={field.value === 'Not found' ? 'not-found' : ''}>
                                {field.value}
                              </p>
                              {field.citations.length > 0 && (
                                <>
                                  <Citations items={field.citations} onSelect={onCitation} />
                                  <Confidence value={field.confidence} />
                                </>
                              )}
                            </div>
                          ))}
                        </div>
                      </section>
                    </div>
                    <aside>
                      <section className="panel review-summary">
                        <span className="section-icon">
                          <ShieldAlert size={22} />
                        </span>
                        <h3>Worth a closer look</h3>
                        <p className="muted">
                          Patterns to clarify, not conclusions about legality.
                        </p>
                        <div className="review-number">
                          {detail.analysis.risks.length}
                          <span>review findings</span>
                        </div>
                        {detail.analysis.risks.slice(0, 3).map((r) => (
                          <div className="mini-risk" key={r.id}>
                            <AttentionBadge value={r.severity} />
                            <p>{r.finding}</p>
                          </div>
                        ))}
                        <button className="text-button" onClick={() => setTab('Review findings')}>
                          Explore review findings
                          <ArrowUpRight size={16} />
                        </button>
                      </section>
                      <section className="panel mini-evidence">
                        <GitBranch size={23} />
                        <h3>Nothing without a source.</h3>
                        <p>Follow a clause through its obligations and supporting page.</p>
                        <button className="text-button" onClick={() => setTab('Evidence Map')}>
                          Open Evidence Map
                          <ArrowRight size={16} />
                        </button>
                      </section>
                    </aside>
                  </div>
                )}
                {tab === 'Clauses' && (
                  <div className="clause-workbench">
                    <PageViewer
                      pages={detail.pages}
                      pageNumber={page}
                      onPageChange={setPage}
                      excerpt={clause?.citations.find((c) => c.page === page)?.excerpt}
                    />
                    <section className="clause-selector">
                      <div className="column-title">
                        <Layers3 size={16} />
                        Clauses <span className="count">{detail.analysis.clauses.length}</span>
                      </div>
                      {detail.analysis.clauses.length === 0 ? (
                        <p className="muted">No clauses identified.</p>
                      ) : (
                        detail.analysis.clauses.map((c) => (
                          <button
                            key={c.id}
                            className={`clause-option ${clause?.id === c.id ? 'active' : ''}`}
                            onClick={() => selectClause(c)}
                          >
                            <span>{label(c.clause_type)}</span>
                            <small>
                              {c.citations[0]?.section || 'Unnumbered section'} · p.{' '}
                              {c.citations[0]?.page}
                            </small>
                            <AttentionBadge value={c.attention} />
                          </button>
                        ))
                      )}
                    </section>
                    <section className="clause-detail">
                      {clause && (
                        <>
                          <div className="eyebrow">SYSTEM INTERPRETATION</div>
                          <h2>{label(clause.clause_type)}</h2>
                          <AttentionBadge value={clause.attention} />
                          <p>{clause.explanation}</p>
                          {clause.risk_reason && (
                            <div className="next-step">
                              <strong>Why this attention level?</strong>
                              <p>{clause.risk_reason}</p>
                            </div>
                          )}
                          {clause.lawyer_question && (
                            <div className="lawyer-question">
                              <strong>Ask a lawyer</strong>
                              <p>{clause.lawyer_question}</p>
                            </div>
                          )}
                          <div className="original-clause">
                            <span className="eyebrow">ORIGINAL CLAUSE · DOCUMENT FACT</span>
                            <blockquote>{clause.original}</blockquote>
                          </div>
                          <ClauseItems title="Parties affected" items={clause.affected_parties} />
                          <ClauseItems title="Rights created" items={clause.rights} />
                          <ClauseItems title="Obligations created" items={clause.obligations} />
                          <ClauseItems title="Deadlines & time windows" items={clause.deadlines} />
                          <ClauseItems
                            title="Financial exposure"
                            items={clause.financial_exposure}
                          />
                          <ClauseItems title="Missing or ambiguous" items={clause.ambiguities} />
                          <Citations items={clause.citations} onSelect={onCitation} />
                          <Confidence value={clause.confidence} />
                        </>
                      )}
                    </section>
                  </div>
                )}
                {tab === 'Review findings' &&
                  (detail.analysis.risks.length === 0 ? (
                    <Empty title="No review patterns identified">
                      This does not mean the document is risk-free. Review the clauses and discuss
                      material questions with a qualified lawyer.
                    </Empty>
                  ) : (
                    <div className="risk-grid">
                      {detail.analysis.risks.map((r) => (
                        <article key={r.id} className="panel risk-card">
                          <AttentionBadge value={r.severity} />
                          <h3>
                            {r.citations.length ? (
                              <button
                                className="risk-evidence-title"
                                onClick={() => onCitation(r.citations[0])}
                              >
                                {r.finding}
                                <ArrowUpRight size={16} />
                              </button>
                            ) : (
                              r.finding
                            )}
                          </h3>
                          <p>{r.why_it_matters}</p>
                          <div className="risk-party">
                            <strong>Affected party</strong>
                            <span>{r.affected_party}</span>
                          </div>
                          <div className="next-step">
                            <span className="eyebrow">SUGGESTED NEXT STEP</span>
                            <p>{r.suggested_clarification}</p>
                          </div>
                          <div className="lawyer-question">
                            <strong>Ask a lawyer</strong>
                            <p>{r.lawyer_question}</p>
                          </div>
                          <Citations items={r.citations} onSelect={onCitation} />
                          <Confidence value={r.confidence} />
                        </article>
                      ))}
                    </div>
                  ))}
                {tab === 'Evidence Map' && (
                  <EvidenceMap
                    clauses={detail.analysis.clauses}
                    risks={detail.analysis.risks}
                    onCitation={onCitation}
                  />
                )}
              </>
            )}
          </>
        )
      )}
    </>
  );
}
function ClauseItems({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="clause-items">
      <h4>{title}</h4>
      {items.length ? (
        <ul>
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="muted small">Not explicitly identified</p>
      )}
    </div>
  );
}
function EvidenceMap({
  clauses,
  risks,
  onCitation,
}: {
  clauses: Clause[];
  risks: Risk[];
  onCitation: (c: Citation) => void;
}) {
  const [selected, setSelected] = useState(clauses[0]?.id || '');
  const clause = clauses.find((c) => c.id === selected) || clauses[0];
  if (!clause)
    return (
      <Empty title="No evidence relationships to display">
        An extracted clause and its citation are required to build an evidence path.
      </Empty>
    );
  const relatedRisks = risks.filter((r) =>
    r.citations.some((c) =>
      clause.citations.some(
        (cc) => c.document_id === cc.document_id && c.page === cc.page && c.section === cc.section,
      ),
    ),
  );
  const branches = [
    ...clause.affected_parties.map((t) => ({ kind: 'Party', text: t })),
    ...clause.rights.map((t) => ({ kind: 'Right', text: t })),
    ...clause.obligations.map((t) => ({ kind: 'Obligation', text: t })),
    ...clause.deadlines.map((t) => ({ kind: 'Date / time window', text: t })),
    ...clause.financial_exposure.map((t) => ({ kind: 'Amount / exposure', text: t })),
    ...(clause.defined_terms || []).map((t) => ({
      kind: 'Defined term',
      text: `${t.term}: ${t.definition}`,
    })),
    ...clause.ambiguities.map((t) => ({ kind: 'Ambiguity', text: t })),
    ...relatedRisks.map((r) => ({ kind: 'Review finding', text: r.finding })),
  ];
  return (
    <section className="panel evidence-map">
      <div className="section-heading">
        <div>
          <div className="eyebrow">THE REASONING, MADE VISIBLE</div>
          <h2>Follow the evidence.</h2>
          <p className="muted">
            Select a clause to trace its findings to the words that support them.
          </p>
        </div>
        <label className="inline-label">
          Explore clause
          <select value={clause.id} onChange={(e) => setSelected(e.target.value)}>
            {clauses.map((c) => (
              <option key={c.id} value={c.id}>
                {label(c.clause_type)} · {c.citations[0]?.section}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="map-canvas">
        <div className="map-column source-nodes">
          <div className="map-column-label">01 · SUPPORTING PAGE</div>
          {clause.citations.map((c, i) => (
            <button className="map-node source-node" key={i} onClick={() => onCitation(c)}>
              <span>
                <FileText size={16} />
                Page {c.page} · {c.section}
              </span>
              <blockquote>“{c.excerpt}”</blockquote>
              <small>
                Inspect source <ArrowUpRight size={13} />
              </small>
            </button>
          ))}
        </div>
        <div className="map-edge" aria-hidden="true">
          <ArrowRight size={22} />
        </div>
        <div className="map-column">
          <div className="map-column-label">02 · CLAUSE</div>
          <button
            className="map-node central-node"
            onClick={() => clause.citations[0] && onCitation(clause.citations[0])}
          >
            <Layers3 size={24} />
            <h3>{label(clause.clause_type)}</h3>
            <p>{clause.explanation}</p>
            <AttentionBadge value={clause.attention} />
          </button>
          <div className="map-key">
            <CircleDot size={13} />
            System interpretation
          </div>
        </div>
        <div className="map-edge" aria-hidden="true">
          <ArrowRight size={22} />
        </div>
        <div className="map-column outcome-nodes">
          <div className="map-column-label">03 · CONNECTED FINDINGS</div>
          {branches.length ? (
            branches.map((b, i) => (
              <button
                key={i}
                className="map-node outcome-node"
                onClick={() => clause.citations[0] && onCitation(clause.citations[0])}
              >
                <span>
                  <ListChecks size={14} />
                  {b.kind}
                </span>
                <p>{b.text}</p>
              </button>
            ))
          ) : (
            <div className="map-node">
              <p>No additional relationships extracted.</p>
            </div>
          )}
        </div>
      </div>
      <p className="field-hint">
        Connections are based on the selected clause and matching source citations. Select any node
        to inspect its evidence. This map describes document relationships, not legal certainty.
      </p>
    </section>
  );
}
