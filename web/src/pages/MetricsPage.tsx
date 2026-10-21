import { useState } from 'react'
import { useHistory } from '../api/hooks'
import type { HistoryRange } from '../api/types'
import { MetricChart } from '../components/LazyMetricChart'
import { Card, PageHead, QueryBoundary } from '../components/ui'
import { fmtBytes, fmtTemp } from '../lib/format'

const RANGES: { id: HistoryRange; label: string }[] = [
  { id: '1h', label: '1h' }, { id: '6h', label: '6h' }, { id: '24h', label: '24h' }, { id: '7d', label: '7d' }, { id: '30d', label: '30d' },
]
const pct = (v: number) => `${v.toFixed(0)}%`

export function MetricsPage() {
  const [range, setRange] = useState<HistoryRange>('1h')
  const q = useHistory(range)
  return (
    <>
      <PageHead title="Metrics" sub="Historical performance. Gaps mean the metric was unavailable, not zero." actions={
        <div className="seg" role="group" aria-label="Time range">
          {RANGES.map((r) => <button key={r.id} aria-pressed={range === r.id} onClick={() => setRange(r.id)}>{r.label}</button>)}
        </div>} />
      <QueryBoundary q={q}>
        {(d) => (
          <div className="grid cols-2">
            <Card><MetricChart title="CPU utilisation" points={d.points} range={range} format={pct} domain={[0, 100]} series={[{ key: 'cpu_percent', label: 'CPU', color: 'var(--series-1)' }]} /></Card>
            <Card><MetricChart title="Memory utilisation" points={d.points} range={range} format={pct} domain={[0, 100]} series={[{ key: 'mem_percent', label: 'Memory', color: 'var(--series-1)' }]} /></Card>
            <Card><MetricChart title="Storage utilisation" points={d.points} range={range} format={pct} domain={[0, 100]} series={[{ key: 'disk_root_percent', label: 'Root filesystem', color: 'var(--series-1)' }, { key: 'storage_max_percent', label: 'Fullest data volume', color: 'var(--series-2)' }]} /></Card>
            <Card><MetricChart title="Network throughput" points={d.points} range={range} format={(v) => `${fmtBytes(v)}/s`} series={[{ key: 'net_rx_bps', label: 'Download', color: 'var(--series-1)' }, { key: 'net_tx_bps', label: 'Upload', color: 'var(--series-2)' }]} /></Card>
            <Card><MetricChart title="Load average (1 min)" points={d.points} range={range} format={(v) => v.toFixed(2)} series={[{ key: 'load1', label: 'Load', color: 'var(--series-3)' }]} /></Card>
            <Card><MetricChart title="CPU temperature" points={d.points} range={range} format={fmtTemp} series={[{ key: 'temp_c', label: 'Temperature', color: 'var(--series-2)' }]} /></Card>
          </div>
        )}
      </QueryBoundary>
    </>
  )
}
