import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useApiMutation, useService, useServices } from '../api/hooks'
import type { ServiceCreate, ServiceView } from '../api/types'
import { Icon } from '../components/Icon'
import { Banner, Card, ConfirmDialog, Dialog, Empty, ErrorState, Field, PageHead, QueryBoundary, SERVICE_STATUS, Spinner, StatusBadge } from '../components/ui'
import { fmtAgo, fmtDateTime } from '../lib/format'

export const statusBadge = (s: ServiceView) => {
  const st = SERVICE_STATUS[s.effective_status] ?? SERVICE_STATUS.unknown
  return <StatusBadge level={st.level} label={st.label} title={s.effective_reason ?? undefined} />
}

type FormState = { name: string; description: string; category: string; url: string; container_name: string; expected_status: string; interval_seconds: string; timeout_seconds: string; verify_tls: boolean; enabled: boolean; allow_control: boolean; actions: string[] }

const blank: FormState = { name: '', description: '', category: 'other', url: '', container_name: '', expected_status: '200-399', interval_seconds: '60', timeout_seconds: '5', verify_tls: true, enabled: true, allow_control: false, actions: [] }

export function validateService(f: FormState): Record<string, string> {
  const e: Record<string, string> = {}
  if (!f.name.trim()) e.name = 'Name is required'
  if (f.url.trim()) {
    try {
      const u = new URL(f.url.trim())
      if (!['http:', 'https:'].includes(u.protocol)) e.url = 'Use http:// or https://'
      else if (u.username || u.password) e.url = 'Credentials in URLs are not allowed'
    } catch {
      e.url = 'Enter a full URL such as http://192.168.1.10:32400/web'
    }
  }
  if (!f.url.trim() && !f.container_name.trim()) e.url = 'Provide a health-check URL, a container name, or both'
  if (f.container_name && !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(f.container_name.trim())) e.container_name = 'Letters, digits, _ . - only'
  if (!/^\d{3}(-\d{3})?(,\s*\d{3}(-\d{3})?)*$/.test(f.expected_status.trim())) e.expected_status = "Use codes or ranges, e.g. '200-399' or '200,401'"
  const iv = Number(f.interval_seconds)
  if (!Number.isInteger(iv) || iv < 10 || iv > 86400) e.interval_seconds = 'Between 10 and 86400 seconds'
  const to = Number(f.timeout_seconds)
  if (!(to >= 1 && to <= 30)) e.timeout_seconds = 'Between 1 and 30 seconds'
  if (f.allow_control && !f.container_name.trim()) e.allow_control = 'Control needs a container name'
  if (f.allow_control && f.actions.length === 0) e.actions = 'Choose at least one permitted action'
  return e
}

function toForm(s?: ServiceView): FormState {
  if (!s) return blank
  return { name: s.name, description: s.description ?? '', category: s.category, url: s.url ?? '', container_name: s.container_name ?? '', expected_status: s.expected_status, interval_seconds: String(s.interval_seconds), timeout_seconds: String(s.timeout_seconds), verify_tls: s.verify_tls, enabled: s.enabled, allow_control: s.allow_control, actions: s.allowed_actions }
}

