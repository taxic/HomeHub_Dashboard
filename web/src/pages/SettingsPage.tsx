import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useApiKeys, useApiMutation, useSessions, useSettings } from '../api/hooks'
import type { ApiKeyCreated, AppSettings } from '../api/types'
import { Banner, Card, ConfirmDialog, Field, PageHead, QueryBoundary, Tabs } from '../components/ui'
import { fmtAgo } from '../lib/format'
import { applyTheme, storedTheme, type ThemePref } from '../lib/theme'

type NumField = { key: keyof AppSettings; label: string; min: number; max: number; unit?: string; hint?: string }

const GROUPS: Record<string, NumField[]> = {
  monitoring: [
    { key: 'host_sample_seconds', label: 'Host sampling interval', min: 5, max: 60, unit: 's' },
    { key: 'docker_refresh_seconds', label: 'Docker refresh interval', min: 5, max: 120, unit: 's' },
    { key: 'metric_persist_seconds', label: 'History sample interval', min: 30, max: 600, unit: 's', hint: 'How often a row is written to the history database.' },
    { key: 'retention_raw_hours', label: 'Keep full-resolution history', min: 6, max: 168, unit: 'hours' },
    { key: 'retention_rollup_days', label: 'Keep 5-minute history', min: 7, max: 365, unit: 'days' },
    { key: 'retention_events_days', label: 'Keep events & resolved alerts', min: 7, max: 730, unit: 'days' },
    { key: 'service_failure_threshold', label: 'Failed checks before "unhealthy"', min: 1, max: 20 },
  ],
  alerts: [
    { key: 'cpu_warn_percent', label: 'CPU warning', min: 1, max: 100, unit: '%' },
    { key: 'cpu_crit_percent', label: 'CPU critical', min: 1, max: 100, unit: '%' },
    { key: 'cpu_duration_minutes', label: 'CPU must stay high for', min: 1, max: 120, unit: 'min' },
    { key: 'mem_warn_percent', label: 'Memory warning', min: 1, max: 100, unit: '%' },
    { key: 'mem_crit_percent', label: 'Memory critical', min: 1, max: 100, unit: '%' },
    { key: 'mem_duration_minutes', label: 'Memory must stay high for', min: 1, max: 120, unit: 'min' },
    { key: 'storage_warn_percent', label: 'Storage warning', min: 1, max: 100, unit: '%' },
    { key: 'storage_crit_percent', label: 'Storage critical', min: 1, max: 100, unit: '%' },
    { key: 'alert_renotify_minutes', label: 'Re-notify unacknowledged alerts every', min: 5, max: 10080, unit: 'min' },
  ],
}

export function validateNumbers(values: Record<string, string>, fields: NumField[]): Record<string, string> {
  const e: Record<string, string> = {}
  for (const f of fields) {
    const n = Number(values[f.key])
    if (values[f.key] === '' || !Number.isFinite(n)) e[f.key] = 'Enter a number'
    else if (n < f.min || n > f.max) e[f.key] = `Between ${f.min} and ${f.max}`
  }
  for (const p of ['cpu', 'mem', 'storage']) {
    if (!e[`${p}_warn_percent`] && !e[`${p}_crit_percent`] && values[`${p}_warn_percent`] !== undefined && Number(values[`${p}_warn_percent`]) >= Number(values[`${p}_crit_percent`])) e[`${p}_warn_percent`] = 'Warning must be lower than critical'
  }
  return e
}

function NumberForm({ group, s }: { group: string; s: AppSettings }) {
  const fields = GROUPS[group]
  const [vals, setVals] = useState<Record<string, string>>(Object.fromEntries(fields.map((f) => [f.key, String(s[f.key])])))
  const [errs, setErrs] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<{ kind: 'info' | 'crit'; text: string } | null>(null)
  const m = useApiMutation((b: Record<string, number>) => api('/settings', { method: 'PATCH', body: b }), [['settings']])
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const v = validateNumbers(vals, fields)
    setErrs(v)
    if (Object.keys(v).length) return
    try {
      await m.mutateAsync(Object.fromEntries(fields.map((f) => [f.key, Number(vals[f.key])])))
      setMsg({ kind: 'info', text: 'Saved. Changes apply on the next monitoring cycle.' })
    } catch (err) {
      if (err instanceof ApiError && err.details?.length) setErrs(Object.fromEntries(err.details.map((d) => [d.field, d.message])))
      setMsg({ kind: 'crit', text: err instanceof ApiError ? err.message : 'Cannot reach the backend' })
    }
  }
  return (
    <form onSubmit={submit} noValidate>
      {msg && <Banner kind={msg.kind} title={msg.text} />}
      <div className="grid cols-2" style={{ columnGap: 20 }}>
        {fields.map((f) => (
          <Field key={f.key} label={`${f.label}${f.unit ? ` (${f.unit})` : ''}`} htmlFor={`s-${f.key}`} hint={f.hint} error={errs[f.key]}>
            <input id={`s-${f.key}`} className="input" inputMode="decimal" value={vals[f.key]} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })} aria-invalid={!!errs[f.key]} />
          </Field>
        ))}
      </div>
      <button className="btn primary" disabled={m.isPending}>{m.isPending ? 'Saving…' : 'Save changes'}</button>
    </form>
  )
}

