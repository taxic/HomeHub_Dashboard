import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useApiMutation, useBackups } from '../api/hooks'
import type { BackupJobCreate, BackupJobOut } from '../api/types'
import { Icon } from '../components/Icon'
import { Banner, Card, ConfirmDialog, Dialog, Empty, Field, PageHead, QueryBoundary, StatusBadge, type Level } from '../components/ui'
import { fmtAgo, fmtDateTime } from '../lib/format'

const STATE: Record<string, { level: Level; label: string; help: string }> = {
  restore_verified: { level: 'ok', label: 'Restore verified', help: 'A restore test was recorded as successful recently.' },
  reported_success: { level: 'warn', label: 'Success reported', help: 'The backup script reported success. No restore test has been recorded, so restorability is unproven.' },
  never_run: { level: 'warn', label: 'Never reported', help: 'No result has been received yet.' },
  overdue: { level: 'crit', label: 'Overdue', help: 'No successful backup within the allowed age.' },
  failed: { level: 'crit', label: 'Failed', help: 'The most recent attempt failed.' },
  restore_failed: { level: 'crit', label: 'Restore test failed', help: 'The latest restore test failed; the backup may not be usable.' },
  disabled: { level: 'unknown', label: 'Disabled', help: 'Monitoring disabled.' },
}

function JobForm({ job, onClose }: { job?: BackupJobOut; onClose: () => void }) {
  const [f, setF] = useState({ name: job?.name ?? '', description: job?.description ?? '', schedule_text: job?.schedule_text ?? '', max_age_hours: String(job?.max_age_hours ?? 36), report_path: job?.report_path ?? '' })
  const [err, setErr] = useState<Record<string, string>>({})
  const m = useApiMutation((b: BackupJobCreate) => api(job ? `/backups/${job.id}` : '/backups', { method: job ? 'PATCH' : 'POST', body: b }), [['backups'], ['overview']])
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const v: Record<string, string> = {}
    if (!f.name.trim()) v.name = 'Name is required'
    const h = Number(f.max_age_hours)
    if (!Number.isInteger(h) || h < 1) v.max_age_hours = 'Whole hours, at least 1'
    setErr(v)
    if (Object.keys(v).length) return
    try {
      await m.mutateAsync({ name: f.name.trim(), description: f.description || null, schedule_text: f.schedule_text || null, report_path: f.report_path || null, max_age_hours: h } as BackupJobCreate)
      onClose()
    } catch (x) {
      setErr({ top: x instanceof ApiError ? x.message : 'Cannot reach the backend' })
    }
  }
  return (
    <Dialog title={job ? 'Edit backup job' : 'Add backup job'} onClose={onClose} busy={m.isPending}>
      <form onSubmit={submit} noValidate>
        {err.top && <Banner kind="crit" title={err.top} />}
        <Field label="Name" htmlFor="b-name" error={err.name}><input id="b-name" className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} aria-invalid={!!err.name} /></Field>
        <Field label="Description" htmlFor="b-desc"><input id="b-desc" className="input" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="Expected schedule (informational)" htmlFor="b-sched"><input id="b-sched" className="input" value={f.schedule_text} onChange={(e) => setF({ ...f, schedule_text: e.target.value })} placeholder="Daily at 02:00" /></Field>
        <Field label="Maximum acceptable age (hours)" htmlFor="b-age" error={err.max_age_hours} hint="The job is overdue if no success arrives within this time."><input id="b-age" className="input" inputMode="numeric" value={f.max_age_hours} onChange={(e) => setF({ ...f, max_age_hours: e.target.value })} aria-invalid={!!err.max_age_hours} /></Field>
        <Field label="Log / report path (label only)" htmlFor="b-path" hint="Shown for reference; the app never reads it."><input id="b-path" className="input mono" value={f.report_path} onChange={(e) => setF({ ...f, report_path: e.target.value })} /></Field>
        <div className="foot"><button type="button" className="btn" onClick={onClose} disabled={m.isPending}>Cancel</button><button className="btn primary" disabled={m.isPending}>Save</button></div>
      </form>
    </Dialog>
  )
}

export function BackupsPage() {
  const q = useBackups()
  const [edit, setEdit] = useState<BackupJobOut | 'new' | null>(null)
  const [del, setDel] = useState<BackupJobOut | null>(null)
  const rm = useApiMutation((id: number) => api(`/backups/${id}`, { method: 'DELETE' }), [['backups'], ['overview']])
  return (
    <>
      <PageHead title="Backups" sub="Status tracking only. Backups are reported by your own scripts; this app never runs or deletes them." actions={<button className="btn primary" onClick={() => setEdit('new')}><Icon name="plus" /> Add job</button>} />
      <QueryBoundary q={q}>
        {(jobs) => jobs.length === 0 ? (
          <Card><Empty title="No backup jobs">Add a job, then have your backup script report to <code>POST /api/v1/backups/&#123;id&#125;/report</code> with an API key (Settings → Security).</Empty></Card>
        ) : (
          <div className="grid cols-2">
            {jobs.map((j) => {
              const s = STATE[j.state] ?? STATE.never_run
              return (
                <Card key={j.id} title={j.schedule_text ?? 'Backup job'}>
                  <div className="spread"><h3>{j.name}</h3><StatusBadge level={s.level} label={s.label} title={s.help} /></div>
                  {j.description && <p className="muted" style={{ margin: '4px 0' }}>{j.description}</p>}
                  <p className="muted" style={{ margin: '6px 0' }}>{j.state_reason ?? s.help}</p>
                  <dl className="kv">
                    <dt>Last success</dt><dd>{j.last_success_at ? `${fmtDateTime(j.last_success_at)} (${fmtAgo(j.last_success_at)})` : 'never'}</dd>
                    <dt>Last attempt</dt><dd>{j.last_attempt_at ? `${j.last_attempt_status} · ${fmtAgo(j.last_attempt_at)}` : 'never'}</dd>
                    <dt>Restore test</dt><dd>{j.last_restore_test_at ? `${j.last_restore_test_ok ? 'passed' : 'FAILED'} · ${fmtAgo(j.last_restore_test_at)}` : 'none recorded'}</dd>
                    <dt>Max age</dt><dd>{j.max_age_hours}h</dd>
                    {j.report_path && <><dt>Log</dt><dd className="mono">{j.report_path}</dd></>}
                  </dl>
                  <div className="actions" style={{ marginTop: 10 }}><button className="btn sm" onClick={() => setEdit(j)}>Edit</button><button className="btn sm danger" onClick={() => setDel(j)}>Remove</button></div>
                </Card>
              )
            })}
          </div>
        )}
      </QueryBoundary>
      {edit && <JobForm job={edit === 'new' ? undefined : edit} onClose={() => setEdit(null)} />}
      {del && <ConfirmDialog title={`Remove ${del.name}?`} confirmLabel="Remove" danger body="Only the status record is removed. No backup data is touched." busy={rm.isPending} onClose={() => setDel(null)} onConfirm={() => rm.mutate(del.id, { onSuccess: () => setDel(null) })} />}
    </>
  )
}
