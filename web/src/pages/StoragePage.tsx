import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useApiMutation, useStorage, useVolumes } from '../api/hooks'
import type { VolumeCreate, VolumeOut, VolumeStatus } from '../api/types'
import { Icon } from '../components/Icon'
import { Banner, Card, ConfirmDialog, Dialog, Empty, Field, Meter, PageHead, QueryBoundary, StatusBadge } from '../components/ui'
import { fmtBytes, fmtPercent, fmtRate, fmtTime } from '../lib/format'
import { volumeLevel } from './OverviewPage'

const STATE_LABEL: Record<string, string> = { ok: 'Mounted', missing: 'Path missing', unmounted: 'Not mounted', unreadable: 'Unreadable', unresponsive: 'Not responding', disabled: 'Disabled' }

function VolumeCard({ v }: { v: VolumeStatus }) {
  const lvl = volumeLevel(v)
  return (
    <Card title={v.kind === 'root' ? 'Host root filesystem' : v.kind === 'external' ? 'External volume' : 'Data volume'}>
      <div className="spread"><h3>{v.name}</h3><StatusBadge level={lvl} label={v.state === 'ok' ? `${fmtPercent(v.percent)} used` : STATE_LABEL[v.state]} /></div>
      <div className="mono faint" style={{ margin: '4px 0 10px' }}>{v.path}</div>
      {v.state === 'ok' ? (
        <>
          <Meter value={v.percent} level={lvl} label={`${v.name} usage`} />
          <dl className="kv" style={{ marginTop: 10 }}>
            <dt>Used</dt><dd className="num">{fmtBytes(v.used_bytes)}</dd>
            <dt>Free</dt><dd className="num">{fmtBytes(v.free_bytes)}</dd>
            <dt>Total</dt><dd className="num">{fmtBytes(v.total_bytes)}</dd>
          </dl>
        </>
      ) : <Banner kind={v.state === 'disabled' ? 'info' : 'crit'} title={STATE_LABEL[v.state]}>{v.message} The app never mounts, repairs or writes to disks.</Banner>}
      <div className="faint" style={{ marginTop: 8 }}>Checked {fmtTime(v.checked_at)}{v.required ? '' : ' · optional volume'}</div>
    </Card>
  )
}

function VolumeForm({ vol, onClose }: { vol?: VolumeOut; onClose: () => void }) {
  const [f, setF] = useState({ name: vol?.name ?? '', path: vol?.path ?? '/mnt/', kind: vol?.kind ?? 'external', required: vol?.required ?? true, require_mountpoint: vol?.require_mountpoint ?? true, marker_file: vol?.marker_file ?? '' })
  const [errs, setErrs] = useState<Record<string, string>>({})
  const [top, setTop] = useState<string | null>(null)
  const m = useApiMutation((b: Partial<VolumeCreate>) => api(vol ? `/storage/volumes/${vol.id}` : '/storage/volumes', { method: vol ? 'PATCH' : 'POST', body: b }), [['volumes'], ['storage'], ['overview']])
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const v: Record<string, string> = {}
    if (!f.name.trim()) v.name = 'Name is required'
    if (!f.path.startsWith('/') || f.path.split('/').includes('..')) v.path = 'Use an absolute path without ".."'
    if (f.marker_file && !/^[A-Za-z0-9._-]+$/.test(f.marker_file)) v.marker_file = 'A plain file name, no slashes'
    setErrs(v)
    if (Object.keys(v).length) return
    try {
      await m.mutateAsync({ name: f.name.trim(), path: f.path.trim(), kind: f.kind as 'external' | 'data', required: f.required, require_mountpoint: f.require_mountpoint, marker_file: f.marker_file || null })
      onClose()
    } catch (err) {
      if (err instanceof ApiError && err.details?.length) setErrs(Object.fromEntries(err.details.map((d) => [d.field, d.message])))
      setTop(err instanceof ApiError ? err.message : 'Cannot reach the backend')
    }
  }
  return (
    <Dialog title={vol ? 'Edit volume' : 'Monitor a volume'} onClose={onClose} busy={m.isPending}>
      <form onSubmit={submit} noValidate>
        {top && <Banner kind="crit" title={top} />}
        <Field label="Name" htmlFor="v-name" error={errs.name}><input id="v-name" className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} aria-invalid={!!errs.name} /></Field>
        <Field label="Path inside the backend container" htmlFor="v-path" error={errs.path} hint="Must be bind-mounted read-only into the backend (see deployment docs)."><input id="v-path" className="input mono" value={f.path} onChange={(e) => setF({ ...f, path: e.target.value })} aria-invalid={!!errs.path} /></Field>
        <Field label="Type" htmlFor="v-kind"><select id="v-kind" className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="external">External disk (must differ from root fs)</option><option value="data">Data volume</option></select></Field>
        <Field label="Marker file (recommended)" htmlFor="v-marker" error={errs.marker_file} hint="Create an empty file with this name on the disk itself. If it is missing the disk is reported as not mounted."><input id="v-marker" className="input mono" value={f.marker_file} onChange={(e) => setF({ ...f, marker_file: e.target.value })} placeholder=".homelab-mounted" /></Field>
        <label className="check"><input type="checkbox" checked={f.required} onChange={(e) => setF({ ...f, required: e.target.checked })} /> Required (alert if unavailable)</label>
        <label className="check"><input type="checkbox" checked={f.require_mountpoint} onChange={(e) => setF({ ...f, require_mountpoint: e.target.checked })} /> Path must be a mount point</label>
        <div className="foot"><button type="button" className="btn" onClick={onClose} disabled={m.isPending}>Cancel</button><button className="btn primary" disabled={m.isPending}>Save</button></div>
      </form>
    </Dialog>
  )
}

