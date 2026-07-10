// lib/api-client.ts
// Shared fetch helper for BFF routes → Python backend

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export async function fetchFromBackend<T = unknown>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${BACKEND_URL}${path}`;
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Backend ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}