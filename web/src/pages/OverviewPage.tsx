import { Link } from 'react-router-dom'
import { NetworkError } from '../api/client'
import { useHistory, useOverview } from '../api/hooks'
import type { Overview, VolumeStatus } from '../api/types'
import { MetricChart } from '../components/LazyMetricChart'
import { Card, Empty, Meter, PageHead, QueryBoundary, StatusBadge, type Level } from '../components/ui'
import { fmtAgo, fmtBytes, fmtDuration, fmtPercent, fmtRate, fmtTemp, fmtTime, isNum, levelFor } from '../lib/format'

const HOST_STATUS: Record<string, { level: Level; label: string }> = {
  healthy: { level: 'ok', label: 'All systems healthy' },
  warning: { level: 'warn', label: 'Needs attention' },
  critical: { level: 'crit', label: 'Critical issues' },
  unknown: { level: 'unknown', label: 'Status unknown' },
}

function Metric({ title, value, unit, pct, sub, na, naText = 'Unavailable on this host' }: { title: string; value: string; unit?: string; pct?: number | null; sub?: string; na?: boolean; naText?: string }) {
  const level = levelFor(pct)
  return (
    <Card title={title}>
      <div className={`stat ${na ? 'na' : ''}`}>{value}{unit && !na && <small> {unit}</small>}</div>
      {isNum(pct) && <div style={{ margin: '10px 0 6px' }}><Meter value={pct} level={level} label={`${title} utilisation`} /></div>}
      {na ? <div className="faint">{naText}</div> : sub && <div className="muted num">{sub}</div>}
    </Card>
  )
}

export function volumeLevel(v: VolumeStatus): Level {
  if (v.state === 'ok') return levelFor(v.percent)
  return v.state === 'disabled' ? 'unknown' : 'crit'
}

function VolumeRow({ v }: { v: VolumeStatus }) {
  const lvl = volumeLevel(v)
  return (
    <div style={{ marginBottom: 12 }}>
      <div className="spread">
        <strong>{v.name}</strong>
        {v.state === 'ok' ? <span className="num">{fmtPercent(v.percent)}</span> : <StatusBadge level={lvl} label={v.state === 'unmounted' ? 'Not mounted' : v.state[0].toUpperCase() + v.state.slice(1)} />}
      </div>
      {v.state === 'ok' ? (
        <>
          <Meter value={v.percent} level={lvl} label={`${v.name} usage`} />
          <div className="faint num">{fmtBytes(v.used_bytes)} of {fmtBytes(v.total_bytes)} · {fmtBytes(v.free_bytes)} free</div>
        </>
      ) : <div className="muted">{v.message}</div>}
    </div>
  )
}

function Counts({ o }: { o: Overview }) {
  const c = o.containers
  const s = o.services
  return (
    <div className="grid cols-4">
      <Card title="Containers" action={<Link to="/containers">View</Link>}>
        {c.available ? (
          <>
            <div className="stat">{c.running}<small> running</small></div>
            <div className="muted num">{c.stopped} stopped · {c.unhealthy} unhealthy · {c.total} total</div>
          </>
        ) : <><div className="stat na">—</div><div className="faint">Docker unavailable{c.error ? '' : ''}</div></>}
      </Card>
      <Card title="Services" action={<Link to="/services">View</Link>}>
        <div className="stat">{s.healthy}<small> healthy</small></div>
        <div className="muted num">{s.unhealthy} unhealthy · {s.degraded + s.unknown} unknown/degraded · {s.disabled} disabled</div>
      </Card>
      <Card title="Backups" action={<Link to="/backups">View</Link>}>
        <div className="stat">{o.backups.ok}<small> / {o.backups.total} OK</small></div>
        <div className="muted">{o.backups.problem ? `${o.backups.problem} need attention` : o.backups.total ? 'All reporting fine' : 'None configured'}</div>
      </Card>
      <Card title="Open alerts" action={<Link to="/alerts">View</Link>}>
        <div className="stat">{o.alerts.open}</div>
        <div className="muted num">{o.alerts.critical} critical · {o.alerts.warning} warning · {o.alerts.unacknowledged} unacknowledged</div>
      </Card>
    </div>
  )
}

