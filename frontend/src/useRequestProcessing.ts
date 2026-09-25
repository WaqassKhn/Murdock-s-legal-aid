import { useCallback, useRef } from 'react';
import { api, ApiError, errorMessage, workspacePath } from './api';
import type { DocumentRecord } from './types';

/** Resume serverless jobs on a foreground request, never on an assumed background worker. */
export function useRequestProcessing(onError: (message: string) => void) {
  const active = useRef(false);
  const retries = useRef(new Map<string, { after: number; failures: number }>());
  return useCallback(
    (workspaceId: string, documents: DocumentRecord[]) => {
      if (active.current) return;
      const pending = documents.find(
        (document) =>
          document.processing_required &&
          document.job_id &&
          !['ready', 'partially_processed', 'failed'].includes(document.status) &&
          (retries.current.get(document.job_id)?.after ?? 0) <= Date.now(),
      );
      if (!pending) return;
      active.current = true;
      void (async () => {
        try {
          await api(
            `${workspacePath(workspaceId)}/jobs/${encodeURIComponent(pending.job_id)}/process`,
            { method: 'POST' },
          );
          retries.current.set(pending.job_id, { after: Date.now() + 3000, failures: 0 });
        } catch (error) {
          const failures = (retries.current.get(pending.job_id)?.failures ?? 0) + 1;
          const busy = error instanceof ApiError && error.status === 409;
          const permanent = error instanceof ApiError && [401, 403, 404].includes(error.status);
          retries.current.set(pending.job_id, {
            after: permanent
              ? Infinity
              : Date.now() + (busy ? 3000 : Math.min(60000, 5000 * 2 ** Math.min(failures, 4))),
            failures,
          });
          if (!busy)
            onError(
              `${errorMessage(error)} ${permanent ? 'Refresh the page and sign in again to resume processing.' : 'Processing will retry shortly while this workspace is open.'}`,
            );
        } finally {
          active.current = false;
        }
      })();
    },
    [onError],
  );
}
