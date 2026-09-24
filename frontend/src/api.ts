export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
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
