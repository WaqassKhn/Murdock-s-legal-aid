import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useRequestProcessing } from './useRequestProcessing';
import type { DocumentRecord } from './types';

const document = (job: string, status: DocumentRecord['status'] = 'uploaded') =>
  ({
    job_id: job,
    processing_required: true,
    status,
  }) as DocumentRecord;

describe('request-driven processing', () => {
  it('allows one active request across polls and skips terminal jobs', async () => {
    let finish!: (value: Response) => void;
    const fetch = vi.fn<typeof globalThis.fetch>(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    );
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(() => useRequestProcessing(vi.fn()));
    act(() =>
      result.current('a', [document('failed', 'failed'), document('one'), document('two')]),
    );
    act(() => result.current('a', [document('two')]));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toContain('/jobs/one/process');
    await act(async () => finish(new Response('{}')));
    act(() => result.current('a', [document('two')]));
    expect(fetch).toHaveBeenCalledTimes(2);
    await act(async () => finish(new Response('{}')));
    vi.unstubAllGlobals();
  });
  it('backs off transient errors, reports recovery guidance, and treats busy conflicts quietly', async () => {
    const onError = vi.fn();
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response('{}', { status: 503 }))
      .mockResolvedValueOnce(new Response('{}', { status: 409 }))
      .mockResolvedValueOnce(new Response('{}'));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(() => useRequestProcessing(onError));
    await act(async () => result.current('a', [document('one')]));
    act(() => result.current('a', [document('one')]));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(expect.stringContaining('retry'));
    await act(async () => result.current('a', [document('two')]));
    expect(onError).toHaveBeenCalledTimes(1);
    const clock = vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 11000);
    await act(async () => result.current('a', [document('one')]));
    expect(fetch).toHaveBeenCalledTimes(3);
    clock.mockRestore();
    vi.unstubAllGlobals();
  });
});
