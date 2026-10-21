import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { setAccessToken } from '../api/client'
import { AuthProvider } from '../auth/AuthProvider'
import { mockFetch, overview } from './mockApi'

const tree = (route = '/') => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}><AuthProvider><App /></AuthProvider></MemoryRouter>
    </QueryClientProvider>,
  )
}
const empty = { body: { items: [], total: 0, limit: 50, offset: 0 } }
const authed = {
  'GET /auth/status': { body: { setup_required: false, setup_token_required: false } },
  'POST /auth/refresh': { body: { access_token: 't', expires_in: 900, username: 'owner' } },
  'GET /auth/me': { body: { username: 'owner' } },
  'GET /overview': { body: overview() },
  'GET /settings': { body: { settings: { dashboard_refresh_seconds: 10 }, telegram_configured: false, docker_control_enabled: false, version: '0.1.0', public_url: null } },
  'GET /metrics/history': { body: { range: '1h', start: '', end: '', bucket_seconds: 60, points: [] } },
  'GET /services': empty, 'GET /alerts': empty, 'GET /backups': { body: [] },
}

beforeEach(() => setAccessToken(null))

describe('App', () => {
  it('first run shows the setup form with client-side password checks', async () => {
    mockFetch({ 'GET /auth/status': { body: { setup_required: true, setup_token_required: false } } })
    tree()
    expect(await screen.findByRole('heading', { name: 'Create the administrator' })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Password'), 'short')
    await userEvent.type(screen.getByLabelText('Repeat password'), 'short')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('Use at least 12 characters')).toBeInTheDocument()
  })

  it('unauthenticated users get the login form; bad credentials show an error', async () => {
    mockFetch({
      'GET /auth/status': { body: { setup_required: false, setup_token_required: false } },
      'POST /auth/refresh': { status: 401, body: { error: { code: 'invalid_refresh_token', message: 'Invalid refresh token' } } },
      'POST /auth/login': { status: 401, body: { error: { code: 'invalid_credentials', message: 'Invalid username or password' } } },
    })
    tree()
    await userEvent.type(await screen.findByLabelText('Username'), 'owner')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-password')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Invalid username or password')).toBeInTheDocument()
  })

  it('shows a backend-unreachable screen at startup', async () => {
    mockFetch({}, { offline: () => true })
    tree()
    expect(await screen.findByText('Backend unreachable')).toBeInTheDocument()
  })

  it('restores the session from the refresh cookie, renders navigation and navigates', async () => {
    mockFetch(authed)
    tree()
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    const side = screen.getByRole('navigation', { name: 'Main' })
    for (const l of ['Overview', 'Services', 'Containers', 'Metrics', 'Storage', 'Alerts & events', 'Backups', 'Settings']) expect(side).toHaveTextContent(l)
    // compact (mobile) navigation is also present; CSS decides which is visible
    const tabbar = screen.getByRole('navigation', { name: 'Primary' })
    expect(tabbar).toHaveTextContent('More')
    await userEvent.click(screen.getAllByRole('link', { name: 'Services', hidden: true })[0])
    expect(await screen.findByRole('heading', { name: 'Services' })).toBeInTheDocument()
  })

  it('"More" menu exposes secondary destinations on small screens', async () => {
    mockFetch(authed)
    tree()
    await screen.findByRole('heading', { name: 'Overview' })
    await userEvent.click(screen.getByRole('button', { name: 'More' }))
    const menu = screen.getByRole('menu')
    expect(menu).toHaveTextContent('Storage')
    expect(menu).toHaveTextContent('Backups')
    expect(menu).toHaveTextContent('Settings')
  })

  it('shows an explicit disconnected banner when polling fails after load', async () => {
    let offline = false
    mockFetch({ ...authed, 'GET /settings': { body: { settings: { dashboard_refresh_seconds: 5 }, telegram_configured: false, docker_control_enabled: false, version: '0.1.0', public_url: null } } }, { offline: () => offline })
    const { container } = tree()
    await screen.findByRole('heading', { name: 'Overview' })
    offline = true
    // Window focus triggers a refetch, which now fails like a dead network.
    window.dispatchEvent(new Event('visibilitychange'))
    expect(await screen.findByText('Disconnected from the backend', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(container.textContent).toContain('no longer updating')
  })

  it('sign out clears the session', async () => {
    mockFetch({ ...authed, 'POST /auth/logout': { body: { message: 'Signed out' } } })
    tree()
    await screen.findByRole('heading', { name: 'Overview' })
    await userEvent.click(screen.getAllByRole('button', { name: 'Sign out', hidden: true })[0])
    expect(await screen.findByRole('form', { name: 'Sign in' })).toBeInTheDocument()
  })
})