export function StoragePage() {
  const q = useStorage()
  const defs = useVolumes()
  const [edit, setEdit] = useState<VolumeOut | 'new' | null>(null)
  const [del, setDel] = useState<VolumeOut | null>(null)
  const rm = useApiMutation((id: number) => api(`/storage/volumes/${id}`, { method: 'DELETE' }), [['volumes'], ['storage'], ['overview']])
  return (
    <>
      <PageHead title="Storage" sub="Capacity and mount health. Read-only: nothing is mounted, repaired or written." actions={<button className="btn primary" onClick={() => setEdit('new')}><Icon name="plus" /> Monitor volume</button>} />
      <QueryBoundary q={q}>
        {(d) => (
          <div className="stack">
            <div className="grid cols-3">
              {d.root && <VolumeCard v={d.root} />}
              {d.volumes.map((v) => <VolumeCard key={v.id ?? v.name} v={v} />)}
            </div>
            {d.volumes.length === 0 && <Card><Empty title="No external volumes configured">Add each USB/SATA/HDD mount you want watched. A missing mount raises a critical alert.</Empty></Card>}
            <Card title="Disk I/O">
              {d.disk_io ? <div className="num">Read <strong>{d.disk_io.read_bps === null ? '—' : fmtRate(d.disk_io.read_bps)}</strong> · Write <strong>{d.disk_io.write_bps === null ? '—' : fmtRate(d.disk_io.write_bps)}</strong></div> : <p className="muted">Disk I/O counters unavailable.</p>}
            </Card>
            <Card title="Monitored volume definitions">
              {defs.data?.length ? defs.data.map((v) => (
                <div key={v.id} className="spread" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                  <span><strong>{v.name}</strong> <span className="mono faint">{v.path}</span></span>
                  <span className="row"><button className="btn sm" onClick={() => setEdit(v)}>Edit</button><button className="btn sm danger" onClick={() => setDel(v)}>Remove</button></span>
                </div>
              )) : <p className="muted">None.</p>}
            </Card>
          </div>
        )}
      </QueryBoundary>
      {edit && <VolumeForm vol={edit === 'new' ? undefined : edit} onClose={() => setEdit(null)} />}
      {del && <ConfirmDialog title={`Stop monitoring ${del.name}?`} confirmLabel="Remove" danger body="Only the monitoring definition is removed. Nothing on disk is touched." busy={rm.isPending} onClose={() => setDel(null)} onConfirm={() => rm.mutate(del.id, { onSuccess: () => setDel(null) })} />}
    </>
  )
}
