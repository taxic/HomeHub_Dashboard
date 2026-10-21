import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useApiMutation, useContainerLogs, useContainers } from '../api/hooks'
import type { ContainerActionResult, ContainerOut } from '../api/types'
import { Icon } from '../components/Icon'
import { Banner, Card, ConfirmDialog, Empty, ErrorState, PageHead, QueryBoundary, Spinner, StatusBadge, type Level } from '../components/ui'
import { fmtAgo, fmtBytes, fmtDateTime, fmtPercent, isNum } from '../lib/format'

type Action = 'start' | 'stop' | 'restart'

function stateBadge(c: ContainerOut) {
  let level: Level = 'unknown'
  let label: string
  if (c.state === 'running') {
    level = c.health === 'unhealthy' ? 'crit' : c.health === 'starting' ? 'warn' : 'ok'
    label = c.health === 'unhealthy' ? 'Running · unhealthy' : c.health === 'starting' ? 'Running · starting' : c.health === 'healthy' ? 'Running · healthy' : 'Running'
  } else if (c.state === 'restarting') {
    level = 'warn'
    label = 'Restarting'
  } else if (c.state === 'exited' || c.state === 'dead') {
    level = 'crit'
    label = c.state === 'dead' ? 'Dead' : 'Stopped'
  } else if (c.state === 'paused' || c.state === 'created') {
    level = 'warn'
    label = c.state === 'paused' ? 'Paused' : 'Created'
  } else label = 'Unknown'
  return <StatusBadge level={level} label={label} />
}

const LABEL: Record<Action, string> = { start: 'Start', stop: 'Stop', restart: 'Restart' }

export function ContainerActions({ c, size = 'sm' }: { c: ContainerOut; size?: 'sm' | '' }) {
  const [pending, setPending] = useState<Action | null>(null)
  const [result, setResult] = useState<string | null>(null)
  const m = useApiMutation((a: Action) => api<ContainerActionResult>(`/containers/${c.id}/${a}`, { method: 'POST' }), [['containers'], ['services'], ['overview']])
  if (!c.can_control) return <span className="faint" title={c.protected ? 'Protected container' : 'Enable control on its service definition and on the server'}>{c.protected ? 'Protected' : 'Read-only'}</span>
  const available: Action[] = (['start', 'stop', 'restart'] as Action[]).filter((a) => c.allowed_actions.includes(a) && (a === 'start' ? c.state !== 'running' : c.state === 'running'))
  const close = () => { setPending(null); setResult(null); m.reset() }
  return (
    <>
      <span className="row" style={{ gap: 6 }}>
        {available.length === 0 && <span className="faint">No actions available</span>}
        {available.map((a) => (
          <button key={a} className={`btn ${size}`} onClick={() => setPending(a)} aria-label={`${LABEL[a]} ${c.name}`}>
            <Icon name={a === 'start' ? 'play' : a === 'stop' ? 'stop' : 'refresh'} size={14} />{LABEL[a]}
          </button>
        ))}
      </span>
      {pending && (
        <ConfirmDialog
          title={`${LABEL[pending]} ${c.name}?`}
          danger={pending !== 'start'}
          confirmLabel={LABEL[pending]}
          busy={m.isPending}
          result={result}
          error={m.error ? (m.error instanceof ApiError ? m.error.message : 'Cannot reach the backend') : null}
          body={pending === 'stop' ? 'The container will be stopped and will not be restarted automatically. Services running in it will become unavailable.' : pending === 'restart' ? 'The container will be restarted. Services in it will be briefly unavailable.' : 'The container will be started.'}
          onClose={close}
          onConfirm={() => m.mutate(pending, { onSuccess: (r) => setResult(r.message) })}
        />
      )}
    </>
  )
}

