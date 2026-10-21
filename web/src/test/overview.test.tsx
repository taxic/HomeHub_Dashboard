import { screen, waitFor } from '@testing-library/react'
import { OverviewPage } from '../pages/OverviewPage'
import { mockFetch, overview, renderWithProviders } from './mockApi'

describe('OverviewPage', () => {
  it('renders real values, and "—" for unavailable metrics (not zero)', async () => {
    mockFetch({ 'GET /overview': { body: overview() }, 'GET /metrics/history': { body: { range: '1h', start: '', end: '', bucket_seconds: 60, points: [] } } })
    renderWithProviders(<OverviewPage />)
    expect(await screen.findByText('All systems healthy')).toBeInTheDocument()
    expect(screen.getByText(/14.9 GB|12\.\d GB|11\.\d GB/)).toBeInTheDocument()
    expect(screen.getByText('No swap configured')).toBeInTheDocument()
    expect(screen.getByText('↓', { exact: false }).textContent).toContain('0 B/s') // measured zero
    expect(screen.getAllByText('—').length).toBeGreaterThan(0) // temperature / tx rate unavailable
  })

  it('flags a missing mount with text, not colour alone', async () => {
    mockFetch({ 'GET /overview': { body: overview({ status: 'critical', status_reason: '1 critical alert(s) open' }) }, 'GET /metrics/history': { body: { range: '1h', start: '', end: '', bucket_seconds: 60, points: [] } } })
    renderWithProviders(<OverviewPage />)
    expect(await screen.findByText('Critical issues')).toBeInTheDocument()
    expect(screen.getByText('Not mounted')).toBeInTheDocument()
    expect(screen.getByText('Path is not a mount point')).toBeInTheDocument()
  })

  it('shows Docker as unavailable instead of zero counts', async () => {
    mockFetch({ 'GET /overview': { body: overview({ containers: { available: false, running: 0, stopped: 0, unhealthy: 0, total: 0, error: 'x' } }) }, 'GET /metrics/history': { body: { range: '1h', start: '', end: '', bucket_seconds: 60, points: [] } } })
    renderWithProviders(<OverviewPage />)
    expect(await screen.findByText('Docker unavailable')).toBeInTheDocument()
  })

  it('shows an empty state when no host sample exists yet', async () => {
    mockFetch({ 'GET /overview': { body: overview({ host: null, last_update: null, status: 'unknown', status_reason: 'No host data' }) }, 'GET /metrics/history': { body: { range: '1h', start: '', end: '', bucket_seconds: 60, points: [] } } })
    renderWithProviders(<OverviewPage />)
    expect(await screen.findByText('No host metrics yet')).toBeInTheDocument()
  })

  it('shows a backend-unreachable error state when the first load fails', async () => {
    mockFetch({}, { offline: () => true })
    renderWithProviders(<OverviewPage />)
    expect(await screen.findByText('Backend unreachable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('shows permission denied for 403', async () => {
    mockFetch({ 'GET /overview': { status: 403, body: { error: { code: 'forbidden', message: 'nope' } } } })
    renderWithProviders(<OverviewPage />)
    await waitFor(() => expect(screen.getByText('Permission denied')).toBeInTheDocument())
  })
})