export function OverviewPage() {
  const q = useOverview()
  const hist = useHistory('1h')
  const disconnected = q.error instanceof NetworkError
  return (
    <>
      <PageHead title="Overview" sub={q.data ? <>Last host sample {fmtTime(q.data.last_update)} ({fmtAgo(q.data.last_update)}) · refresh every {q.data.refresh_seconds}s</> : undefined} />
      <QueryBoundary q={q}>
        {(o) => {
          const h = o.host
          const hs = HOST_STATUS[o.status]
          return (
            <div className="stack" style={disconnected ? { opacity: 0.6 } : undefined}>
              <Card>
                <div className="spread">
                  <div className="row">
                    <StatusBadge level={hs.level} label={hs.label} />
                    {o.status_reason && <span className="muted">{o.status_reason}</span>}
                  </div>
                  {h && <span className="muted num">Uptime {fmtDuration(h.uptime_seconds)} · Load {h.load_avg ? h.load_avg.map((x) => x.toFixed(2)).join(' ') : '—'}</span>}
                </div>
              </Card>
              {!h ? (
                <Card><Empty title="No host metrics yet">The monitor has not produced a sample. This usually resolves within seconds of startup.</Empty></Card>
              ) : (
                <div className="grid cols-4">
                  <Metric title="CPU" value={isNum(h.cpu_percent) ? h.cpu_percent.toFixed(0) : '—'} unit="%" pct={h.cpu_percent} na={!isNum(h.cpu_percent)} sub={h.cpu_count ? `${h.cpu_count} threads` : undefined} />
                  <Metric title="Memory" value={isNum(h.memory?.percent) ? h.memory!.percent.toFixed(0) : '—'} unit="%" pct={h.memory?.percent} na={!h.memory} sub={h.memory ? `${fmtBytes(h.memory.available_bytes)} available of ${fmtBytes(h.memory.total_bytes)}` : undefined} />
                  <Metric title="Root filesystem" value={o.root_volume?.state === 'ok' ? fmtPercent(o.root_volume.percent).replace('%', '') : '—'} unit="%" pct={o.root_volume?.percent} na={o.root_volume?.state !== 'ok'} sub={o.root_volume?.state === 'ok' ? `${fmtBytes(o.root_volume.free_bytes)} free` : undefined} />
                  <Card title="Network">
                    {h.network ? (
                      <>
                        <div className="num">↓ <strong>{h.network.rx_bps === null ? '—' : fmtRate(h.network.rx_bps)}</strong></div>
                        <div className="num">↑ <strong>{h.network.tx_bps === null ? '—' : fmtRate(h.network.tx_bps)}</strong></div>
                        <div className="faint">{h.network.interfaces.join(', ') || 'no interfaces'}</div>
                      </>
                    ) : <><div className="stat na">—</div><div className="faint">Host network counters unavailable (see docs)</div></>}
                  </Card>
                  <Metric title="CPU temperature" value={isNum(h.temperature_c) ? fmtTemp(h.temperature_c).replace('°C', '') : '—'} unit="°C" na={!isNum(h.temperature_c)} sub={h.temperatures.length ? `${h.temperatures.length} sensors` : undefined} />
                  <Metric title="Swap" value={h.swap ? h.swap.percent.toFixed(0) : '—'} unit="%" pct={h.swap?.percent} na={!h.swap} naText="No swap configured" sub={h.swap ? fmtBytes(h.swap.total_bytes) + ' total' : undefined} />
                </div>
              )}
              <Counts o={o} />
              <div className="grid cols-2">
                <Card title="Storage volumes" action={<Link to="/storage">Details</Link>}>
                  {o.volumes.length === 0 && !o.root_volume ? <Empty title="No volumes">Add volumes in Storage.</Empty> : (
                    <>
                      {o.root_volume && <VolumeRow v={o.root_volume} />}
                      {o.volumes.map((v) => <VolumeRow key={v.id ?? v.name} v={v} />)}
                    </>
                  )}
                </Card>
                <Card title="Trend · last hour" action={<Link to="/metrics">More</Link>}>
                  <MetricChart title="CPU and memory" points={hist.data?.points ?? []} range="1h" format={(v) => `${v.toFixed(0)}%`} domain={[0, 100]} height={150}
                    series={[{ key: 'cpu_percent', label: 'CPU', color: 'var(--series-1)' }, { key: 'mem_percent', label: 'Memory', color: 'var(--series-2)' }]} />
                </Card>
              </div>
              <div className="grid cols-2">
                <Card title="Recent alerts" action={<Link to="/alerts">All</Link>}>
                  {o.recent_alerts.length === 0 ? <p className="muted">No alerts recorded.</p> : o.recent_alerts.map((a) => (
                    <div key={a.id} className="spread" style={{ padding: '6px 0' }}>
                      <span>{a.title}<div className="faint">{fmtAgo(a.last_seen_at)}</div></span>
                      <StatusBadge level={a.status === 'resolved' ? 'ok' : a.severity === 'critical' ? 'crit' : 'warn'} label={a.status === 'resolved' ? 'Resolved' : a.severity === 'critical' ? 'Critical' : 'Warning'} />
                    </div>
                  ))}
                </Card>
                <Card title="Recent events">
                  {o.recent_events.length === 0 ? <p className="muted">No events yet.</p> : o.recent_events.map((e) => (
                    <div key={e.id} style={{ padding: '4px 0' }}>{e.message}<div className="faint">{fmtAgo(e.ts)}</div></div>
                  ))}
                </Card>
              </div>
            </div>
          )
        }}
      </QueryBoundary>
    </>
  )
}
