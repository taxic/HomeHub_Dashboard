import { useState } from 'react'
import { api } from '../api/client'
import { useAlerts, useApiMutation, useEvents } from '../api/hooks'
import type { AlertOut } from '../api/types'
import { Card, Empty, PageHead, QueryBoundary, StatusBadge, Tabs } from '../components/ui'
import { fmtAgo, fmtDateTime } from '../lib/format'

function AlertRow({ a }: { a: AlertOut }) {
  const ack = useApiMutation(() => api(`/alerts/${a.id}/acknowledge`, { method: 'POST' }), [['alerts'], ['overview']])
  const resolved = a.status === 'resolved'
  return (
    <div style={{ padding: '12px 0', borderBottom: '1px solid var(--border)' }}>
      <div className="spread">
        <div className="row">
          <StatusBadge level={resolved ? 'ok' : a.severity === 'critical' ? 'crit' : 'warn'} label={resolved ? 'Resolved' : a.severity === 'critical' ? 'Critical' : 'Warning'} />
          <strong>{a.title}</strong>
        </div>
        {!resolved && (a.acknowledged_at ? <span className="faint">Acknowledged by {a.acknowledged_by}</span> : <button className="btn sm" onClick={() => ack.mutate(undefined)} disabled={ack.isPending}>Acknowledge</button>)}
      </div>
      <div className="muted" style={{ margin: '4px 0' }}>{a.message}</div>
      <div className="faint num">First seen {fmtDateTime(a.first_seen_at)} · last {fmtAgo(a.last_seen_at)} · seen {a.occurrences}×{a.resolved_at ? ` · resolved ${fmtDateTime(a.resolved_at)}` : ''}</div>
    </div>
  )
}

function AlertList({ status }: { status: 'open' | 'resolved' }) {
  const q = useAlerts(status)
  return <QueryBoundary q={q}>{(d) => d.items.length ? <>{d.items.map((a) => <AlertRow key={a.id} a={a} />)}</> : <Empty title={status === 'open' ? 'No open alerts' : 'Nothing resolved yet'}>{status === 'open' ? 'Everything being monitored is within its limits.' : ''}</Empty>}</QueryBoundary>
}

function EventList() {
  const q = useEvents()
  return <QueryBoundary q={q}>{(d) => d.items.length ? (
    <div className="table-wrap"><table><thead><tr><th>Time</th><th>Severity</th><th>Event</th><th>By</th></tr></thead><tbody>
      {d.items.map((e) => <tr key={e.id}><td className="num" title={fmtDateTime(e.ts)}>{fmtAgo(e.ts)}</td><td><StatusBadge level={e.severity === 'critical' ? 'crit' : e.severity === 'warning' ? 'warn' : 'ok'} label={e.severity} /></td><td>{e.message}</td><td className="faint">{e.actor ?? 'system'}</td></tr>)}
    </tbody></table></div>
  ) : <Empty title="No events" />}</QueryBoundary>
}

export function AlertsPage() {
  const [tab, setTab] = useState<'open' | 'resolved' | 'events'>('open')
  return (
    <>
      <PageHead title="Alerts & events" sub="Alerts open and resolve automatically; events are the audit trail." />
      <Tabs tabs={[{ id: 'open', label: 'Open alerts' }, { id: 'resolved', label: 'History' }, { id: 'events', label: 'Events' }]} value={tab} onChange={setTab} />
      <Card>{tab === 'events' ? <EventList /> : <AlertList status={tab} />}</Card>
    </>
  )
}
