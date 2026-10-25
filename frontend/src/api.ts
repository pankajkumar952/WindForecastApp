const apiBase = '/api'

export async function getJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  return readJson<T>(await fetch(`${apiBase}${path}`, { signal }))
}

export async function postJson<T>(path: string): Promise<T> {
  return readJson<T>(await fetch(`${apiBase}${path}`, { method: 'POST' }))
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // Retain the status-based error when the server does not return JSON.
    }
    throw new Error(message)
  }
  return (await response.json()) as T
}

export function cutoffQuery(cutoff: string): string {
  return `cutoff=${encodeURIComponent(cutoff)}`
}