function Notifications({ s, configured }: { s: AppSettings; configured: boolean }) {
  const m = useApiMutation((b: Partial<AppSettings>) => api('/settings', { method: 'PATCH', body: b }), [['settings']])
  const test = useApiMutation(() => api('/settings/test-notification', { method: 'POST' }), [])
  return (
    <div className="stack">
      {!configured && <Banner kind="info" title="Telegram is not configured on the server">Set HOMELAB_TELEGRAM_BOT_TOKEN and HOMELAB_TELEGRAM_CHAT_ID in the deployment environment. Secrets are never entered or stored in the browser. In-app alerts work without it.</Banner>}
      <label className="check"><input type="checkbox" checked={s.telegram_enabled} onChange={(e) => m.mutate({ telegram_enabled: e.target.checked })} /> Send alerts to Telegram</label>
      <label className="check"><input type="checkbox" checked={s.notify_on_resolve} onChange={(e) => m.mutate({ notify_on_resolve: e.target.checked })} /> Also notify when an alert resolves</label>
      <Field label="Minimum severity to notify" htmlFor="n-sev">
        <select id="n-sev" className="input" style={{ maxWidth: 240 }} value={s.notify_min_severity} onChange={(e) => m.mutate({ notify_min_severity: e.target.value as 'warning' | 'critical' })}>
          <option value="warning">Warning and critical</option><option value="critical">Critical only</option>
        </select>
      </Field>
      <div className="row">
        <button className="btn" disabled={!configured || test.isPending} onClick={() => test.mutate(undefined)}>Send test message</button>
        {test.isSuccess && <span className="muted" role="status">Test message sent.</span>}
        {test.error && <span style={{ color: 'var(--crit)' }} role="alert">{(test.error as Error).message}</span>}
      </div>
    </div>
  )
}

function Dashboard({ s }: { s: AppSettings }) {
  const [theme, setTheme] = useState<ThemePref>(storedTheme())
  const m = useApiMutation((b: Partial<AppSettings>) => api('/settings', { method: 'PATCH', body: b }), [['settings']])
  const [secs, setSecs] = useState(String(s.dashboard_refresh_seconds))
  const bad = !(Number(secs) >= 5 && Number(secs) <= 300)
  return (
    <div className="stack" style={{ maxWidth: 480 }}>
      <Field label="Theme (this browser)" htmlFor="d-theme">
        <select id="d-theme" className="input" value={theme} onChange={(e) => { const t = e.target.value as ThemePref; setTheme(t); applyTheme(t) }}>
          <option value="dark">Dark</option><option value="light">Light</option><option value="system">Match system</option>
        </select>
      </Field>
      <Field label="Dashboard refresh interval (seconds)" htmlFor="d-refresh" hint="5–300. Shorter intervals mean more API requests." error={bad ? 'Between 5 and 300' : null}>
        <input id="d-refresh" className="input" inputMode="numeric" value={secs} onChange={(e) => setSecs(e.target.value)} aria-invalid={bad} />
      </Field>
      <div><button className="btn primary" disabled={bad || m.isPending} onClick={() => m.mutate({ dashboard_refresh_seconds: Number(secs) })}>Save</button></div>
    </div>
  )
}

