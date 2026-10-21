import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ServiceFormDialog, ServicesPage, validateService } from '../pages/ServicesPage'
import { mockFetch, renderWithProviders, service } from './mockApi'

const page = (items: unknown[]) => ({ body: { items, total: items.length, limit: 200, offset: 0 } })

describe('ServicesPage', () => {
  it('groups services and presents status as text + icon', async () => {
    mockFetch({ 'GET /services': page([service(), service({ id: 2, name: 'Pi-hole', category: 'network', effective_status: 'unhealthy', effective_reason: 'Container is exited' }), service({ id: 3, name: 'Syncthing', effective_status: 'unknown' })]) })
    renderWithProviders(<ServicesPage />)
    expect(await screen.findByText('Plex')).toBeInTheDocument()
    expect(screen.getByText('Healthy')).toBeInTheDocument()
    expect(screen.getByText('Unhealthy')).toBeInTheDocument()
    expect(screen.getByText('Unknown')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'network' })).toBeInTheDocument()
  })

  it('empty state invites adding a service', async () => {
    mockFetch({ 'GET /services': page([]) })
    renderWithProviders(<ServicesPage />)
    expect(await screen.findByText('No services yet')).toBeInTheDocument()
  })

  it('shows an error state with retry when the API fails', async () => {
    mockFetch({ 'GET /services': { status: 500, body: { error: { code: 'internal_error', message: 'An internal error occurred' } } } })
    renderWithProviders(<ServicesPage />)
    expect(await screen.findByText('Something went wrong')).toBeInTheDocument()
  })
})

describe('service form validation', () => {
  const base = { name: 'X', description: '', category: 'other', url: 'http://192.168.1.5/', container_name: '', expected_status: '200-399', interval_seconds: '60', timeout_seconds: '5', verify_tls: true, enabled: true, allow_control: false, actions: [] as string[] }
  it('accepts a valid definition', () => expect(validateService(base)).toEqual({}))
  it.each([
    [{ name: ' ' }, 'name'],
    [{ url: 'ftp://x' }, 'url'],
    [{ url: 'not a url' }, 'url'],
    [{ url: 'http://u:p@host/' }, 'url'],
    [{ url: '', container_name: '' }, 'url'],
    [{ container_name: 'bad name' }, 'container_name'],
    [{ expected_status: 'ok' }, 'expected_status'],
    [{ interval_seconds: '3' }, 'interval_seconds'],
    [{ timeout_seconds: '99' }, 'timeout_seconds'],
    [{ allow_control: true }, 'allow_control'],
    [{ allow_control: true, container_name: 'plex' }, 'actions'],
  ])('rejects %j', (patch, field) => expect(validateService({ ...base, ...patch })).toHaveProperty(field))

  it('blocks submit and shows inline errors without calling the API', async () => {
    const calls = mockFetch({})
    renderWithProviders(<ServiceFormDialog onClose={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Name is required')).toBeInTheDocument()
    expect(calls).toHaveLength(0)
  })

  it('submits a valid new service', async () => {
    const calls = mockFetch({ 'POST /services': { status: 201, body: service() } })
    let closed = false
    renderWithProviders(<ServiceFormDialog onClose={() => (closed = true)} />)
    const dlg = screen.getByRole('dialog')
    await userEvent.type(within(dlg).getByLabelText('Name'), 'Radarr')
    await userEvent.type(within(dlg).getByLabelText('Health-check URL'), 'http://192.168.1.5:7878/')
    await userEvent.click(within(dlg).getByRole('button', { name: 'Save' }))
    await screen.findByRole('dialog').catch(() => undefined)
    await vi.waitFor(() => expect(closed).toBe(true))
    const post = calls.find((c) => c.method === 'POST')!
    expect(post.body).toMatchObject({ name: 'Radarr', url: 'http://192.168.1.5:7878/', allowed_actions: [], allow_control: false })
  })

  it('surfaces server-side rejection (SSRF block) next to the field', async () => {
    mockFetch({ 'POST /services': { status: 422, body: { error: { code: 'blocked_url', message: 'Target is not allowed: link-local address', details: [{ field: 'url', message: 'Target is not allowed: link-local address' }] } } } })
    renderWithProviders(<ServiceFormDialog onClose={() => {}} />)
    await userEvent.type(screen.getByLabelText('Name'), 'Meta')
    await userEvent.type(screen.getByLabelText('Health-check URL'), 'http://169.254.169.254/')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect((await screen.findAllByText(/link-local/)).length).toBeGreaterThan(0)
  })
})
