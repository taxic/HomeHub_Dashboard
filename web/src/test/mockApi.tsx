import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { setAccessToken } from '../api/client'

type Handler = (req: { method: string; path: string; body: unknown }) => { status?: number; body?: unknown } | undefined
export type Calls = { method: string; path: string; body: unknown }[]

/** Replaces global fetch with a route table. `offline` makes every request fail like a dead network. */
export function mockFetch(handlers: Record<string, Handler | { status?: number; body?: unknown }>, opts: { offline?: () => boolean } = {}) {
  const calls: Calls = []
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (opts.offline?.()) throw new TypeError('Failed to fetch')
    const url = new URL(String(input), 'http://localhost')
    const path = url.pathname.replace('/api/v1', '')
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ method, path, body })
    const h = handlers[`${method} ${path}`]
    const r = typeof h === 'function' ? h({ method, path, body }) : h
    if (!r) return new Response(JSON.stringify({ error: { code: 'not_found', message: `no mock for ${method} ${path}` } }), { status: 404 })
    return new Response(JSON.stringify(r.body ?? {}), { status: r.status ?? 200, headers: { 'content-type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fn)
  return calls
}

export function renderWithProviders(ui: ReactElement, { route = '/' }: { route?: string } = {}) {
  setAccessToken('test-token')
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

const now = new Date().toISOString()
export const volume = (o: Record<string, unknown> = {}) => ({ id: null, name: 'Root filesystem', path: '/', kind: 'root', required: true, state: 'ok', message: null, total_bytes: 1e11, used_bytes: 2.5e10, free_bytes: 7.5e10, percent: 25, checked_at: now, ...o })

export const overview = (o: Record<string, unknown> = {}) => ({
  status: 'healthy', status_reason: null, generated_at: now, last_update: now, stale: false, refresh_seconds: 10,
  host: { sampled_at: now, cpu_percent: 12.3, cpu_count: 4, load_avg: [0.5, 0.4, 0.3], memory: { total_bytes: 16e9, used_bytes: 4e9, available_bytes: 12e9, percent: 25 }, swap: null, uptime_seconds: 90000, temperature_c: null, temperatures: [], network: { rx_bps: 0, tx_bps: null, rx_total_bytes: 1, tx_total_bytes: 1, interfaces: ['eth0'] }, disk_io: null },
  root_volume: volume(), volumes: [volume({ id: 1, name: 'Media HDD', path: '/mnt/media', kind: 'external', state: 'unmounted', message: 'Path is not a mount point', percent: null, total_bytes: null, used_bytes: null, free_bytes: null })],
  containers: { available: true, running: 3, stopped: 1, unhealthy: 0, total: 4, error: null },
  services: { healthy: 2, unhealthy: 1, unknown: 0, degraded: 0, disabled: 0, total: 3 },
  backups: { total: 1, ok: 1, problem: 0 }, alerts: { open: 0, critical: 0, warning: 0, unacknowledged: 0 },
  recent_alerts: [], recent_events: [], ...o,
})

export const container = (o: Record<string, unknown> = {}) => ({ id: 'a'.repeat(64), short_id: 'a'.repeat(12), name: 'plex', image: 'plexinc/pms:latest', state: 'running', status_text: 'running', health: 'none', created_at: now, started_at: now, restart_count: 0, stats: { cpu_percent: 5, memory_bytes: 1e8, memory_limit_bytes: null, memory_percent: null }, service_id: 1, service_name: 'Plex', can_control: true, allowed_actions: ['start', 'stop', 'restart'], protected: false, ...o })

export const service = (o: Record<string, unknown> = {}) => ({ id: 1, name: 'Plex', description: null, category: 'media', icon: null, container_name: 'plex', url: 'http://192.168.1.5:32400/web', expected_status: '200-399', verify_tls: true, interval_seconds: 60, timeout_seconds: 5, enabled: true, allow_control: true, allowed_actions: ['restart'], expected_state: 'running', health_status: 'healthy', last_checked_at: now, last_success_at: now, last_response_ms: 42, last_status_code: 200, last_error: null, consecutive_failures: 0, created_at: now, updated_at: now, container_state: 'running', container_health: 'none', effective_status: 'healthy', effective_reason: null, ...o })
