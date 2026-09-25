import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HighlightedText } from './components';
import { PageViewer } from './SourceViewer';
import { AnswerCard } from './Ask';
import type { Answer } from './types';

describe('evidence rendering', () => {
  it('identifies generated answers as interpretation and shows the actual provider mode', () => {
    const answer: Answer = {
      direct_answer: 'You need to give advance written notice to end the agreement.',
      explanation: 'The notice clause describes a written notice requirement.',
      citations: [],
      excerpts: [],
      missing_information: [],
      confidence: 0.8,
      follow_up_questions: [],
      category: 'System interpretation',
      abstained: false,
      mode: 'AI-generated answer · evidence checked',
      answer_type: 'interpreted',
    };
    render(<AnswerCard answer={answer} onCitation={vi.fn()} onFollowUp={vi.fn()} />);
    expect(screen.getByText(answer.mode)).toBeInTheDocument();
    expect(screen.getAllByText('System interpretation').length).toBeGreaterThan(0);
    expect(screen.queryByText('Explicit document statement')).not.toBeInTheDocument();
  });
  it('makes answer provenance and a verification step visible alongside source excerpts', () => {
    const answer = {
      direct_answer: 'The Customer must give 30 days written notice.',
      explanation: '',
      citations: [],
      excerpts: [],
      missing_information: [],
      confidence: 0.9,
      follow_up_questions: [],
      category: 'Document facts',
      abstained: false,
      mode: 'extractive',
      answer_type: 'explicit',
      confidence_label: 'high',
      verification_step: 'Confirm the notice delivery method.',
      relevant_clauses: [],
    } as Answer;
    render(<AnswerCard answer={answer} onCitation={vi.fn()} onFollowUp={vi.fn()} />);
    expect(screen.getByText('Explicit document statement')).toBeInTheDocument();
    expect(screen.getByText('Confirm the notice delivery method.')).toBeInTheDocument();
  });
  it('highlights only the exact supporting excerpt and never interprets document HTML', () => {
    render(
      <div data-testid="source">
        <HighlightedText
          text={'Notice: 30 days. <script>steal()</script> Nothing else.'}
          excerpt="30 days"
        />
      </div>,
    );
    expect(screen.getByTestId('source-highlight')).toHaveTextContent('30 days');
    expect(screen.getByTestId('source').querySelector('script')).toBeNull();
    expect(screen.getByTestId('source')).toHaveTextContent('<script>steal()</script>');
  });
  it('does not invent a highlight when the excerpt is not present', () => {
    render(<HighlightedText text="Thirty days after notice." excerpt="May 10, 2027" />);
    expect(screen.queryByTestId('source-highlight')).not.toBeInTheDocument();
    expect(screen.getByText('Thirty days after notice.')).toBeInTheDocument();
  });
  it('shows the cited page, extraction warning and excerpt, and supports page navigation', async () => {
    const onPage = vi.fn();
    render(
      <PageViewer
        pages={[
          { number: 1, text: 'Original title', quality: 1, ocr: false, blocks: [] },
          {
            number: 2,
            text: 'The rent is USD 900 monthly.',
            quality: 0.4,
            ocr: true,
            warning: 'Low-confidence extraction',
            blocks: [],
          },
        ]}
        pageNumber={2}
        onPageChange={onPage}
        excerpt="USD 900"
      />,
    );
    expect(screen.queryByText('Original title')).not.toBeInTheDocument();
    expect(screen.getByText('Page 2: Low-confidence extraction')).toBeInTheDocument();
    expect(screen.getByTestId('source-highlight')).toHaveTextContent('USD 900');
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Previous page' }));
    expect(onPage).toHaveBeenCalledWith(1);
  });
  it('shows abstention and missing information without fabricating document evidence', () => {
    const answer: Answer = {
      direct_answer:
        'I could not find enough information in the uploaded documents to answer this reliably.',
      explanation: 'No source addresses the question.',
      citations: [],
      excerpts: [],
      missing_information: ['The agreement does not mention taxes.'],
      confidence: 0,
      follow_up_questions: ['Which payment terms are stated?'],
      category: 'document_only',
      abstained: true,
      mode: 'extractive',
    };
    render(<AnswerCard answer={answer} onCitation={vi.fn()} onFollowUp={vi.fn()} />);
    expect(screen.getByText(answer.direct_answer)).toBeInTheDocument();
    expect(screen.getByText('Insufficient document evidence')).toBeInTheDocument();
    expect(screen.getByText('The agreement does not mention taxes.')).toBeInTheDocument();
    expect(screen.queryByText('DOCUMENT EVIDENCE')).not.toBeInTheDocument();
  });
});
