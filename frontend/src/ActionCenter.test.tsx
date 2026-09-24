import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Obligations } from './Obligations';
import type { ActionPlan, Workspace } from './types';

const citation = {
  document_id: 'doc-a',
  page: 2,
  section: '4. Notice',
  excerpt: 'The Customer must give 30 days written notice.',
  confidence: 1,
};
const workspace: Workspace = {
  id: 'w-a',
  name: 'Notice review',
  objective: 'Understand notice.',
  jurisdiction: 'Unknown',
  created_at: '2026-09-21T00:00:00Z',
  document_count: 1,
  is_demo: false,
};
const plan: ActionPlan = {
  workspace_id: 'w-a',
  workspace_name: workspace.name,
  objective: workspace.objective,
  responsibilities: [
    {
      id: 'o-a',
      document_id: 'doc-a',
      document_name: 'agreement.txt',
      action: 'Give 30 days written notice.',
      responsible_party: 'Customer',
      trigger: 'Written notice',
      time_window: '30 days after written notice',
      recurrence: 'Once',
      consequence: 'Not specified',
      status: 'open',
      citations: [citation],
      confidence: 1,
      user_action: '',
      user_notes: '',
    },
  ],
  timeline: [
    {
      id: 'o-a',
      document_id: 'doc-a',
      document_name: 'agreement.txt',
      title: 'Give notice',
      expression: '30 days after written notice',
      trigger: 'Written notice',
      calendar_date: null,
      kind: 'relative',
      explanation: 'No calendar date is calculated without a confirmed trigger.',
      status: 'open',
      citations: [citation],
    },
  ],
  open_questions: [],
  lawyer_questions: [],
  negotiation_prompts: [],
  risks: [],
  preparation_evidence: [citation],
  disclaimer: 'Informational material, not legal advice.',
};
afterEach(() => vi.unstubAllGlobals());

describe('editable Action Center', () => {
  it('edits personal planning fields while keeping the original obligation and evidence visible', async () => {
    const user = userEvent.setup();
    const requests: { path: string; body: unknown }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string, options?: RequestInit) => {
        if (options?.method === 'PATCH') {
          const edits = JSON.parse(String(options.body));
          requests.push({ path, body: edits });
          return { ok: true, json: async () => ({ ...plan.responsibilities[0], ...edits }) };
        }
        return { ok: true, json: async () => plan };
      }),
    );
    render(<Obligations workspace={workspace} onCitation={vi.fn()} />);
    await user.click(await screen.findByRole('button', { name: 'Edit personal task' }));
    await user.type(screen.getByLabelText('Your action'), 'Prepare the written notice for review.');
    await user.type(screen.getByLabelText('Your notes'), 'Ask a lawyer about delivery.');
    await user.click(screen.getByRole('button', { name: 'Save personal task' }));
    expect(await screen.findByText('Prepare the written notice for review.')).toBeInTheDocument();
    expect(screen.getByText('Give 30 days written notice.')).toBeInTheDocument();
    expect(requests[0].body).toEqual({
      user_action: 'Prepare the written notice for review.',
      user_notes: 'Ask a lawyer about delivery.',
    });
    expect(screen.getByText('Your action · not source evidence')).toBeInTheDocument();
  });
  it('shows relative windows without inventing calendar dates and resolves timeline evidence', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, json: async () => plan })),
    );
    const onCitation = vi.fn();
    const user = userEvent.setup();
    render(<Obligations workspace={workspace} onCitation={onCitation} />);
    await user.click(await screen.findByRole('tab', { name: 'Timeline' }));
    const event = screen.getByRole('article', { name: 'Timeline: Give notice' });
    expect(within(event).getByText('30 days after written notice')).toBeInTheDocument();
    expect(within(event).getByText('Relative time window')).toBeInTheDocument();
    expect(within(event).getByText(/No calendar date is calculated/)).toBeInTheDocument();
    expect(event.querySelector('time')).toBeNull();
    await user.click(within(event).getByRole('button', { name: /p\. 2/ }));
    expect(onCitation).toHaveBeenCalledWith(citation);
  });
  it('keeps unsaved edits available after a failed save', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_path: string, options?: RequestInit) =>
        options?.method === 'PATCH'
          ? {
              ok: false,
              status: 503,
              json: async () => ({ detail: 'Temporary failure. Retry your save.' }),
            }
          : { ok: true, json: async () => plan },
      ),
    );
    const user = userEvent.setup();
    render(<Obligations workspace={workspace} onCitation={vi.fn()} />);
    await user.click(await screen.findByRole('button', { name: 'Edit personal task' }));
    await user.type(screen.getByLabelText('Your action'), 'My unsaved action');
    await user.click(screen.getByRole('button', { name: 'Save personal task' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Temporary failure');
    expect(screen.getByLabelText('Your action')).toHaveValue('My unsaved action');
  });
});