export function ServiceFormDialog({ service, onClose }: { service?: ServiceView; onClose: () => void }) {
  const [f, setF] = useState<FormState>(toForm(service))
  const [errs, setErrs] = useState<Record<string, string>>({})
  const [serverErr, setServerErr] = useState<string | null>(null)
  const m = useApiMutation((body: ServiceCreate) => service ? api<ServiceView>(`/services/${service.id}`, { method: 'PATCH', body }) : api<ServiceView>('/services', { method: 'POST', body }), [['services'], ['overview']])
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((p) => ({ ...p, [k]: v }))
  const submit = async (ev: FormEvent) => {
    ev.preventDefault()
    const e = validateService(f)
    setErrs(e)
    if (Object.keys(e).length) return
    setServerErr(null)
    const body = { name: f.name.trim(), description: f.description.trim() || null, category: f.category.trim() || 'other', url: f.url.trim() || null, container_name: f.container_name.trim() || null, expected_status: f.expected_status.replace(/\s/g, ''), interval_seconds: Number(f.interval_seconds), timeout_seconds: Number(f.timeout_seconds), verify_tls: f.verify_tls, enabled: f.enabled, allow_control: f.allow_control, allowed_actions: f.allow_control ? f.actions : [] } as ServiceCreate
    try {
      await m.mutateAsync(body)
      onClose()
    } catch (err) {
      if (err instanceof ApiError && err.details?.length) setErrs(Object.fromEntries(err.details.map((d) => [d.field, d.message])))
      setServerErr(err instanceof ApiError ? err.message : 'Cannot reach the backend')
    }
  }
  const toggle = (a: string) => set('actions', f.actions.includes(a) ? f.actions.filter((x) => x !== a) : [...f.actions, a])
  return (
    <Dialog title={service ? `Edit ${service.name}` : 'Add service'} onClose={onClose} busy={m.isPending}>
      <form onSubmit={submit} noValidate>
        {serverErr && <Banner kind="crit" title={serverErr} />}
        <Field label="Name" htmlFor="sf-name" error={errs.name}><input id="sf-name" className="input" value={f.name} onChange={(e) => set('name', e.target.value)} aria-invalid={!!errs.name} /></Field>
        <div className="grid cols-2" style={{ gap: 12 }}>
          <Field label="Category" htmlFor="sf-cat"><input id="sf-cat" className="input" value={f.category} onChange={(e) => set('category', e.target.value)} placeholder="media, network, …" /></Field>
          <Field label="Description" htmlFor="sf-desc"><input id="sf-desc" className="input" value={f.description} onChange={(e) => set('description', e.target.value)} /></Field>
        </div>
        <Field label="Health-check URL" htmlFor="sf-url" error={errs.url} hint="Optional. Loopback and cloud-metadata addresses are blocked."><input id="sf-url" className="input" value={f.url} onChange={(e) => set('url', e.target.value)} placeholder="http://192.168.1.10:32400/web" aria-invalid={!!errs.url} inputMode="url" /></Field>
        <Field label="Docker container name" htmlFor="sf-cn" error={errs.container_name} hint="Optional. Links this service to a container."><input id="sf-cn" className="input" value={f.container_name} onChange={(e) => set('container_name', e.target.value)} placeholder="plex" aria-invalid={!!errs.container_name} /></Field>
        <div className="grid cols-3" style={{ gap: 12 }}>
          <Field label="Expected status" htmlFor="sf-es" error={errs.expected_status}><input id="sf-es" className="input" value={f.expected_status} onChange={(e) => set('expected_status', e.target.value)} aria-invalid={!!errs.expected_status} /></Field>
          <Field label="Interval (s)" htmlFor="sf-iv" error={errs.interval_seconds}><input id="sf-iv" className="input" inputMode="numeric" value={f.interval_seconds} onChange={(e) => set('interval_seconds', e.target.value)} aria-invalid={!!errs.interval_seconds} /></Field>
          <Field label="Timeout (s)" htmlFor="sf-to" error={errs.timeout_seconds}><input id="sf-to" className="input" inputMode="decimal" value={f.timeout_seconds} onChange={(e) => set('timeout_seconds', e.target.value)} aria-invalid={!!errs.timeout_seconds} /></Field>
        </div>
        <label className="check"><input type="checkbox" checked={f.enabled} onChange={(e) => set('enabled', e.target.checked)} /> Monitoring enabled</label>
        <label className="check"><input type="checkbox" checked={f.verify_tls} onChange={(e) => set('verify_tls', e.target.checked)} /> Verify TLS certificate (untick for self-signed)</label>
        <fieldset style={{ border: '1px solid var(--border)', borderRadius: 8, margin: '12px 0 0', padding: 12 }}>
          <legend>Remote container control</legend>
          <label className="check"><input type="checkbox" checked={f.allow_control} onChange={(e) => set('allow_control', e.target.checked)} /> Allow start/stop/restart from this app</label>
          {errs.allow_control && <span className="err" role="alert">{errs.allow_control}</span>}
          {f.allow_control && (
            <div className="row" role="group" aria-label="Permitted actions">
              {['start', 'stop', 'restart'].map((a) => <label key={a} className="check"><input type="checkbox" checked={f.actions.includes(a)} onChange={() => toggle(a)} /> {a}</label>)}
              {errs.actions && <span className="err" role="alert">{errs.actions}</span>}
            </div>
          )}
          <p className="hint faint" style={{ marginBottom: 0 }}>Also requires HOMELAB_DOCKER_CONTROL_ENABLED=true on the server.</p>
        </fieldset>
        <div className="foot">
          <button type="button" className="btn" onClick={onClose} disabled={m.isPending}>Cancel</button>
          <button className="btn primary" disabled={m.isPending}>{m.isPending ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Dialog>
  )
}

export function ServicesPage() {
  const q = useServices()
  const [adding, setAdding] = useState(false)
  const items = q.data?.items ?? []
  const groups = Object.entries(items.reduce<Record<string, ServiceView[]>>((a, s) => ((a[s.category] ??= []).push(s), a), {}))
  return (
    <>
      <PageHead title="Services" sub="Applications and their health" actions={<button className="btn primary" onClick={() => setAdding(true)}><Icon name="plus" /> Add service</button>} />
      <QueryBoundary q={q}>
        {() => items.length === 0 ? (
          <Card><Empty title="No services yet" action={<button className="btn primary" onClick={() => setAdding(true)}>Add your first service</button>}>Define services with a URL and/or Docker container. Nothing is assumed to be installed.</Empty></Card>
        ) : (
          <div className="stack">
            {groups.map(([cat, list]) => (
              <Card key={cat} title={cat}>
                {list.map((s) => (
                  <Link key={s.id} to={`/services/${s.id}`} className="spread" style={{ padding: '10px 0', textDecoration: 'none', color: 'inherit', borderBottom: '1px solid var(--border)' }}>
                    <span><strong>{s.name}</strong><div className="faint">{s.url ?? `container: ${s.container_name}`} · checked {fmtAgo(s.last_checked_at)}</div></span>
                    {statusBadge(s)}
                  </Link>
                ))}
              </Card>
            ))}
          </div>
        )}
      </QueryBoundary>
      {adding && <ServiceFormDialog onClose={() => setAdding(false)} />}
    </>
  )
}

export function ServiceDetailPage() {
  const id = Number(useParams().id)
  const nav = useNavigate()
  const q = useService(id)
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const check = useApiMutation(() => api<ServiceView>(`/services/${id}/check`, { method: 'POST' }), [['services'], ['overview']])
  const del = useApiMutation(() => api(`/services/${id}`, { method: 'DELETE' }), [['services'], ['overview']])
  useEffect(() => { document.title = q.data ? `${q.data.name} · HomeLab` : 'HomeLab Command Centre' }, [q.data])
  if (q.error instanceof ApiError && q.error.status === 404) return <Card><Empty title="Service not found" action={<Link to="/services" className="btn">Back to services</Link>} /></Card>
  return (
    <QueryBoundary q={q}>
      {(s) => (
        <>
          <PageHead title={s.name} sub={<>{s.category}{s.description ? ` · ${s.description}` : ''}</>} actions={<>
            {s.url && <button className="btn" onClick={() => check.mutate(undefined)} disabled={check.isPending}>{check.isPending ? <Spinner label="Checking" /> : <Icon name="refresh" />} Check now</button>}
            <button className="btn" onClick={() => setEditing(true)}>Edit</button>
            <button className="btn danger" onClick={() => setDeleting(true)}>Delete</button>
          </>} />
          <div className="stack">
            <Card title="Status"><div className="row">{statusBadge(s)}<span className="muted">{s.effective_reason}</span></div></Card>
            {check.error && <ErrorState error={check.error} />}
            <div className="grid cols-2">
              <Card title="Health check">
                {s.url ? (
                  <dl className="kv">
                    <dt>URL</dt><dd className="mono">{s.url}</dd>
                    <dt>Expected</dt><dd>HTTP {s.expected_status}</dd>
                    <dt>Last check</dt><dd>{fmtDateTime(s.last_checked_at)} ({fmtAgo(s.last_checked_at)})</dd>
                    <dt>Result</dt><dd>{s.health_status === 'unknown' ? 'Not checked yet' : s.last_error ? <span style={{ color: 'var(--crit)' }}>{s.last_error}</span> : `OK${s.last_status_code ? ` (HTTP ${s.last_status_code})` : ''}`}</dd>
                    <dt>Response</dt><dd className="num">{s.last_response_ms != null ? `${s.last_response_ms.toFixed(0)} ms` : '—'}</dd>
                    <dt>Last success</dt><dd>{fmtDateTime(s.last_success_at)}</dd>
                    <dt>Failures in a row</dt><dd className="num">{s.consecutive_failures}</dd>
                    <dt>Interval / timeout</dt><dd>{s.interval_seconds}s / {s.timeout_seconds}s</dd>
                  </dl>
                ) : <p className="muted">No URL configured; status comes from the Docker container only.</p>}
              </Card>
              <Card title="Docker">
                {s.container_name ? (
                  <dl className="kv">
                    <dt>Container</dt><dd><Link to={`/containers/${s.container_name}`}>{s.container_name}</Link></dd>
                    <dt>State</dt><dd>{s.container_state ?? 'unknown (Docker unavailable)'}</dd>
                    <dt>Docker health</dt><dd>{s.container_health ?? '—'}</dd>
                    <dt>Remote control</dt><dd>{s.allow_control ? `Allowed: ${s.allowed_actions.join(', ')}` : 'Not permitted'}</dd>
                  </dl>
                ) : <p className="muted">Not linked to a container.</p>}
              </Card>
            </div>
          </div>
          {editing && <ServiceFormDialog service={s} onClose={() => setEditing(false)} />}
          {deleting && <ConfirmDialog title={`Delete ${s.name}?`} danger confirmLabel="Delete service" busy={del.isPending} error={del.error ? (del.error as Error).message : null}
            body="This removes the monitoring definition only. The container and application are not touched." onClose={() => setDeleting(false)}
            onConfirm={() => del.mutate(undefined, { onSuccess: () => nav('/services') })} />}
        </>
      )}
    </QueryBoundary>
  )
}
