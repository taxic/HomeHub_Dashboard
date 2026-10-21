import { lazy, Suspense, type ComponentProps } from 'react'
import { Spinner } from './ui'

// Recharts is the heaviest dependency; load it only when a chart is first shown.
const Chart = lazy(() => import('./MetricChart').then((m) => ({ default: m.MetricChart })))

export function MetricChart(props: ComponentProps<typeof Chart>) {
  return (
    <Suspense fallback={<div className="empty" style={{ minHeight: props.height ?? 180 }}><Spinner label="Loading chart" /></div>}>
      <Chart {...props} />
    </Suspense>
  )
}