export function ContainersPage() {
  const q = useContainers()
  return (
    <>
      <PageHead title="Containers" sub={q.data?.refreshed_at ? `Docker snapshot ${fmtAgo(q.data.refreshed_at)}` : undefined} actions={<button className="btn" onClick={() => void q.refetch()} disabled={q.isFetching}><Icon name="refresh" /> Refresh</button>} />
      <QueryBoundary q={q}>
        {(d) => (
          <>
            {!d.docker_available && <Banner kind="warn" title="Docker is unavailable">{d.docker_error ?? 'The Docker integration cannot be reached.'} No container data is shown rather than showing stale values.</Banner>}
            {d.containers.length === 0 ? (
              <Card><Empty title={d.docker_available ? 'No containers found' : 'No container data'} /></Card>
            ) : (
              <Card>
                <div className="table-wrap responsive">
                  <table>
                    <thead><tr><th>Name</th><th>Status</th><th>Image</th><th>CPU</th><th>Memory</th><th>Restarts</th><th>Service</th><th>Actions</th></tr></thead>
                    <tbody>
                      {d.containers.map((c) => (
                        <tr key={c.id}>
                          <td><Link to={`/containers/${c.id}`}><strong>{c.name}</strong></Link><div className="faint mono">{c.short_id}</div></td>
                          <td>{stateBadge(c)}</td>
                          <td className="mono">{c.image}</td>
                          <td className="num">{isNum(c.stats?.cpu_percent) ? fmtPercent(c.stats!.cpu_percent, 1) : '—'}</td>
                          <td className="num">{isNum(c.stats?.memory_bytes) ? fmtBytes(c.stats!.memory_bytes) : '—'}</td>
                          <td className="num">{c.restart_count ?? '—'}</td>
                          <td>{c.service_id ? <Link to={`/services/${c.service_id}`}>{c.service_name}</Link> : <span className="faint">—</span>}</td>
                          <td><ContainerActions c={c} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="cardlist">
                  {d.containers.map((c) => (
                    <div key={c.id} className="card" style={{ background: 'var(--surface-2)' }}>
                      <div className="spread"><Link to={`/containers/${c.id}`}><strong>{c.name}</strong></Link>{stateBadge(c)}</div>
                      <div className="faint mono">{c.image}</div>
                      <div className="muted num" style={{ margin: '6px 0' }}>CPU {isNum(c.stats?.cpu_percent) ? fmtPercent(c.stats!.cpu_percent, 1) : '—'} · Mem {isNum(c.stats?.memory_bytes) ? fmtBytes(c.stats!.memory_bytes) : '—'}</div>
                      <ContainerActions c={c} />
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </>
        )}
      </QueryBoundary>
    </>
  )
}

export function ContainerDetailPage() {
  const id = useParams().id ?? ''
  const q = useContainers()
  const c = q.data?.containers.find((x) => x.id === id || x.name === id || x.id.startsWith(id))
  const [tail, setTail] = useState(100)
  const logs = useContainerLogs(c?.id ?? id, tail, !!c)
  return (
    <QueryBoundary q={q}>
      {(d) => !c ? (
        <Card><Empty title="Container not found" action={<Link className="btn" to="/containers">Back to containers</Link>}>{d.docker_available ? 'It may have been removed.' : 'Docker is unavailable.'}</Empty></Card>
      ) : (
        <>
          <PageHead title={c.name} sub={<span className="mono">{c.short_id} · {c.image}</span>} actions={<ContainerActions c={c} size="" />} />
          <div className="stack">
            <div className="grid cols-2">
              <Card title="State">
                <div className="row" style={{ marginBottom: 10 }}>{stateBadge(c)}<span className="muted">{c.status_text}</span></div>
                <dl className="kv">
                  <dt>Started</dt><dd>{c.started_at ? `${fmtDateTime(c.started_at)} (${fmtAgo(c.started_at)})` : '—'}</dd>
                  <dt>Created</dt><dd>{fmtDateTime(c.created_at)}</dd>
                  <dt>Restart count</dt><dd className="num">{c.restart_count ?? '—'}</dd>
                  <dt>Service</dt><dd>{c.service_id ? <Link to={`/services/${c.service_id}`}>{c.service_name}</Link> : 'Not linked to a service'}</dd>
                  <dt>Control</dt><dd>{c.protected ? 'Protected (Command Centre component)' : c.can_control ? `Allowed: ${c.allowed_actions.join(', ')}` : 'Read-only'}</dd>
                </dl>
              </Card>
              <Card title="Resources">
                {c.stats ? (
                  <dl className="kv">
                    <dt>CPU</dt><dd className="num">{isNum(c.stats.cpu_percent) ? fmtPercent(c.stats.cpu_percent, 1) : '—'}</dd>
                    <dt>Memory</dt><dd className="num">{fmtBytes(c.stats.memory_bytes)}{isNum(c.stats.memory_limit_bytes) && ` of ${fmtBytes(c.stats.memory_limit_bytes)}`}{isNum(c.stats.memory_percent) && ` (${fmtPercent(c.stats.memory_percent, 1)})`}</dd>
                  </dl>
                ) : <p className="muted">Stats unavailable (container not running or Docker did not report them).</p>}
              </Card>
            </div>
            <Card title="Recent logs" action={
              <div className="actions">
                <select className="input" style={{ width: 'auto', minHeight: 32 }} aria-label="Number of lines" value={tail} onChange={(e) => setTail(Number(e.target.value))}>
                  {[50, 100, 200, 500].map((n) => <option key={n} value={n}>Last {n} lines</option>)}
                </select>
                <button className="btn sm" onClick={() => void logs.refetch()} disabled={logs.isFetching}><Icon name="refresh" size={14} /> Reload</button>
              </div>}>
              {logs.isPending ? <Spinner label="Loading logs" /> : logs.error ? <ErrorState error={logs.error} onRetry={() => void logs.refetch()} /> : (
                <>
                  {logs.data!.truncated && <p className="faint">Output was truncated to the server's size limit.</p>}
                  <pre className="logbox" tabIndex={0} aria-label="Container log output">{logs.data!.lines.length ? logs.data!.lines.join('\n') : '(no log output)'}</pre>
                </>
              )}
            </Card>
          </div>
        </>
      )}
    </QueryBoundary>
  )
}
