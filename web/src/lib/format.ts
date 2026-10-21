export const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)

export function fmtBytes(n: number | null | undefined, digits = 1): string {
  if (!isNum(n)) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(i === 0 ? 0 : digits)} ${units[i]}`
}

export const fmtRate = (n: number | null | undefined) => (isNum(n) ? `${fmtBytes(n)}/s` : '—')
export const fmtPercent = (n: number | null | undefined, digits = 0) => (isNum(n) ? `${n.toFixed(digits)}%` : '—')
export const fmtTemp = (n: number | null | undefined) => (isNum(n) ? `${n.toFixed(0)}°C` : '—')

export function fmtDuration(seconds: number | null | undefined): string {
  if (!isNum(seconds)) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

export function fmtAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return 'never'
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

/** Severity of a utilisation value; thresholds mirror the server defaults. */
export function levelFor(pct: number | null | undefined, warn = 85, crit = 95): 'ok' | 'warn' | 'crit' | 'unknown' {
  if (!isNum(pct)) return 'unknown'
  return pct >= crit ? 'crit' : pct >= warn ? 'warn' : 'ok'
}
