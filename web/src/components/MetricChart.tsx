import { useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { isNum } from '../lib/format'
import type { HistoryPoint, HistoryRange } from '../api/types'

export type Series = { key: keyof HistoryPoint; label: string; color: string }

const tickFmt = (range: HistoryRange) => (iso: number) => {
  const d = new Date(iso)
  return range === '7d' || range === '30d' ? d.toLocaleDateString([], { month: 'short', day: 'numeric' }) : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/**
 * Line chart where `null` renders as a gap (unavailable) rather than a zero.
 * A table view is always available (accessibility + exact values).
 */
export function MetricChart({ title, points, series, range, format, domain, height = 180 }: { title: string; points: HistoryPoint[]; series: Series[]; range: HistoryRange; format: (v: number) => string; domain?: [number, number | 'auto']; height?: number }) {
  const [table, setTable] = useState(false)
  const data = points.map((p) => ({ ...p, t: new Date(p.ts).getTime() }))
  const hasData = series.some((s) => data.some((p) => isNum(p[s.key])))
  return (
    <div>
      <div className="spread">
        <h3>{title}</h3>
        <button className="btn sm ghost" onClick={() => setTable((t) => !t)} aria-pressed={table}>{table ? 'Chart' : 'Table'}</button>
      </div>
      {!hasData ? (
        <p className="muted" style={{ padding: '24px 0' }}>No data in this range{series.length ? ' (metric unavailable or not yet collected).' : '.'}</p>
      ) : table ? (
        <div className="table-wrap" style={{ maxHeight: height + 40, overflow: 'auto' }}>
          <table>
            <thead><tr><th>Time</th>{series.map((s) => <th key={s.label}>{s.label}</th>)}</tr></thead>
            <tbody>
              {[...data].reverse().slice(0, 200).map((p) => (
                <tr key={p.t}><td className="num">{new Date(p.t).toLocaleString()}</td>{series.map((s) => <td key={s.label} className="num">{isNum(p[s.key]) ? format(p[s.key] as number) : '—'}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ width: '100%', height }} role="img" aria-label={`${title} over the selected range. Use the Table button for exact values.`}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={tickFmt(range)} tick={{ fill: 'var(--text-3)', fontSize: 11 }} stroke="var(--border)" minTickGap={40} />
              <YAxis tickFormatter={(v: number) => format(v)} tick={{ fill: 'var(--text-3)', fontSize: 11 }} stroke="var(--border)" width={76} domain={domain ?? [0, 'auto']} />
              <Tooltip
                isAnimationActive={false}
                content={({ active, payload, label }) =>
                  active && payload?.length ? (
                    <div className="chart-tip">
                      <div className="muted">{new Date(label as number).toLocaleString()}</div>
                      {series.map((s) => {
                        const v = payload[0]?.payload?.[s.key]
                        return <div key={s.label}><span style={{ color: s.color }}>●</span> {s.label}: <strong className="num">{isNum(v) ? format(v) : 'unavailable'}</strong></div>
                      })}
                    </div>
                  ) : null
                }
              />
              {series.map((s) => (
                <Line key={s.label} dataKey={s.key as string} stroke={s.color} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }} connectNulls={false} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      {series.length > 1 && (
        <div className="chart-legend">{series.map((s) => <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>)}</div>
      )}
    </div>
  )
}
