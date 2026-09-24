import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import {
  AlertCircle,
  ArrowUpRight,
  BookOpen,
  Check,
  FileSearch,
  LoaderCircle,
  ShieldCheck,
  X,
} from 'lucide-react';
import type { Attention, Citation } from './types';

export const DISCLAIMER =
  'LegalLens provides document-based legal information, not legal advice. Laws and outcomes depend on jurisdiction and circumstances. Consult a qualified legal professional before making important decisions. AI-generated results may be incomplete or incorrect.';
export function Disclaimer() {
  return (
    <p className="disclaimer">
      <ShieldCheck size={17} />
      <span>{DISCLAIMER}</span>
    </p>
  );
}
export function Loading({ text = 'Loading your workspace…' }: { text?: string }) {
  return (
    <div role="status" className="loading">
      <LoaderCircle className="spin" size={20} />
      {text}
    </div>
  );
}
export function ErrorNotice({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return (
    <div role="alert" className="notice error">
      <AlertCircle size={19} />
      <span>{message}</span>
      {onDismiss && (
        <button className="icon-button" aria-label="Dismiss error" onClick={onDismiss}>
          <X size={16} />
        </button>
      )}
    </div>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <FileSearch size={30} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function AttentionBadge({ value }: { value: Attention | string }) {
  return (
    <span
      className={`badge attention ${value === 'High attention' ? 'high' : value === 'Review recommended' ? 'review' : value === 'Low attention' ? 'low' : 'neutral'}`}
    >
      {value === 'Low attention' ? <Check size={12} /> : <AlertCircle size={12} />} {value}
    </span>
  );
}
export function Confidence({ value }: { value: number }) {
  return (
    <span
      className="confidence"
      title="An extraction confidence score, not a measure of legal certainty"
    >
      {Math.round(value * 100)}% extraction confidence
    </span>
  );
}
export function Citations({
  items,
  onSelect,
}: {
  items: Citation[];
  onSelect: (citation: Citation) => void;
}) {
  return (
    <div className="citations">
      {items.map((citation, index) => (
        <button
          className="citation"
          key={`${citation.document_id}-${citation.page}-${index}`}
          onClick={() => onSelect(citation)}
          title={citation.excerpt}
        >
          <BookOpen size={13} />
          p. {citation.page} {citation.section && `· ${citation.section}`}
          <ArrowUpRight size={12} />
        </button>
      ))}
    </div>
  );
}
export function HighlightedText({ text, excerpt }: { text: string; excerpt?: string }) {
  if (!excerpt) return <>{text}</>;
  const index = text.toLocaleLowerCase().indexOf(excerpt.toLocaleLowerCase());
  if (index < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <mark data-testid="source-highlight">{text.slice(index, index + excerpt.length)}</mark>
      {text.slice(index + excerpt.length)}
    </>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
    const el = dialog.current;
    return () => el?.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      className={`modal ${wide ? 'wide' : ''}`}
      onCancel={onClose}
      aria-label={title}
      onClick={(e) => {
        if (e.target === dialog.current) onClose();
      }}
    >
      <div className="modal-heading">
        <h2>{title}</h2>
        <button className="icon-button" onClick={onClose} aria-label="Close dialog">
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
