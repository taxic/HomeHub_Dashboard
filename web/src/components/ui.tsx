import { useEffect, useId, useRef, type ReactNode } from 'react'
import { ApiError, NetworkError } from '../api/client'
import { Icon, type IconName } from './Icon'

export type Level = 'ok' | 'warn' | 'crit' | 'unknown'

const LEVEL_ICON: Record<Level, IconName> = { ok: 'check', warn: 'warn', crit: 'x', unknown: 'help' }

/** Status is always conveyed by icon + text label, never colour alone. */
export function StatusBadge({ level, label, title }: { level: Level; label: string; title?: string }) {
  return (
    <span className={`badge ${level}`} title={title}>
      <Icon name={LEVEL_ICON[level]} size={13} />
      {label}
    </span>
  )
}

export const SERVICE_STATUS: Record<string, { level: Level; label: string }> = {
  healthy: { level: 'ok', label: 'Healthy' },
  degraded: { level: 'warn', label: 'Degraded' },
  unhealthy: { level: 'crit', label: 'Unhealthy' },
  unknown: { level: 'unknown', label: 'Unknown' },
  disabled: { level: 'unknown', label: 'Disabled' },
}

export function Card({ title, action, children, dim, className = '' }: { title?: string; action?: ReactNode; children: ReactNode; dim?: boolean; className?: string }) {
  return (
    <section className={`card ${dim ? 'dim' : ''} ${className}`} aria-label={title}>
      {(title || action) && (
        <div className="card-head">
          {title && <h2 className="card-title">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function Meter({ value, level, label }: { value: number | null | undefined; level: Level; label: string }) {
  const v = typeof value === 'number' ? Math.max(0, Math.min(100, value)) : 0
  return (
    <div className={`meter ${level === 'warn' ? 'warn' : level === 'crit' ? 'crit' : ''}`} role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={typeof value === 'number' ? Math.round(v) : undefined} aria-valuetext={typeof value === 'number' ? `${Math.round(v)} percent` : 'unavailable'}>
      <span style={{ width: `${v}%` }} />
    </div>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <span role="status" aria-live="polite">
      <span className="spinner" aria-hidden />
      <span className="sr-only">{label}…</span>
    </span>
  )
}

export function Banner({ kind, title, children }: { kind: 'warn' | 'crit' | 'info'; title?: string; children?: ReactNode }) {
  return (
    <div className={`banner ${kind}`} role={kind === 'info' ? 'status' : 'alert'}>
      <Icon name={kind === 'crit' ? 'x' : kind === 'warn' ? 'warn' : 'help'} />
      <div>
        {title && <strong>{title}</strong>}
        {children && <div className="muted">{children}</div>}
      </div>
    </div>
  )
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <p style={{ margin: '0 0 12px' }}>{children}</p>}
      {action}
    </div>
  )
}

/** Distinguishes: backend unreachable / permission denied / generic error. */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  let title = 'Something went wrong'
  let detail = error instanceof Error ? error.message : 'Unknown error'
  if (error instanceof NetworkError) {
    title = 'Backend unreachable'
    detail = 'The HomeLab backend did not respond. Check that it is running and that you are connected (e.g. to Tailscale).'
  } else if (error instanceof ApiError && error.status === 403) {
    title = 'Permission denied'
  } else if (error instanceof ApiError && error.status === 503) {
    title = 'Service unavailable'
  }
  return (
    <div className="empty" role="alert">
      <h3>{title}</h3>
      <p style={{ margin: '0 0 12px' }}>{detail}</p>
      {onRetry && (
        <button className="btn" onClick={onRetry}>
          <Icon name="refresh" /> Try again
        </button>
      )}
    </div>
  )
}

/** Wraps a react-query result: loading → skeleton spinner, first-load error → ErrorState. */
export function QueryBoundary<T>({ q, children }: { q: { data: T | undefined; isPending: boolean; error: unknown; refetch: () => unknown }; children: (data: T) => ReactNode }) {
  if (q.data !== undefined) return <>{children(q.data)}</>
  if (q.isPending) return <div className="empty"><Spinner /></div>
  return <ErrorState error={q.error} onRetry={() => void q.refetch()} />
}

export function Dialog({ title, onClose, children, footer, busy }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; busy?: boolean }) {
  const id = useId()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    ref.current?.querySelector<HTMLElement>('input,select,textarea,button')?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      prev?.focus?.()
    }
  }, [onClose, busy])
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && !busy && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby={id} ref={ref}>
        <h2 id={id}>{title}</h2>
        {children}
        {footer && <div className="foot">{footer}</div>}
      </div>
    </div>
  )
}

export function ConfirmDialog({ title, body, confirmLabel, danger, busy, error, result, onConfirm, onClose }: { title: string; body: ReactNode; confirmLabel: string; danger?: boolean; busy?: boolean; error?: string | null; result?: string | null; onConfirm: () => void; onClose: () => void }) {
  return (
    <Dialog title={title} onClose={onClose} busy={busy} footer={
      result ? <button className="btn primary" onClick={onClose}>Close</button> : <>
        <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
        <button className={`btn ${danger ? 'danger' : 'primary'}`} onClick={onConfirm} disabled={busy}>{busy ? 'Working…' : confirmLabel}</button>
      </>
    }>
      {result ? <Banner kind="info" title="Done">{result}</Banner> : <div className="muted">{body}</div>}
      {busy && <p role="status"><Spinner label="Operation in progress" /> <span className="muted">Waiting for Docker to finish…</span></p>}
      {error && <Banner kind="crit" title="Operation failed">{error}</Banner>}
    </Dialog>
  )
}

export function Field({ label, hint, error, children, htmlFor }: { label: string; hint?: string; error?: string | null; children: ReactNode; htmlFor: string }) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && !error && <span className="hint">{hint}</span>}
      {error && <span className="err" role="alert">{error}</span>}
    </div>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}>{t.label}</button>
      ))}
    </div>
  )
}

export function PageHead({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  )
}
