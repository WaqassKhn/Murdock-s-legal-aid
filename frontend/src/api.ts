declare const __TEMPORARY_SESSION__: boolean;
export const temporarySession = __TEMPORARY_SESSION__;
let sessionState = '';
let sessionQueue: Promise<unknown> = Promise.resolve();

function base64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  }
  return btoa(binary);
}

/** Serialize mutations so concurrent UI refreshes cannot overwrite session state. */
export function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  if (!temporarySession) return fetch(path, options);
  const run = sessionQueue.then(async () => {
    const request = new Request(new URL(path, window.location.origin), options);
    const bytes = new Uint8Array(await request.arrayBuffer());
    const body = JSON.stringify({
      path,
      method: request.method,
      content_type: request.headers.get('Content-Type') || 'application/json',
      body: base64(bytes),
      state: sessionState,
    });
    if (new TextEncoder().encode(body).length > 4_000_000) {
      throw new Error(
        'Temporary session request is too large. Delete documents or upload a smaller file.',
      );
    }
    const response = await fetch('/api/session', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body,
    });
    if (!response.ok) return response;
    const envelope = await response.json();
    sessionState = envelope.state;
    const decoded = Uint8Array.from(atob(envelope.body), (c) => c.charCodeAt(0));
    return new Response(envelope.status === 204 ? null : decoded, {
      status: envelope.status,
      headers: envelope.headers,
    });
  });
  sessionQueue = run.catch(() => undefined);
  return run;
}

export async function downloadFile(path: string, name: string): Promise<void> {
  const response = await apiFetch(path, { credentials: 'include' });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || 'Download failed. Please retry.');
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await apiFetch(`/api${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    throw new ApiError(
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((e: { msg: string }) => e.msg).join('; ')
          : `Request failed (${response.status}). Please try again.`,
      response.status,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
export const json = (value: unknown) => JSON.stringify(value);
export const workspacePath = (workspaceId: string) =>
  `/workspaces/${encodeURIComponent(workspaceId)}`;
export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'Something went wrong. Please try again.';
export const formatDate = (date: string) =>
  new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' }).format(
    new Date(date),
  );
export const label = (value: string) =>
  value.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase());
