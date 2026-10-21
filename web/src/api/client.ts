/**
 * Typed fetch wrapper. The access token lives only in this module's memory (never in
 * localStorage); the long-lived refresh token is an HttpOnly cookie the JS cannot read.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: { field: string; message: string }[],
  ) {
    super(message)
  }
}

/** The backend could not be reached at all (as opposed to answering with an error). */
export class NetworkError extends Error {
  constructor() {
    super('Cannot reach the HomeLab backend')
  }
}

const BASE = '/api/v1'
let accessToken: string | null = null
let refreshing: Promise<boolean> | null = null
let onAuthLost: (() => void) | null = null

export const setAccessToken = (t: string | null) => {
  accessToken = t
}
export const setAuthLostHandler = (fn: (() => void) | null) => {
  onAuthLost = fn
}

type Opts = { method?: string; body?: unknown; query?: Record<string, string | number | undefined>; auth?: boolean; signal?: AbortSignal }

async function raw(path: string, o: Opts): Promise<Response> {
  const qs = o.query
    ? '?' + new URLSearchParams(Object.entries(o.query).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])).toString()
    : ''
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (o.body !== undefined) headers['Content-Type'] = 'application/json'
  if (path === '/auth/refresh' || path === '/auth/logout') headers['X-Requested-With'] = 'hlcc'
  if (o.auth !== false && accessToken) headers.Authorization = `Bearer ${accessToken}`
  try {
    return await fetch(`${BASE}${path}${qs}`, {
      method: o.method ?? 'GET',
      headers,
      body: o.body !== undefined ? JSON.stringify(o.body) : undefined,
      credentials: 'same-origin',
      signal: o.signal,
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new NetworkError()
  }
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const j = await res.json()
    const e = j.error ?? {}
    return new ApiError(res.status, e.code ?? 'error', e.message ?? res.statusText, e.details)
  } catch {
    return new ApiError(res.status, 'error', res.statusText || 'Request failed')
  }
}

/** Single-flight refresh using the HttpOnly cookie. Returns true when a new token is held. */
export function refreshSession(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      for (let attempt = 0; attempt < 3; attempt++) {
        const res = await raw('/auth/refresh', { method: 'POST', auth: false })
        if (res.ok) {
          accessToken = (await res.json()).access_token
          return true
        }
        const err = await toError(res)
        if (err.code !== 'refresh_conflict') break // another tab refreshed first: retry with new cookie
        await new Promise((r) => setTimeout(r, 300))
      }
      accessToken = null
      return false
    } finally {
      refreshing = null
    }
  })()
  return refreshing
}

export async function api<T>(path: string, o: Opts = {}): Promise<T> {
  let res = await raw(path, o)
  if (res.status === 401 && o.auth !== false) {
    if (await refreshSession()) res = await raw(path, o)
    else {
      onAuthLost?.()
    }
  }
  if (!res.ok) throw await toError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
