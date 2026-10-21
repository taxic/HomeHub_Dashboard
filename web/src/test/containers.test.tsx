import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ContainersPage } from '../pages/ContainersPage'
import { container, mockFetch, renderWithProviders } from './mockApi'

const list = (cs: unknown[], extra = {}) => ({ body: { docker_available: true, docker_error: null, refreshed_at: new Date().toISOString(), containers: cs, ...extra } })

describe('ContainersPage', () => {
  it('requires confirmation before any state change and shows progress + result', async () => {
    const calls = mockFetch({
      'GET /containers': list([container()]),
      ['POST /containers/' + 'a'.repeat(64) + '/restart']: { body: { ok: true, action: 'restart', state: 'running', message: 'Restart completed; container is now running' } },
    })
    renderWithProviders(<ContainersPage />)
    const btns = await screen.findAllByRole('button', { name: 'Restart plex' })
    await userEvent.click(btns[0])
    const dlg = await screen.findByRole('dialog')
    expect(within(dlg).getByText(/Restart plex\?/)).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false) // nothing sent yet
    await userEvent.click(within(dlg).getByRole('button', { name: 'Restart' }))
    expect(await within(dlg).findByText(/Restart completed/)).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1)
  })

  it('cancel sends nothing', async () => {
    const calls = mockFetch({ 'GET /containers': list([container()]) })
    renderWithProviders(<ContainersPage />)
    await userEvent.click((await screen.findAllByRole('button', { name: 'Stop plex' }))[0])
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  it('shows the server error when an action is refused', async () => {
    mockFetch({
      'GET /containers': list([container()]),
      ['POST /containers/' + 'a'.repeat(64) + '/stop']: { status: 403, body: { error: { code: 'not_permitted', message: 'This container is not permitted for remote control.' } } },
    })
    renderWithProviders(<ContainersPage />)
    await userEvent.click((await screen.findAllByRole('button', { name: 'Stop plex' }))[0])
    await userEvent.click(screen.getByRole('button', { name: 'Stop' }))
    expect(await screen.findByText(/not permitted for remote control/)).toBeInTheDocument()
  })

  it('offers only applicable actions and hides them for read-only / protected containers', async () => {
    mockFetch({ 'GET /containers': list([
      container({ name: 'stopped', id: 'b'.repeat(64), short_id: 'b'.repeat(12), state: 'exited', stats: null }),
      container({ name: 'ro', id: 'c'.repeat(64), short_id: 'c'.repeat(12), can_control: false, allowed_actions: [] }),
      container({ name: 'homelab-backend', id: 'd'.repeat(64), short_id: 'd'.repeat(12), can_control: false, protected: true }),
    ]) })
    renderWithProviders(<ContainersPage />)
    await screen.findAllByText('stopped')
    expect(screen.getAllByRole('button', { name: 'Start stopped' }).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Stop stopped' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /plex|ro$/ })).not.toBeInTheDocument()
    expect(screen.getAllByText('Read-only').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Protected').length).toBeGreaterThan(0)
  })

  it('shows Docker-unavailable banner without stale container rows', async () => {
    mockFetch({ 'GET /containers': list([], { docker_available: false, docker_error: 'socket refused' }) })
    renderWithProviders(<ContainersPage />)
    expect(await screen.findByText('Docker is unavailable')).toBeInTheDocument()
    expect(screen.getByText('No container data')).toBeInTheDocument()
  })

  it('renders both table and card layouts so CSS can pick one (responsive)', async () => {
    mockFetch({ 'GET /containers': list([container()]) })
    const { container: root } = renderWithProviders(<ContainersPage />)
    await screen.findAllByText('plex')
    expect(root.querySelector('table')).toBeInTheDocument()
    expect(root.querySelector('.cardlist')).toBeInTheDocument()
  })

  it('failure to reach backend during an action is reported', async () => {
    let offline = false
    mockFetch({ 'GET /containers': list([container()]) }, { offline: () => offline })
    renderWithProviders(<ContainersPage />)
    await userEvent.click((await screen.findAllByRole('button', { name: 'Restart plex' }))[0])
    offline = true
    await userEvent.click(screen.getByRole('button', { name: 'Restart' }))
    await waitFor(() => expect(screen.getByText('Cannot reach the backend')).toBeInTheDocument())
  })
})
