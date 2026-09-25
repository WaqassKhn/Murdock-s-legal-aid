import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Documents } from './Documents';
import type { Workspace } from './types';

const workspace: Workspace = {
  id: 'workspace-a',
  name: 'Review',
  objective: '',
  jurisdiction: '',
  created_at: '2026-09-21T00:00:00Z',
  document_count: 0,
  is_demo: false,
};
describe('document ingestion boundaries', () => {
  it('uses server upload limits and explains unavailable OCR', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    render(
      <Documents
        capabilities={{ max_upload_mb: 3, ocr_available: false, request_processing: true }}
        workspace={workspace}
        documents={[]}
        onRefresh={async () => {}}
        onOpen={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/Up to 3 MB each/)).toBeInTheDocument();
    expect(screen.getByText(/Scanned PDFs need OCR/)).toBeInTheDocument();
    await userEvent
      .setup()
      .upload(
        screen.getByLabelText('Upload documents'),
        new File([new Uint8Array(3 * 1024 * 1024 + 1)], 'large.pdf', { type: 'application/pdf' }),
      );
    expect(await screen.findByRole('alert')).toHaveTextContent('exceeds the 3 MB limit');
    expect(fetch).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
  it('prevents uploads until deployment limits are available', () => {
    render(
      <Documents
        capabilities={null}
        workspace={workspace}
        documents={[]}
        onRefresh={async () => {}}
        onOpen={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByLabelText('Upload documents')).toBeDisabled();
  });

  it('reports an unsupported file before submitting and keeps the library empty', async () => {
    const refresh = vi.fn(async () => {});
    const user = userEvent.setup({ applyAccept: false });
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    render(
      <Documents
        capabilities={{ max_upload_mb: 20, ocr_available: true, request_processing: false }}
        workspace={workspace}
        documents={[]}
        onRefresh={refresh}
        onOpen={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    await user.upload(
      screen.getByLabelText('Upload documents'),
      new File(['malicious'], 'contract.exe', { type: 'application/octet-stream' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('unsupported format');
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByText('Your evidence starts with a document')).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
  it('makes a partial extraction visible and includes the affected-page warning', () => {
    render(
      <Documents
        capabilities={{ max_upload_mb: 20, ocr_available: true, request_processing: false }}
        workspace={workspace}
        documents={[
          {
            id: 'doc-a',
            workspace_id: workspace.id,
            name: 'scan.pdf',
            status: 'partially_processed',
            media_type: 'application/pdf',
            page_count: 3,
            warnings: ['Page 2: OCR confidence is low.'],
            created_at: workspace.created_at,
            version: 1,
            job_id: 'job-a',
          },
        ]}
        onRefresh={async () => {}}
        onOpen={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText('Partially Processed')).toBeInTheDocument();
    expect(screen.getByText('Page 2: OCR confidence is low.')).toBeInTheDocument();
  });
});
