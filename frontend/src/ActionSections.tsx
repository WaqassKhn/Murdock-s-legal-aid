import { CalendarDays, Check, ShieldAlert } from 'lucide-react';
import { Citations, Empty } from './components';
import type { ActionQuestion, Citation, TimelineEvent } from './types';

export function Timeline({
  events,
  onCitation,
}: {
  events: TimelineEvent[];
  onCitation: (citation: Citation) => void;
}) {
  const dated = events.filter((event) => event.calendar_date !== null);
  const relative = events.filter((event) => event.calendar_date === null);
  return (
    <section className="action-timeline">
      <div className="section-heading">
        <div>
          <h2>Dates & time windows</h2>
          <p className="field-hint">
            Explicit dates are ordered chronologically. Relative windows remain unplaced until their
            trigger is confirmed.
          </p>
        </div>
        <CalendarDays size={24} />
      </div>
      {!events.length ? (
        <Empty title="No supported time windows extracted">
          Check your document for missing dates, deadlines, or notice requirements. No calendar
          dates have been assumed.
        </Empty>
      ) : (
        <>
          {dated.length > 0 && (
            <TimelineGroup
              title="Dates stated in the document"
              events={dated}
              onCitation={onCitation}
            />
          )}{' '}
          {relative.length > 0 && (
            <TimelineGroup
              title="Relative or unclear windows · date not calculated"
              events={relative}
              onCitation={onCitation}
            />
          )}
        </>
      )}
      <div className="info-strip">
        <strong>Before you act on a deadline</strong>
        <span>
          Confirm the trigger date, notice method, time zone, and whether the document counts
          calendar or business days. Seek professional guidance for an urgent legal deadline.
        </span>
      </div>
    </section>
  );
}
function TimelineGroup({
  title,
  events,
  onCitation,
}: {
  title: string;
  events: TimelineEvent[];
  onCitation: (citation: Citation) => void;
}) {
  return (
    <div className="timeline-group">
      <h3>{title}</h3>
      <div className="timeline-events">
        {events.map((event) => (
          <article
            className="timeline-event"
            key={event.id}
            aria-label={`Timeline: ${event.title}`}
          >
            <span className="timeline-node">
              <CalendarDays size={16} />
            </span>
            <div className="timeline-event-main">
              <div className="timeline-top">
                <span className={`badge ${event.kind === 'dated' ? 'low' : 'neutral'}`}>
                  {event.kind === 'dated'
                    ? 'Explicit source date'
                    : event.kind === 'relative'
                      ? 'Relative time window'
                      : 'Date needs clarification'}
                </span>
                {event.status === 'complete' && (
                  <span className="badge low">
                    <Check size={12} />
                    Marked complete
                  </span>
                )}
              </div>
              <h4>{event.title}</h4>
              {event.calendar_date ? (
                <time dateTime={event.calendar_date}>{event.expression}</time>
              ) : (
                <strong className="timeline-expression">{event.expression}</strong>
              )}
              <p className="timeline-trigger">Trigger: {event.trigger || 'Not specified'}</p>
              <p className="timeline-limitation">{event.explanation}</p>
              <Citations items={event.citations} onSelect={onCitation} />
              <span className="cell-sub">{event.document_name}</span>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
export function QuestionList({
  title,
  introduction,
  items,
  onCitation,
}: {
  title: string;
  introduction: string;
  items: ActionQuestion[];
  onCitation: (citation: Citation) => void;
}) {
  return (
    <section className="panel action-question-section">
      <div className="section-heading">
        <h2>{title}</h2>
        <ShieldAlert size={21} />
      </div>
      <p className="muted">{introduction}</p>
      {items.length ? (
        items.map((item) => (
          <article className="action-question" key={`${item.document_id}-${item.id}`}>
            <h3>{item.question}</h3>
            <p>{item.reason}</p>
            <Citations items={item.citations} onSelect={onCitation} />
            {item.citations.length === 0 && (
              <span className="field-hint">
                A preparation question about missing information; no supporting passage was located.
              </span>
            )}
          </article>
        ))
      ) : (
        <p className="field-hint">
          No questions identified here yet. This does not establish that all terms are clear.
        </p>
      )}
    </section>
  );
}