function Security() {
  const sessions = useSessions()
  const keys = useApiKeys()
  const [cur, setCur] = useState('')
  const [next, setNext] = useState('')
  const [pwMsg, setPwMsg] = useState<{ kind: 'info' | 'crit'; text: string } | null>(null)
  const [newKey, setNewKey] = useState<ApiKeyCreated | null>(null)
  const [keyName, setKeyName] = useState('')
  const [revoke, setRevoke] = useState<number | null>(null)
  const pw = useApiMutation(() => api('/auth/change-password', { method: 'POST', body: { current_password: cur, new_password: next } }), [['sessions']])
  const mk = useApiMutation((name: string) => api<ApiKeyCreated>('/auth/api-keys', { method: 'POST', body: { name } }), [['apikeys']])
  const rmKey = useApiMutation((id: number) => api(`/auth/api-keys/${id}`, { method: 'DELETE' }), [['apikeys']])
  const rmSess = useApiMutation((id: number) => api(`/auth/sessions/${id}`, { method: 'DELETE' }), [['sessions']])
  return (
    <div className="stack">
      <Card title="Change password">
        <form onSubmit={async (e) => { e.preventDefault(); if (next.length < 12) return setPwMsg({ kind: 'crit', text: 'New password must be at least 12 characters' }); try { await pw.mutateAsync(undefined); setPwMsg({ kind: 'info', text: 'Password changed. Other sessions were signed out.' }); setCur(''); setNext('') } catch (x) { setPwMsg({ kind: 'crit', text: x instanceof ApiError ? x.message : 'Cannot reach the backend' }) } }} style={{ maxWidth: 420 }}>
          {pwMsg && <Banner kind={pwMsg.kind} title={pwMsg.text} />}
          <Field label="Current password" htmlFor="pw-c"><input id="pw-c" className="input" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
          <Field label="New password" htmlFor="pw-n" hint="At least 12 characters."><input id="pw-n" className="input" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} /></Field>
          <button className="btn primary" disabled={!cur || !next || pw.isPending}>Change password</button>
        </form>
      </Card>
      <Card title="Active sessions">
        <QueryBoundary q={sessions}>{(list) => list.map((s) => (
          <div key={s.id} className="spread" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
            <span>{s.client === 'mobile' ? 'Mobile app' : 'Web browser'}{s.current && <strong> · this session</strong>}<div className="faint">{s.user_agent ?? 'unknown device'} · signed in {fmtAgo(s.created_at)}</div></span>
            {!s.current && <button className="btn sm danger" onClick={() => rmSess.mutate(s.id)}>Sign out</button>}
          </div>
        ))}</QueryBoundary>
      </Card>
      <Card title="API keys for scripts">
        <p className="muted" style={{ marginTop: 0 }}>Keys can only report backup results (<code>backup:report</code>). They cannot read data or control containers.</p>
        {newKey && <Banner kind="info" title={`Key "${newKey.name}" created. Copy it now; it is shown only once.`}><code className="mono" style={{ userSelect: 'all' }}>{newKey.key}</code></Banner>}
        <QueryBoundary q={keys}>{(list) => list.map((k) => (
          <div key={k.id} className="spread" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
            <span>{k.name} <span className="mono faint">{k.prefix}…</span>{k.revoked_at && <span className="faint"> · revoked</span>}<div className="faint">Last used {k.last_used_at ? fmtAgo(k.last_used_at) : 'never'}</div></span>
            {!k.revoked_at && <button className="btn sm danger" onClick={() => setRevoke(k.id)}>Revoke</button>}
          </div>
        ))}</QueryBoundary>
        <form className="row" style={{ marginTop: 12 }} onSubmit={async (e) => { e.preventDefault(); if (!keyName.trim()) return; try { setNewKey(await mk.mutateAsync(keyName.trim())); setKeyName('') } catch { /* surfaced below */ } }}>
          <input className="input" style={{ maxWidth: 260 }} aria-label="New API key name" placeholder="e.g. nightly-backup-script" value={keyName} onChange={(e) => setKeyName(e.target.value)} />
          <button className="btn" disabled={!keyName.trim() || mk.isPending}>Create key</button>
          {mk.error && <span style={{ color: 'var(--crit)' }} role="alert">{(mk.error as Error).message}</span>}
        </form>
      </Card>
      {revoke !== null && <ConfirmDialog title="Revoke this API key?" danger confirmLabel="Revoke" body="Scripts using it will stop being able to report." busy={rmKey.isPending} onClose={() => setRevoke(null)} onConfirm={() => rmKey.mutate(revoke, { onSuccess: () => setRevoke(null) })} />}
    </div>
  )
}

export function SettingsPage() {
  const q = useSettings()
  const [tab, setTab] = useState('monitoring')
  return (
    <>
      <PageHead title="Settings" />
      <Tabs tabs={[{ id: 'monitoring', label: 'Monitoring' }, { id: 'alerts', label: 'Alert thresholds' }, { id: 'notifications', label: 'Notifications' }, { id: 'dashboard', label: 'Dashboard' }, { id: 'security', label: 'Security' }, { id: 'about', label: 'About' }]} value={tab} onChange={setTab} />
      <QueryBoundary q={q}>
        {(d) => (
          <Card>
            {tab === 'monitoring' && <NumberForm group="monitoring" s={d.settings} />}
            {tab === 'alerts' && <NumberForm group="alerts" s={d.settings} />}
            {tab === 'notifications' && <Notifications s={d.settings} configured={d.telegram_configured} />}
            {tab === 'dashboard' && <Dashboard s={d.settings} />}
            {tab === 'security' && <Security />}
            {tab === 'about' && (
              <dl className="kv">
                <dt>Backend version</dt><dd>{d.version}</dd>
                <dt>Public URL</dt><dd>{d.public_url ?? <span className="faint">not set (HOMELAB_PUBLIC_URL)</span>}</dd>
                <dt>Container control</dt><dd>{d.docker_control_enabled ? 'Enabled on server' : 'Disabled on server (read-only)'}</dd>
                <dt>Telegram</dt><dd>{d.telegram_configured ? 'Configured' : 'Not configured'}</dd>
              </dl>
            )}
          </Card>
        )}
      </QueryBoundary>
    </>
  )
}
