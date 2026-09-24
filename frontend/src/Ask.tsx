import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import {
  ArrowRight,
  BookOpen,
  CircleHelp,
  CornerDownRight,
  Send,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { api, errorMessage, json, label, workspacePath } from './api';
import { Citations, Confidence, Empty, ErrorNotice, Loading } from './components';
import type { Answer, Citation, DocumentRecord, Workspace } from './types';

const suggestions = [
  'Can I terminate this agreement early?',
  'Who owns the work produced?',
  'Is there an automatic renewal?',
  'What happens if payment is late?',
  'Which obligations continue after termination?',
  'What should I clarify with a lawyer?',
];
export function AnswerCard({
  answer,
  onCitation,
  onFollowUp,
}: {
  answer: Answer;
  onCitation: (c: Citation) => void;
  onFollowUp: (q: string) => void;
}) {
  return (
    <article className={`answer-card ${answer.abstained ? 'abstained' : ''}`}>
      <div className="answer-heading">
        <span className="answer-symbol">
          {answer.abstained ? <CircleHelp size={21} /> : <Sparkles size={21} />}
        </span>
        <div>
          <strong>LegalLens</strong>
          <span>
            {answer.abstained
              ? 'Insufficient document evidence'
              : answer.category === 'General legal information'
                ? 'General legal information'
                : 'Document-grounded response'}
          </span>
        </div>
        <span className="mode-badge">{label(answer.mode)}</span>
      </div>
      <h3>{answer.direct_answer}</h3>
      {answer.answer_type && (
        <div className="answer-provenance">
          <span className="badge neutral">
            {answer.answer_type === 'explicit'
              ? 'Explicit document statement'
              : answer.answer_type === 'interpreted'
                ? 'System interpretation'
                : 'Not found in the documents'}
          </span>
          {answer.confidence_label && (
            <span className="small muted">
              {label(answer.confidence_label)} evidence confidence
            </span>
          )}
        </div>
      )}
      {answer.explanation && (
        <div className="answer-explanation">
          <span className="eyebrow">SYSTEM INTERPRETATION</span>
          <p>{answer.explanation}</p>
        </div>
      )}
      {answer.citations.length > 0 && (
        <details className="answer-evidence" open>
          <summary className="eyebrow">
            <BookOpen size={14} /> DOCUMENT EVIDENCE{' '}
            <span>
              {' '}
              · {answer.citations.length} {answer.citations.length === 1 ? 'source' : 'sources'} ·
              expand / collapse
            </span>
          </summary>
          {answer.citations.map((c, i) => (
            <div key={i} className="answer-quote">
              <blockquote>“{c.excerpt}”</blockquote>
              <Citations items={[c]} onSelect={onCitation} />
            </div>
          ))}
        </details>
      )}
      {answer.missing_information.length > 0 && (
        <div className="missing-information">
          <strong>Assumptions & missing information</strong>
          <ul>
            {answer.missing_information.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      <Confidence value={answer.confidence} />
      {answer.verification_step && (
        <div className="next-step">
          <span className="eyebrow">RECOMMENDED VERIFICATION</span>
          <p>{answer.verification_step}</p>
        </div>
      )}
      {answer.follow_up_questions.length > 0 && (
        <div className="followups">
          <span className="eyebrow">SUGGESTED NEXT QUESTIONS</span>
          {answer.follow_up_questions.map((q, i) => (
            <button className="followup" onClick={() => onFollowUp(q)} key={i}>
              <CornerDownRight size={15} />
              {q}
              <ArrowRight size={14} />
            </button>
          ))}
        </div>
      )}
    </article>
  );
}
export function Ask({
  workspace,
  documents,
  onCitation,
  onGoDocuments,
}: {
  workspace: Workspace;
  documents: DocumentRecord[];
  onCitation: (c: Citation) => void;
  onGoDocuments: () => void;
}) {
  const [question, setQuestion] = useState(''),
    [scope, setScope] = useState('all'),
    [jurisdiction, setJurisdiction] = useState(workspace.jurisdiction || ''),
    [history, setHistory] = useState<{ question: string; answer: Answer }[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const input = useRef<HTMLTextAreaElement>(null);
  async function ask(event?: FormEvent) {
    event?.preventDefault();
    if (!question.trim() || busy) return;
    const submitted = question.trim();
    setBusy(true);
    setError('');
    try {
      const answer = await api<Answer>(`${workspacePath(workspace.id)}/ask`, {
        method: 'POST',
        body: json({
          question: submitted,
          document_ids: scope === 'all' ? undefined : [scope],
          jurisdiction: jurisdiction || undefined,
        }),
      });
      setHistory((h) => [...h, { question: submitted, answer }]);
      setQuestion('');
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  function followup(q: string) {
    setQuestion(q);
    input.current?.focus();
  }
  if (!documents.length)
    return (
      <Empty
        title="Bring a document. Ask a better question."
        action={
          <button className="primary" onClick={onGoDocuments}>
            Upload a document
            <ArrowRight size={16} />
          </button>
        }
      >
        Answers will be grounded in the sources you upload. Add your first document to get started.
      </Empty>
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ANSWERS YOU CAN TRACE</div>
          <h1>Ask your documents.</h1>
          <p>Understand the terms, with the evidence beside every answer.</p>
        </div>
        <span className="grounded-tag">
          <ShieldCheck size={16} />
          Evidence-grounded
        </span>
      </div>
      <div className="ask-layout">
        <div className="ask-main">
          {history.length === 0 ? (
            <section className="panel ask-welcome">
              <span className="ask-icon">
                <Sparkles size={26} />
              </span>
              <h2>What would you like to understand?</h2>
              <p className="muted">
                Start with a question about your documents. When the evidence is missing, we will
                say so.
              </p>
              <div className="suggestion-grid">
                {suggestions.map((q) => (
                  <button key={q} onClick={() => followup(q)}>
                    {q}
                    <ArrowUpRightIcon />
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <div className="answer-history">
              {history.map((entry, i) => (
                <div key={i}>
                  <div className="user-question">
                    <span>YOUR QUESTION</span>
                    <p>{entry.question}</p>
                  </div>
                  <AnswerCard answer={entry.answer} onCitation={onCitation} onFollowUp={followup} />
                </div>
              ))}
            </div>
          )}
          {busy && <Loading text="Retrieving clauses and verifying source evidence…" />}
          {error && <ErrorNotice message={error} onDismiss={() => setError('')} />}
          <form className="question-composer" onSubmit={ask}>
            <label className="sr-only" htmlFor="question">
              Your question
            </label>
            <textarea
              id="question"
              ref={input}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="Ask about a clause, an obligation, or something that feels unclear…"
              required
            />
            <div className="composer-footer">
              <span>
                <BookOpen size={14} />
                {scope === 'all' ? `${documents.length} documents in scope` : '1 document in scope'}
              </span>
              <button className="primary" disabled={busy || !question.trim()} type="submit">
                {busy ? 'Reviewing…' : 'Ask question'}
                <Send size={16} />
              </button>
            </div>
          </form>
          <p className="field-hint">
            Questions and responses may be retained in workspace history. Do not include information
            you do not want stored.
          </p>
        </div>
        <aside className="ask-aside">
          <section className="panel">
            <div className="eyebrow">REVIEW CONTEXT</div>
            <h3>Keep the scope clear.</h3>
            <label>
              Document scope
              <select value={scope} onChange={(e) => setScope(e.target.value)}>
                <option value="all">All workspace documents</option>
                {documents.map((d) => (
                  <option value={d.id} key={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Jurisdiction
              <input
                value={jurisdiction}
                maxLength={100}
                onChange={(e) => setJurisdiction(e.target.value)}
                placeholder="Not confirmed"
              />
            </label>
            <p className="field-hint">
              Confirm the governing law before requesting general legal information. We never infer
              it from your location.
            </p>
            <div className="info-note">
              <ShieldCheck size={18} />
              <p>
                This release answers from your documents. External legal research is unavailable;
                jurisdiction-dependent legal rules are not supplied from model memory.
              </p>
            </div>
          </section>
          <section className="evidence-legend">
            <h4>Know what you’re reading</h4>
            <p>
              <span className="legend-dot fact" />
              <strong>Document facts</strong>
              <br />
              Words directly supported by the source.
            </p>
            <p>
              <span className="legend-dot interpretation" />
              <strong>System interpretation</strong>
              <br />
              An explanation to independently review.
            </p>
            <p>
              <span className="legend-dot next" />
              <strong>Suggested next steps</strong>
              <br />
              Practical questions, not legal instructions.
            </p>
          </section>
        </aside>
      </div>
    </>
  );
}
function ArrowUpRightIcon() {
  return <ArrowRight size={15} />;
}
